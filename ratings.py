"""Update Elo ratings."""

import json
import os

# K-factor controls how fast ratings move.
K_FACTOR_DEFAULT = 32

# Where to save ratings
RATINGS_FILE = "ratings.json"


def expected_score(rating_a, rating_b):
    """Return how much we expect A to score vs B (number between 0 and 1)."""
    exponent = (rating_b - rating_a) / 400
    return 1 / (1 + 10**exponent)


def update_elo(rating_a, rating_b, score_a):
    """Return new (rating_a, rating_b) after one game.

    score_a is 1 for win, 0.5 for draw, 0 for loss.
    """
    exp_a = expected_score(rating_a, rating_b)
    exp_b = expected_score(rating_b, rating_a)
    new_a = rating_a + K_FACTOR_DEFAULT * (score_a - exp_a)
    new_b = rating_b + K_FACTOR_DEFAULT * ((1 - score_a) - exp_b)
    return new_a, new_b


class RatingsTable:
    """Class to keep ratings in memory.

    - By default, new models start at 1200.
    - Use get/set to read and write values.
    - Use apply_result to apply a PGN-like result string ("1-0", "0-1", "1/2-1/2").
    """

    def __init__(self, default_rating=1200):
        self.default_rating = default_rating
        self.load_ratings()

    def load_ratings(self):
        if os.path.exists(RATINGS_FILE):
            with open(RATINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.ratings = {str(k): float(v) for k, v in data.items()}
        else:
            self.ratings = {}

    def get(self, player_id):
        return self.ratings.get(player_id, self.default_rating)

    def set(self, player_id, rating):
        self.ratings[player_id] = rating

    def apply_result(self, white_id, black_id, result):
        """Update ratings based on a PGN-like result string.

        - "1-0" means White won
        - "0-1" means Black won
        - "1/2-1/2" means draw
        """
        white_rating = self.get(white_id)
        black_rating = self.get(black_id)

        if result == "1-0":
            score_white = 1
        elif result == "0-1":
            score_white = 0
        else:
            score_white = 0.5

        # Update ratings
        new_white, new_black = update_elo(white_rating, black_rating, score_white)
        self.set(white_id, new_white)
        self.set(black_id, new_black)
        self.save()

    def save(self):
        with open(RATINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.ratings, f, indent=2, ensure_ascii=False)
