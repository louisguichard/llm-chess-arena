"""Play a chess game."""

import io
import time
import json

import chess
import chess.pgn
from prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
    RetryReason,
    build_retry_message,
)
from gcp import write_file_to_gcs, write_json_to_gcs
from logger import log


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

        # Set up PGN headers
        self.game.headers["Event"] = "LLM Chess Arena"
        self.game.headers["Site"] = "Local"
        self.game.headers["White"] = self.white_player.name()
        self.game.headers["Black"] = self.black_player.name()
        self.game.headers["Date"] = time.strftime("%Y.%m.%d")

        # Create one chat conversation per player for the whole game
        self.white_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.black_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.is_over = False

        # Game data to be saved as JSON
        self.moves_log = []

        # Track game statistics
        self.white_time = 0.0
        self.black_time = 0.0
        self.white_cost = 0.0
        self.black_cost = 0.0

    def extract_move_from_response(self, response):
        """Extract the move from the response.

        Returns:
            dict: Either {"move": chess.Move or "resign", "rationale": string, "reasoning": string} for success
                or {"error": RetryReason} for failure
        """
        if not response:
            return {"error": RetryReason.EMPTY_RESPONSE}

        try:
            parsed_response = json.loads(response.strip())
        except json.JSONDecodeError:
            log.warning(f"Error parsing JSON: {response}")
            return {"error": RetryReason.INVALID_JSON}

        if "reasoning" not in parsed_response:
            log.warning(f"Missing 'reasoning' key in response: {parsed_response}")
            return {"error": RetryReason.MISSING_REASONING_KEY}
        if "rationale" not in parsed_response:
            log.warning(f"Missing 'rationale' key in response: {parsed_response}")
            return {"error": RetryReason.MISSING_RATIONALE_KEY}
        if "move" not in parsed_response:
            log.warning(f"Missing 'move' key in response: {parsed_response}")
            return {"error": RetryReason.MISSING_MOVE_KEY}

        try:
            move_str = parsed_response["move"].strip()
            rationale = parsed_response.get("rationale", "No rationale provided.")
            reasoning = parsed_response.get("reasoning", "No reasoning provided.")
            if move_str == "resign" or move_str == "pass":
                return {
                    "move": move_str,
                    "rationale": rationale,
                    "reasoning": reasoning,
                }
            return {
                "move": chess.Move.from_uci(move_str),
                "move_uci": move_str,
                "rationale": rationale,
                "reasoning": reasoning,
            }
        except ValueError:
            log.warning(f"Error parsing UCI move: {move_str}")
            return {"error": RetryReason.INVALID_UCI_FORMAT, "attempted": move_str}

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

    def get_player_move(self, player, max_retries=2):
        """Get a move from the specified player with retry logic."""

        # Add current board state to the conversation
        messages = (
            self.white_messages if player is self.white_player else self.black_messages
        )
        messages.append({"role": "user", "content": build_user_prompt(self.board)})

        for i in range(1 + max_retries):
            # Ask the player for its move
            log.debug(
                f"Attempt {i + 1}/{1 + max_retries}: Getting move from {player.name()}..."
            )
            log.debug(
                f"Prompt to {player.name()} (role=user):\n{messages[-1]['content']}"
            )
            response_data = player.chat(messages)
            log.debug(
                f"Attempt {i + 1}/{1 + max_retries}: Received response for {player.name()}."
            )
            if not response_data:
                # Handle case where chat returns None
                error_reason = RetryReason.EMPTY_RESPONSE
                messages.append(
                    {
                        "role": "user",
                        "content": build_user_prompt(self.board)
                        + "\n\n"
                        + build_retry_message(error_reason),
                    }
                )
                continue

            completion = response_data["completion"]
            cost = response_data.get("cost", 0)
            latency = response_data.get("latency", 0)

            response = completion.choices[0].message.content
            response_single_line = response.replace("\n", " ")
            log.info(f"- {player.name()}: {response_single_line}")
            if response:
                messages.append({"role": "assistant", "content": response})
            else:
                log.warning(f"Messages: {messages}")
                log.warning(f"Completion: {completion}")
                messages.append({"role": "assistant", "content": ""})
                error_reason = RetryReason.EMPTY_RESPONSE

            # Extract the move from the response
            result = self.extract_move_from_response(response)
            if "move" in result:
                move = result["move"]
                # Check if move is legal
                if (
                    move == "resign"
                    or (move == "pass" and self.board.is_stalemate())
                    or move in self.board.legal_moves
                ):
                    return {
                        "move": move,
                        "rationale": result.get("rationale"),
                        "reasoning": result.get("reasoning"),
                        "cost": cost,
                        "latency": latency,
                    }
                else:
                    error_reason = RetryReason.ILLEGAL_MOVE
                    attempted = result.get("move_uci")
            else:
                error_reason = result["error"]
                attempted = result.get("attempted")
            log.warning(f"⚠️ Error on this move: {error_reason}")
            # Add error reason to the conversation
            messages.append(
                {
                    "role": "user",
                    "content": build_user_prompt(self.board)
                    + "\n\n"
                    + build_retry_message(error_reason, attempted),
                }
            )

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

    def save_game(self):
        """Save game to PGN and JSON."""
        timestamp = time.time_ns()
        safe_white = self.white_player.name().replace("/", "-")
        safe_black = self.black_player.name().replace("/", "-")
        base_filename = f"{timestamp}_{safe_white}_vs_{safe_black}"

        # Save PGN
        pgn_filename = f"{base_filename}.pgn"
        pgn_blob_name = f"{self.pgn_dir}/{pgn_filename}"
        pgn_io = io.StringIO()
        exporter = chess.pgn.FileExporter(pgn_io)
        self.game.accept(exporter)
        pgn_text = pgn_io.getvalue()
        write_file_to_gcs(
            pgn_blob_name, pgn_text, content_type="application/x-chess-pgn"
        )

        # Save JSON data
        game_data = {
            "white_player": self.white_player.name(),
            "black_player": self.black_player.name(),
            "result": self.game.headers.get("Result"),
            "termination": self.game.headers.get("Termination"),
            "moves": self.moves_log,
            "stats": {
                "white_time": self.white_time,
                "black_time": self.black_time,
                "white_cost": self.white_cost,
                "black_cost": self.black_cost,
                "total_moves": len(self.board.move_stack),
            },
        }
        json_filename = f"{base_filename}.json"
        json_blob_name = f"{self.pgn_dir}/{json_filename}"
        write_json_to_gcs(json_blob_name, game_data)

    def get_current_player(self):
        """Return the player whose turn it is."""
        return (
            self.white_player if self.board.turn == chess.WHITE else self.black_player
        )

    def play_next_move(self, max_retries=2):
        """Play one move and return the result.

        Returns a dictionary with move info, or None if game is over.
        """
        if (
            self.is_over
            or self.board.is_game_over()
            or self.board.fullmove_number > self.max_moves
        ):
            self.is_over = True
            if "Result" not in self.game.headers:
                self.determine_game_result()
            self.save_game()
            return None

        player = self.get_current_player()
        result = self.get_player_move(player, max_retries)

        if "error" in result:
            self.resign(
                self.board.turn, f"No valid move provided ({result['error'].value})"
            )
            self.is_over = True
            self.save_game()
            return {"status": "error", "message": "Player failed to move."}

        # Extract all data from the result
        move = result["move"]
        rationale = result.get("rationale", "No rationale provided.")
        reasoning = result.get("reasoning", "No reasoning provided.")
        cost = result.get("cost", 0)
        latency = result.get("latency", 0)

        # Log move data for JSON export
        move_log_entry = {
            "player": player.name(),
            "color": "White" if self.board.turn == chess.WHITE else "Black",
            "move_number": self.board.fullmove_number,
            "fen_before": self.board.fen(),
            "reasoning": reasoning,
            "rationale": rationale,
            "cost": cost,
            "latency": latency,
        }
        if isinstance(move, chess.Move):
            move_log_entry["move"] = {"uci": move.uci(), "san": self.board.san(move)}
        else:
            move_log_entry["move"] = move
        self.moves_log.append(move_log_entry)

        # Track statistics for the current move, regardless of what the move is
        if self.board.turn == chess.WHITE:
            self.white_time += latency
            self.white_cost += cost
        else:
            self.black_time += latency
            self.black_cost += cost

        if move == "resign":
            self.resign(self.board.turn, "Resigned")
            self.is_over = True
            self.save_game()
            return {"status": "resigned"}

        if move == "pass":
            # Stalemate acknowledgment without pushing a move
            self.is_over = True
            self.determine_game_result()
            self.save_game()
            return {
                "status": "success",
                "move_san": "pass",
                "fen": self.board.fen(),
                "is_over": True,
                "result": self.game.headers.get("Result"),
                "rationale": rationale,
                "reasoning": reasoning,
                "cost": cost,
                "latency": latency,
            }

        # If it is a standard move, we can make it
        san_move = self.board.san(move)
        self.board.push(move)
        self.node = self.node.add_variation(move)

        # Check for game over condition after the move
        if self.board.is_game_over(claim_draw=True):
            self.is_over = True
            self.determine_game_result()
            self.save_game()

        return {
            "status": "success",
            "move_san": san_move,
            "fen": self.board.fen(),
            "is_over": self.is_over,
            "result": self.game.headers.get("Result"),
            "rationale": rationale,
            "reasoning": reasoning,
            "cost": cost,
            "latency": latency,
        }

    def play(self, max_retries=2):
        """Play the complete game and return the result and statistics."""
        while not self.is_over:
            move_result = self.play_next_move(max_retries)
            if move_result is None:  # Game ended
                break

        # Calculate moves: total moves divided by 2, white gets the extra if odd
        total_moves = len(self.board.move_stack)
        white_moves = (total_moves + 1) // 2  # White moves first, so gets extra if odd
        black_moves = total_moves // 2

        # Print and save results
        log.info(f"Game result: {self.game.headers['Result']}")
        log.info(f"Termination reason: {self.game.headers['Termination']}")
        log.debug(
            f"Game stats: W({white_moves}m, {self.white_time:.1f}s, ${self.white_cost:.4f}) vs B({black_moves}m, {self.black_time:.1f}s, ${self.black_cost:.4f})"
        )

        return {
            "result": self.game.headers["Result"],
            "white_moves": white_moves,
            "black_moves": black_moves,
            "white_time": self.white_time,
            "black_time": self.black_time,
            "white_cost": self.white_cost,
            "black_cost": self.black_cost,
        }
