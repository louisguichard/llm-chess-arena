"""Play a chess game."""

import io
import os
import time
import json

import chess
import chess.pgn
from prompts import SYSTEM_PROMPT, build_user_prompt, RetryReason


class ChessGame:
    """Single chess game between two players."""

    def __init__(self, white_player, black_player, max_moves=200, pgn_dir="games"):
        """Initialize a new chess game."""
        self.white_player = white_player
        self.black_player = black_player
        self.max_moves = max_moves
        self.pgn_dir = pgn_dir

        # Initialize game state
        self.board = chess.Board()
        self.game = chess.pgn.Game()
        self.node = self.game

        # Ensure PGN directory exists
        os.makedirs(self.pgn_dir, exist_ok=True)

        # Set up PGN headers
        self.game.headers["Event"] = "LLM Chess Arena"
        self.game.headers["Site"] = "Local"
        self.game.headers["White"] = self.white_player.name()
        self.game.headers["Black"] = self.black_player.name()
        self.game.headers["Date"] = time.strftime("%Y.%m.%d")

        # Create one chat conversation per player for the whole game
        self.white_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.black_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def extract_move_from_response(self, response):
        """Extract the move from the response.

        Returns:
            dict: Either {"move": chess.Move or "resign"} for success
                or {"error": RetryReason} for failure
        """
        if not response:
            return {"error": RetryReason.EMPTY_RESPONSE}
        # TODO: empty response could not be counted in the retry logic

        try:
            parsed_response = json.loads(response.strip())
        except json.JSONDecodeError:
            print(f"Error parsing JSON: {response}")
            return {"error": RetryReason.INVALID_JSON}

        if "move" not in parsed_response:
            print(f"Missing 'move' key in response: {parsed_response}")
            return {"error": RetryReason.MISSING_MOVE_KEY}

        try:
            move_str = parsed_response["move"].strip()
            if move_str == "resign":
                return {"move": move_str}
            return {"move": chess.Move.from_uci(move_str)}
        except ValueError:
            print(f"Error parsing UCI move: {move_str}")
            return {"error": RetryReason.INVALID_UCI_FORMAT}

    def terminate_game(self, result, termination_reason):
        """Set game result and termination reason."""
        self.game.headers["Result"] = result
        self.game.headers["Termination"] = termination_reason

    def resign(self, player_color, reason):
        """Handle player resignation."""
        if player_color == chess.WHITE:
            self.terminate_game("0-1", f"White resigned ({reason})")
        else:
            self.terminate_game("1-0", f"Black resigned ({reason})")

    def get_player_move(self, player, max_retries=1):
        """Get a move from the specified player with retry logic."""

        # Add current board state to the conversation
        messages = (
            self.white_messages if player is self.white_player else self.black_messages
        )
        messages.append({"role": "user", "content": build_user_prompt(self.board)})

        for _ in range(1 + max_retries):
            # Ask the player for its move
            response = player.chat(messages)
            print(f"- {player.name()}: {response}")
            if response:
                messages.append({"role": "assistant", "content": response})
            else:
                print("⚠️ Error on this move: RetryReason.EMPTY_RESPONSE")
                break

            # Extract the move from the response
            result = self.extract_move_from_response(response)
            if "move" in result:
                move = result["move"]
                # Check if move is legal
                if move == "resign" or move in self.board.legal_moves:
                    return {"move": move}
                else:
                    error_reason = RetryReason.ILLEGAL_MOVE
            else:
                error_reason = result["error"]
            print(f"⚠️ Error on this move: {error_reason}")
            # Add error reason to the conversation
            messages.append({"role": "user", "content": error_reason.value})

        # All attempts failed
        return {"error": error_reason}

    def determine_game_result(self):
        """Determine the final result if the game ended naturally."""
        if self.board.is_game_over():
            result = self.board.result(claim_draw=True)
            self.game.headers["Result"] = result
            if self.board.is_checkmate():
                self.game.headers["Termination"] = "checkmate"
            elif self.board.is_stalemate():
                self.game.headers["Termination"] = "stalemate"
            elif self.board.can_claim_fifty_moves():
                self.game.headers["Termination"] = "50-move rule"
            elif self.board.can_claim_threefold_repetition():
                self.game.headers["Termination"] = "threefold repetition"
            else:
                self.game.headers["Termination"] = "draw"
        else:
            # Game ended due to move limit
            self.game.headers["Result"] = "1/2-1/2"
            self.game.headers["Termination"] = "exceeded moves limit"

    def save_pgn(self):
        """Save the game to a PGN file."""
        pgn_io = io.StringIO()
        exporter = chess.pgn.FileExporter(pgn_io)
        self.game.accept(exporter)
        pgn_text = pgn_io.getvalue()

        safe_white = self.white_player.name().replace("/", "-")
        safe_black = self.black_player.name().replace("/", "-")
        filename = f"{time.time_ns()}_{safe_white}_vs_{safe_black}.pgn"
        pgn_path = os.path.join(self.pgn_dir, filename)

        with open(pgn_path, "w", encoding="utf-8") as f:
            f.write(pgn_text)

    def play(self, max_retries=1):
        """Play the complete game and return the result."""
        while (
            not self.board.is_game_over()
            and self.board.fullmove_number <= self.max_moves
        ):
            # Get next player
            player = (
                self.white_player
                if self.board.turn == chess.WHITE
                else self.black_player
            )

            # Get move from player
            result = self.get_player_move(player, max_retries)

            if "error" in result:  # player failed to provide a valid move after retries
                self.resign(self.board.turn, "No valid move provided")
                break

            move = result["move"]
            if move == "resign":
                self.resign(self.board.turn, "Resigned")
                break

            # Make move
            self.board.push(move)
            self.node = self.node.add_variation(move)

        # Determine final result if not set yet
        if "Result" not in self.game.headers:
            self.determine_game_result()

        # Print and save results
        print(f"Game result: {self.game.headers['Result']}")
        print(f"Termination reason: {self.game.headers['Termination']}")
        self.save_pgn()

        return self.game.headers["Result"]
