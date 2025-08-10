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
                self.ratings = json.load(f)
        else:
            self.ratings = {}

    def get(self, player_id):
        player_data = self.ratings.get(player_id)
        if player_data is None:
            return self.default_rating
        return player_data.get("rating", self.default_rating)

    def set(self, player_id, rating):
        if player_id not in self.ratings:
            self.ratings[player_id] = {
                "rating": rating,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "moves": 0,
                "time": 0.0,
                "cost": 0.0,
            }
        else:
            self.ratings[player_id]["rating"] = rating

    def get_stats(self, player_id):
        """Get player statistics."""
        player_data = self.ratings.get(player_id)
        if player_data is None:
            return {
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "total": 0,
                "moves": 0,
                "time": 0.0,
                "cost": 0.0,
            }

        wins = player_data.get("wins", 0)
        draws = player_data.get("draws", 0)
        losses = player_data.get("losses", 0)
        total_games = wins + draws + losses
        moves = player_data.get("moves", 0)
        time = player_data.get("time", 0.0)
        cost = player_data.get("cost", 0.0)

        return {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "total": total_games,
            "moves": moves,
            "time": time,
            "cost": cost,
        }

    def apply_result(
        self,
        white_id,
        black_id,
        result,
        white_moves=0,
        black_moves=0,
        white_time=0.0,
        black_time=0.0,
        white_cost=0.0,
        black_cost=0.0,
    ):
        """Update ratings based on a PGN-like result string.

        - "1-0" means White won
        - "0-1" means Black won
        - "1/2-1/2" means draw

        Parameters for tracking:
        - white_moves, black_moves: number of moves made by each player
        - white_time, black_time: total time spent by each player (seconds)
        - white_cost, black_cost: total cost incurred by each player (dollars)
        """
        # Ensure players exist in ratings
        if white_id not in self.ratings:
            self.set(white_id, self.default_rating)
        if black_id not in self.ratings:
            self.set(black_id, self.default_rating)

        white_rating = self.get(white_id)
        black_rating = self.get(black_id)

        if result == "1-0":
            score_white = 1
            # White wins, black loses
            self.ratings[white_id]["wins"] += 1
            self.ratings[black_id]["losses"] += 1
        elif result == "0-1":
            score_white = 0
            # Black wins, white loses
            self.ratings[black_id]["wins"] += 1
            self.ratings[white_id]["losses"] += 1
        else:
            score_white = 0.5
            # Draw for both
            self.ratings[white_id]["draws"] += 1
            self.ratings[black_id]["draws"] += 1

        # Update statistics
        self.ratings[white_id]["moves"] += white_moves
        self.ratings[white_id]["time"] += white_time
        self.ratings[white_id]["cost"] += white_cost

        self.ratings[black_id]["moves"] += black_moves
        self.ratings[black_id]["time"] += black_time
        self.ratings[black_id]["cost"] += black_cost

        # Update ratings
        new_white, new_black = update_elo(white_rating, black_rating, score_white)
        self.set(white_id, new_white)
        self.set(black_id, new_black)
        self.save()

    def save(self):
        with open(RATINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.ratings, f, indent=2, ensure_ascii=False)
