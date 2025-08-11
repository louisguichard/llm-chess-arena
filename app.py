from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    Response,
    stream_with_context,
)
from utils import read_models_from_file
from ratings import RatingsTable
from match import ChessGame
from client import OpenRouterClient
import json
import traceback
from logger import log
import threading
from queue import Queue, Empty

app = Flask(__name__)

MODELS_FILE = "models.txt"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/models")
def get_models():
    models = read_models_from_file(MODELS_FILE)
    return jsonify(models)


@app.route("/api/ratings")
def get_ratings():
    ratings = RatingsTable()
    return jsonify(ratings.ratings)


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

    def worker():
        log.info("Starting game worker thread...")
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
            log.error(f"An exception occurred in the game worker thread: {e}")
            log.error(traceback.format_exc())
            error_event = {
                "error": "An internal error occurred during the game.",
                "details": str(e),
            }
            q.put(error_event)
        finally:
            log.info("Game worker thread finished.")

    threading.Thread(target=worker).start()

    @stream_with_context
    def generate_moves():
        log.info("Starting game stream...")
        game_is_running = True
        while game_is_running:
            try:
                message = q.get(timeout=15)
                event_data = f"data: {json.dumps(message)}\n\n"
                yield event_data
                if message.get("is_over") or message.get("error"):
                    game_is_running = False
            except Empty:
                log.debug("Sending keepalive to prevent timeout.")
                yield ": keepalive\n\n"
        log.info("Game stream finished.")

    headers = {"Cache-Control": "no-cache"}
    return Response(
        generate_moves(),
        headers=headers,
        content_type="text/event-stream; charset=utf-8",
    )


if __name__ == "__main__":
    # Minimal local run; no extra flags to avoid errors
    app.run()
