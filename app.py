from flask import Flask, render_template, jsonify, request, Response
from utils import read_models_from_file
from ratings import RatingsTable
from match import ChessGame
from client import OpenRouterClient
import json

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

    def generate_moves():
        while not game.is_over:
            move_result = game.play_next_move()
            if move_result:
                event_data = f"data: {json.dumps(move_result)}\n\n"
                print(f"Sending event: {event_data.strip()}")
                yield event_data
            else:
                break

        # Update ratings after game is over
        result = game.game.headers.get("Result")
        if result:
            ratings = RatingsTable()
            ratings.apply_result(white_model, black_model, result)
            print(f"Updated ratings: {white_model} vs {black_model} -> {result}")

        # Final update
        final_state = {
            "is_over": True,
            "result": result,
            "termination": game.game.headers.get("Termination"),
        }
        event_data = f"data: {json.dumps(final_state)}\n\n"
        print(f"Sending final event: {event_data.strip()}")
        yield event_data

    return Response(generate_moves(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True)
