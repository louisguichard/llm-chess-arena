import threading


from flask import (
    Flask,
    render_template,
    jsonify,
    request,
)
from utils import read_models_from_file
from ratings import RatingsTable
from match import ChessGame
from client import OpenRouterClient
import traceback
from logger import log
import uuid

app = Flask(__name__)

MODELS_FILE = "models.txt"
games = {}
ratings = RatingsTable()


@app.route("/")
@app.route("/battle")
@app.route("/leaderboard")
def index():
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


@app.route("/api/start_game", methods=["POST"])
def start_game():
    data = request.get_json()
    white_model = data.get("white_player")
    black_model = data.get("black_player")

    if not white_model or not black_model:
        return jsonify({"error": "Both players must be selected."}), 400

    game = ChessGame(
        white_player=OpenRouterClient(white_model),
        black_player=OpenRouterClient(black_model),
    )

    game_id = str(uuid.uuid4())
    games[game_id] = {"game": game, "lock": threading.Lock()}
    log.info(f"Started new game: {game_id}")

    return jsonify({"game_id": game_id})


@app.route("/api/play_move/<game_id>", methods=["POST"])
def play_move(game_id):
    entry = games.get(game_id)
    if not entry:
        return jsonify({"error": "Game not found."}), 404

    game = entry["game"]
    lock = entry["lock"]

    try:
        with lock:
            if game.is_over:
                return jsonify(
                    {
                        "status": "game_over",
                        "result": game.game.headers.get("Result"),
                        "termination": game.game.headers.get("Termination"),
                    }
                )

            move_result = game.play_next_move(max_retries=2)

            if move_result and move_result.get("is_over"):
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

                # The game is over, but we send the last move to the client
                # The client will then make one more request, and the game.is_over check at the top
                # will catch it and return the final game over state.
                return jsonify(move_result)

            return jsonify(move_result)

    except Exception as e:
        log.error(f"Error during game execution: {e}")
        log.error(traceback.format_exc())
        error_event = {
            "error": "An internal error occurred during the game.",
            "details": str(e),
        }
        return jsonify(error_event), 500


@app.route("/api/game/<game_id>", methods=["GET"])
def get_game_state(game_id):
    entry = games.get(game_id)
    if not entry:
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
    }
    return jsonify(state)


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
