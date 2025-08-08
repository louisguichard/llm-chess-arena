"""Run a small tournament between models and print the final Elo table."""

import argparse
import random
from dotenv import load_dotenv

from match import play_game
from client import OpenRouterClient
from ratings import RatingsTable
from utils import read_models_from_file


MODELS_FILE = "models.txt"


def run_tournament(models, total_matches):
    "Run a very simple tournament and update Elo ratings."

    # Initialize ratings table
    ratings = RatingsTable()
    for model in models:
        if model not in ratings.ratings:
            ratings.set(model, 1200)  # default rating

    for i in range(total_matches):
        # Randomly select two models
        white_model, black_model = random.sample(models, 2)
        print(f"Game n°{i + 1}: {white_model} (White) vs {black_model} (Black)")

        # Create clients
        white = OpenRouterClient(white_model)
        black = OpenRouterClient(black_model)

        # Play game
        result = play_game(white, black, round_no=i)
        print(f"Game n°{i + 1} result: {result}")

        # Update ratings
        ratings.apply_result(white_model, black_model, result)

    # Print final ratings
    print("\nFinal ELO ratings:")
    for model in ratings.ratings:
        print(f"- {model}: {int(ratings.get(model))}")


if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=10)
    args = parser.parse_args()

    # Read models from file
    models = read_models_from_file(MODELS_FILE)

    # Run tournament
    run_tournament(models, args.matches)
