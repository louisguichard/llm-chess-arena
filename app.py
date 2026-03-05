import threading
from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    Response,
    send_file,
)
from flask import stream_with_context
import json
import uuid
import chess
from src.utils import read_models_from_file
from src.ratings import RatingsTable
from src.match import ChessGame
from src.gcp import read_json_from_gcs
from src.client import LLMClient
from src.logger import log
from src.prompts import SYSTEM_PROMPT, build_user_prompt

app = Flask(__name__)

MODELS_FILE = "models.txt"
games = {}
ratings = RatingsTable()


@app.after_request
def add_static_cache_headers(response):
    try:
        # Cache only immutable piece assets aggressively (versioned via ?v=...)
        if request.path.startswith("/static/pieces/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    except Exception:
        pass
    return response


@app.route("/")
@app.route("/battle")
@app.route("/leaderboard")
@app.route("/about")
def index():
    try:
        ratings.load_ratings()
    except Exception:
        pass
    models = read_models_from_file(MODELS_FILE)

    # Prepare data for battle page
    llms = []
    for model_data in models:
        model_id = model_data["id"]
        display_name = model_data["name"] or model_id.split("/")[-1]
        tags = model_data.get("tags", [])
        stats = ratings.get_stats(model_id)
        llms.append(
            {
                "id": model_id,
                "name": display_name,
                "provider": model_id.split("/")[0] or "Unknown",
                "elo": ratings.get(model_id),
                "tags": tags,
                "deactivated": any(
                    (t or "").lower() in ("deactivated", "expensive") for t in tags
                ),
            }
        )

    # Prepare data for leaderboard page
    leaderboard_data = []
    sorted_players = sorted(
        ratings.ratings.items(), key=lambda item: item[1]["rating"], reverse=True
    )

    for player_id, data in sorted_players:
        stats = ratings.get_stats(player_id)
        total_games = stats["total"]
        win_rate = round(stats["wins"] / total_games * 100) if total_games > 0 else 0
        avg_time_per_move = (
            (stats["time"] / stats["moves"]) if stats["moves"] > 0 else 0
        )
        avg_cost_per_move = (
            (stats["cost"] / stats["moves"]) if stats["moves"] > 0 else 0
        )

        # Find the display name and tags from the models list
        model_info = next((m for m in models if m["id"] == player_id), None)
        display_name = (
            model_info["name"]
            if model_info and model_info["name"]
            else player_id.split("/")[-1]
        )
        tags = model_info.get("tags", []) if model_info else []

        leaderboard_data.append(
            {
                "id": player_id,
                "name": display_name,
                "provider": player_id.split("/")[0] or "Unknown",
                "elo": data["rating"],
                "matchesPlayed": total_games,
                "winRate": win_rate,
                "wins": stats["wins"],
                "draws": stats["draws"],
                "losses": stats["losses"],
                "moves": stats["moves"],
                "avgTimePerMove": avg_time_per_move,
                "avgCostPerMove": avg_cost_per_move,
                "tags": tags,
            }
        )

    return render_template(
        "index.html",
        llms=llms,
        leaderboard_data=leaderboard_data,
        initial_board=[
            ["r", "n", "b", "q", "k", "b", "n", "r"],
            ["p", "p", "p", "p", "p", "p", "p", "p"],
            ["", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", ""],
            ["P", "P", "P", "P", "P", "P", "P", "P"],
            ["R", "N", "B", "Q", "K", "B", "N", "R"],
        ],
    )


@app.route("/status")
def status():
    models = read_models_from_file(MODELS_FILE)
    return render_template("status.html", models=models)


@app.route("/api/check_model", methods=["POST"])
def check_model():
    data = request.get_json()
    model_id = data.get("model_id")
    user_openrouter_api_key = (data.get("openrouter_api_key") or "").strip()

    if not model_id:
        return jsonify({"error": "Model ID is required."}), 400

    try:
        client = LLMClient(
            model_id,
            user_openrouter_api_key=user_openrouter_api_key,
        )
        # Use the initial board prompt for a realistic check
        initial_board = chess.Board()
        user_prompt = build_user_prompt(initial_board)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        resp = client.chat(messages)
        # Fallback provider label if not provided by client
        fallback_provider = "OpenRouter"
        if resp and resp.get("completion"):
            return jsonify(
                {
                    "status": "success",
                    "provider": resp.get("provider") or fallback_provider,
                    "latency": resp.get("latency"),
                }
            )
        else:
            # If client surfaced an error, pass it through precisely
            message = None
            provider = fallback_provider
            latency = None
            if isinstance(resp, dict):
                message = resp.get("error")
                provider = resp.get("provider") or fallback_provider
                latency = resp.get("latency")
            if not message:
                message = "Empty response from model."
            return jsonify(
                {
                    "status": "error",
                    "message": message,
                    "provider": provider,
                    "latency": latency,
                }
            )
    except Exception as e:
        log.error(f"Error checking model {model_id}: {e}")
        provider = "OpenRouter"
        return jsonify(
            {"status": "error", "message": str(e), "provider": provider}
        ), 500


@app.route("/api/start_game", methods=["POST"])
def start_game():
    data = request.get_json()
    white_model_id = data.get("white_player")
    black_model_id = data.get("black_player")
    user_openrouter_api_key = (data.get("openrouter_api_key") or "").strip()

    if not white_model_id or not black_model_id:
        return jsonify({"error": "Both players must be selected."}), 400

    models = read_models_from_file(MODELS_FILE)
    white_model_data = next((m for m in models if m["id"] == white_model_id), None)
    black_model_data = next((m for m in models if m["id"] == black_model_id), None)

    if not white_model_data or not black_model_data:
        return jsonify({"error": "One or both selected models are invalid."}), 400

    if "Deactivated" in white_model_data.get("tags", []):
        return jsonify(
            {
                "error": f"{white_model_data.get('name', white_model_id)} is deactivated and cannot be used."
            }
        ), 400

    if "Deactivated" in black_model_data.get("tags", []):
        return jsonify(
            {
                "error": f"{black_model_data.get('name', black_model_id)} is deactivated and cannot be used."
            }
        ), 400

    # Build models clients
    white_client = LLMClient(
        white_model_id,
        user_openrouter_api_key=user_openrouter_api_key,
    )
    black_client = LLMClient(
        black_model_id,
        user_openrouter_api_key=user_openrouter_api_key,
    )

    game = ChessGame(
        white_player=white_client,
        black_player=black_client,
    )

    # Human-friendly game id from display names and 8-char suffix
    def slugify(s):
        s = (s or "").strip().lower()
        out = []
        for ch in s:
            if ch.isalnum():
                out.append(ch)
            elif ch in (" ", "-", "_"):
                out.append("-")
        slug = "".join(out)
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug.strip("-")
        return slug or "model"

    white_display = white_model_data.get("name") or white_model_id.split("/")[-1]
    black_display = black_model_data.get("name") or black_model_id.split("/")[-1]
    ws = slugify(white_display)
    bs = slugify(black_display)
    short = uuid.uuid4().hex[:8]
    game_id = f"{ws}-vs-{bs}-{short}"
    game.game_id = game_id
    # On stocke aussi une condition et un compteur "version" pour réveiller les clients SSE
    games[game_id] = {
        "game": game,
        "lock": threading.Lock(),
        "cond": threading.Condition(),
        "version": 0,
    }
    log.info(
        f"Starting new game: {white_model_id} vs. {black_model_id} (ID: {game_id})"
    )

    # Start the game loop in a background thread
    def run_game_loop(game_id):
        entry = games.get(game_id)
        if not entry:
            return

        game = entry["game"]
        lock = entry["lock"]
        cond = entry["cond"]

        log.info(f"Background thread started for game {game_id}")

        while not game.is_over:
            with lock:
                if game.is_over:
                    break

                move_result = game.play_next_move(max_retries=2)

                if move_result and move_result.get("is_over"):
                    try:
                        ratings.load_ratings()
                    except Exception:
                        pass
                    total_moves = len(game.board.move_stack)
                    white_moves = (total_moves + 1) // 2
                    black_moves = total_moves // 2

                    result = game.game.headers.get("Result")
                    termination = game.game.headers.get("Termination")
                    if result:
                        ratings.apply_result(
                            game.white_player.name(),
                            game.black_player.name(),
                            result,
                            white_moves=white_moves,
                            black_moves=black_moves,
                            white_time=game.white_time,
                            black_time=game.black_time,
                            white_cost=game.white_cost,
                            black_cost=game.black_cost,
                            termination=termination,
                        )
                        log.debug(
                            f"Updated ratings: {game.white_player.name()} vs {game.black_player.name()} -> {result}"
                        )

            with cond:
                entry["version"] += 1
                cond.notify_all()

        def cleanup():
            import time

            time.sleep(30)
            games.pop(game_id, None)
            log.info(f"Cleaned up game {game_id} from memory")

        threading.Thread(target=cleanup, daemon=True).start()

    threading.Thread(target=run_game_loop, args=(game_id,), daemon=True).start()

    return jsonify({"game_id": game_id})


@app.route("/api/play_move/<game_id>", methods=["POST"])
def play_move(game_id):
    entry = games.get(game_id)
    if not entry:
        return jsonify({"error": "Game not found."}), 404

    game = entry["game"]

    if game.is_over:
        return jsonify(
            {
                "status": "game_over",
                "result": game.game.headers.get("Result"),
                "termination": game.game.headers.get("Termination"),
            }
        )

    return jsonify({"status": "success"})


@app.route("/api/game/<game_id>", methods=["GET"])
def get_game_state(game_id):
    entry = games.get(game_id)
    if not entry:
        # Try loading finished game from storage
        data = read_json_from_gcs(f"games/{game_id}.json")
        if data:
            state = {
                "game_id": game_id,
                "is_over": True,
                "fen": data.get("fen"),
                "result": data.get("result"),
                "termination": data.get("termination"),
                "white_time": (data.get("stats") or {}).get("white_time", 0),
                "black_time": (data.get("stats") or {}).get("black_time", 0),
                "white_cost": (data.get("stats") or {}).get("white_cost", 0),
                "black_cost": (data.get("stats") or {}).get("black_cost", 0),
                "moves": data.get("moves") or [],
                "white_model_id": data.get("white_player"),
                "black_model_id": data.get("black_player"),
            }
            response = jsonify(state)
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            return response
        log.warning(f"Game state requested for missing game_id={game_id}")
        return jsonify({"error": "Game not found."}), 404
    game = entry["game"]
    state = {
        "game_id": game_id,
        "is_over": game.is_over,
        "fen": game.board.fen(),
        "result": game.game.headers.get("Result"),
        "termination": game.game.headers.get("Termination"),
        "white_time": game.white_time,
        "black_time": game.black_time,
        "white_cost": game.white_cost,
        "black_cost": game.black_cost,
        "moves": game.moves_log,
        "white_model_id": game.white_player.name(),
        "black_model_id": game.black_player.name(),
    }
    response = jsonify(state)
    # Prevent caches from serving stale game state
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/api/stream/<game_id>", methods=["GET"])
def stream_game_state(game_id):
    entry = games.get(game_id)
    if not entry:
        # If finished game exists in storage, stream a single state then keepalive pings
        data = read_json_from_gcs(f"games/{game_id}.json")
        if data:

            def sse(event, data):
                return f"event: {event}\ndata: {json.dumps(data)}\n\n"

            @stream_with_context
            def event_stream_finished():
                state = {
                    "game_id": game_id,
                    "is_over": True,
                    "fen": data.get("fen"),
                    "result": data.get("result"),
                    "termination": data.get("termination"),
                    "white_time": (data.get("stats") or {}).get("white_time", 0),
                    "black_time": (data.get("stats") or {}).get("black_time", 0),
                    "white_cost": (data.get("stats") or {}).get("white_cost", 0),
                    "black_cost": (data.get("stats") or {}).get("black_cost", 0),
                    "moves": data.get("moves") or [],
                    "white_model_id": data.get("white_player"),
                    "black_model_id": data.get("black_player"),
                }
                yield sse("state", state)
                # Game is over, just send state once and close connection
                return

            response = Response(event_stream_finished(), mimetype="text/event-stream")
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Accel-Buffering"] = "no"
            response.headers["Connection"] = "keep-alive"
            return response
        return jsonify({"error": "Game not found."}), 404
    cond = entry["cond"]

    def build_state():
        game = entry["game"]
        return {
            "game_id": game_id,
            "is_over": game.is_over,
            "fen": game.board.fen(),
            "result": game.game.headers.get("Result"),
            "termination": game.game.headers.get("Termination"),
            "white_time": game.white_time,
            "black_time": game.black_time,
            "white_cost": game.white_cost,
            "black_cost": game.black_cost,
            "moves": game.moves_log,
            "white_model_id": game.white_player.name(),
            "black_model_id": game.black_player.name(),
        }

    def sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    @stream_with_context
    def event_stream():
        last_version = -1
        yield sse("state", build_state())

        # If game is already over, stop here
        if entry["game"].is_over:
            return

        last_version = entry.get("version", 0)
        while True:
            with cond:
                cond.wait(timeout=15)
                current_version = entry.get("version", 0)

            if entry["game"].is_over:
                yield sse("state", build_state())
                return

            if current_version != last_version:
                last_version = current_version
                yield sse("state", build_state())
            else:
                yield sse("ping", {})

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


@app.route("/preview.png")
def preview_image():
    return send_file("screenshot.png", mimetype="image/png")


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
