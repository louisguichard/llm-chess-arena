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

    @stream_with_context
    def generate_moves():
        # Track statistics during the game
        white_time = 0.0
        black_time = 0.0
        white_cost = 0.0
        black_cost = 0.0

        log.info("Starting game stream...")

        try:
            while not game.is_over:
                # True when it's white to move
                is_white_turn = bool(game.board.turn)

                move_result = game.play_next_move()
                if move_result:
                    # Accumulate statistics based on whose turn it was
                    if is_white_turn:
                        white_time += move_result.get("latency", 0.0)
                        white_cost += move_result.get("cost", 0.0)
                    else:
                        black_time += move_result.get("latency", 0.0)
                        black_cost += move_result.get("cost", 0.0)

                    event_data = f"data: {json.dumps(move_result)}\n\n"
                    log.info(f"Sending event: {event_data.strip()}")
                    yield event_data
                else:
                    break
        except Exception as e:
            log.error(f"An exception occurred during the game stream: {e}")
            log.error(traceback.format_exc())
            error_event = {
                "error": "An internal error occurred during the game.",
                "details": str(e),
            }
            event_data = f"data: {json.dumps(error_event)}\n\n"
            yield event_data
        finally:
            log.info("Game stream finished.")

        # Calculate moves: total moves divided by 2, white gets the extra if odd
        total_moves = len(game.board.move_stack)
        white_moves = (total_moves + 1) // 2  # White moves first, so gets extra if odd
        black_moves = total_moves // 2

        # Update ratings after game is over
        result = game.game.headers.get("Result")
        if result:
            ratings = RatingsTable()
            ratings.apply_result(
                white_model,
                black_model,
                result,
                white_moves=white_moves,
                black_moves=black_moves,
                white_time=white_time,
                black_time=black_time,
                white_cost=white_cost,
                black_cost=black_cost,
            )
            log.info(f"Updated ratings: {white_model} vs {black_model} -> {result}")
            log.info(
                f"Game stats: W({white_moves}m, {white_time:.1f}s, ${white_cost:.4f}) vs B({black_moves}m, {black_time:.1f}s, ${black_cost:.4f})"
            )

        # Final update
        final_state = {
            "is_over": True,
            "result": result,
            "termination": game.game.headers.get("Termination"),
        }
        event_data = f"data: {json.dumps(final_state)}\n\n"
        log.info(f"Sending final event: {event_data.strip()}")
        yield event_data

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # for nginx if present
    }
    return Response(generate_moves(), mimetype="text/event-stream", headers=headers)


if __name__ == "__main__":
    app.run(debug=True)
