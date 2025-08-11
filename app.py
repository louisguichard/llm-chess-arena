from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    Response,
)
from utils import read_models_from_file
from ratings import RatingsTable
from match import ChessGame
from client import OpenRouterClient
import json
import traceback
from logger import log
import gevent
from gevent.queue import Queue


app = Flask(__name__)

MODELS_FILE = "models.txt"


@app.route("/")
def index():
    models = read_models_from_file(MODELS_FILE)
    ratings = RatingsTable()

    # Prepare data for battle page
    llms = []
    for model_id in models:
        stats = ratings.get_stats(model_id)
        llms.append(
            {
                "id": model_id,
                "name": model_id.split("/")[1] or model_id,
                "provider": model_id.split("/")[0] or "Unknown",
                "elo": ratings.get(model_id),
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

        leaderboard_data.append(
            {
                "id": player_id,
                "name": player_id.split("/")[1] or player_id,
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


@app.route("/api/start_game", methods=["GET"])
def start_game():
    white_model = request.args.get("white_player")
    black_model = request.args.get("black_player")

    if not white_model or not black_model:
        return jsonify({"error": "Both players must be selected."}), 400

    game = ChessGame(
        white_player=OpenRouterClient(white_model),
        black_player=OpenRouterClient(black_model),
    )

    q = Queue()

    def run_game():
        """Run game in a background greenlet and put results on a queue."""
        log.info("Starting game in background greenlet...")
        try:
            while not game.is_over:
                move_result = game.play_next_move(max_retries=2)
                if move_result is None:
                    break
                q.put(move_result)

            total_moves = len(game.board.move_stack)
            white_moves = (total_moves + 1) // 2
            black_moves = total_moves // 2

            result = game.game.headers.get("Result")
            if result:
                ratings = RatingsTable()
                ratings.apply_result(
                    white_model,
                    black_model,
                    result,
                    white_moves=white_moves,
                    black_moves=black_moves,
                    white_time=game.white_time,
                    black_time=game.black_time,
                    white_cost=game.white_cost,
                    black_cost=game.black_cost,
                )
                log.debug(
                    f"Updated ratings: {white_model} vs {black_model} -> {result}"
                )

            final_state = {
                "is_over": True,
                "result": result,
                "termination": game.game.headers.get("Termination"),
            }
            q.put(final_state)
        except Exception as e:
            log.error(f"Error during game execution: {e}")
            log.error(traceback.format_exc())
            error_event = {
                "error": "An internal error occurred during the game.",
                "details": str(e),
            }
            q.put(error_event)
        finally:
            log.info("Background game greenlet finished.")
            q.put(StopIteration)

    def generate_moves():
        """Yields game events and keep-alive pings."""
        log.info("Starting game stream...")
        gevent.spawn(run_game)
        try:
            while True:
                try:
                    result = q.get(timeout=15)
                    if result is StopIteration:
                        break
                    yield f"data: {json.dumps(result)}\n\n"
                except gevent.queue.Empty:
                    yield ": keep-alive\n\n"
        except Exception as e:
            log.error(f"Error during game stream: {e}")
            log.error(traceback.format_exc())
        finally:
            log.info("Game stream finished.")

    headers = {"Cache-Control": "no-cache"}
    return Response(
        generate_moves(),
        headers=headers,
        content_type="text/event-stream; charset=utf-8",
    )


if __name__ == "__main__":
    app.run(debug=True)
