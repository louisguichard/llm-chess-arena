"""Prompts for the LLM."""

import chess
from enum import Enum


class RetryReason(Enum):
    """Enumeration of retry reasons with custom messages."""

    EMPTY_RESPONSE = "Your response was empty. Please answer with a JSON object following the schema."
    INVALID_JSON = "The JSON you provided is invalid or you wrote outside of it. Please answer with only a JSON object following the schema."
    ILLEGAL_MOVE = "Your move is illegal. Please provide a legal UCI move."
    MISSING_MOVE_KEY = "The JSON you provided is missing the 'move' key. Please answer with only a JSON object following the schema."
    INVALID_UCI_FORMAT = "Your move isn't in UCI format. Please provide your move in UCI format (e.g., 'e2e4' or 'e7e8q')."


def board_to_ascii(board):
    """Return a simple ASCII representation of the board.

    Uppercase letters represent White pieces, lowercase represent Black.
    Dots represent empty squares. Ranks are shown from 8 down to 1.
    """
    piece_to_char = {
        chess.PAWN: "p",
        chess.KNIGHT: "n",
        chess.BISHOP: "b",
        chess.ROOK: "r",
        chess.QUEEN: "q",
        chess.KING: "k",
    }

    rows = []
    for rank in range(7, -1, -1):  # 7 -> 0 corresponds to ranks 8 -> 1
        row_chars = []
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            if piece is None:
                row_chars.append(".")
            else:
                char = piece_to_char[piece.piece_type]
                row_chars.append(char.upper() if piece.color == chess.WHITE else char)
        rows.append(" ".join(row_chars))

    # Optionally add file labels at the bottom for readability
    file_labels = "a b c d e f g h"
    rank_labels_rows = []
    for idx, row in enumerate(rows):
        rank_label = str(8 - idx)
        rank_labels_rows.append(f"{rank_label}  {row}")

    return "\n".join(rank_labels_rows + ["   " + file_labels])


def san_history_from_board(board):
    """Return the SAN move history for the current board position.

    This reconstructs the SAN strings from the move stack without mutating the
    original board.
    """
    if not board.move_stack:
        return ""

    temp = chess.Board()  # start from the initial position
    san_moves = []
    for move in board.move_stack:
        san_moves.append(temp.san(move))
        temp.push(move)
    return " ".join(san_moves)


SYSTEM_PROMPT = """You are a professional chess player. Choose your next move by replying with a single JSON object.

Schema (all keys required):
{
  "rationale": string,  // concise explanation
  "move": string        // exactly one legal move in UCI, e.g., "e2e4", "e7e8q"
}

Rules:
- Output exactly one move.
- If checkmated: {"rationale":"...", "move":"resign"}
- If stalemate:  {"rationale":"...", "move":"pass"}
- No code fences, no trailing text after the JSON."""


def build_user_prompt(board):
    """Return the user prompt including FEN, SAN history and ASCII board."""
    san_history_str = san_history_from_board(board)
    ascii_board_str = board_to_ascii(board)
    return (
        f"FEN: {board.fen()}\n"
        f"Game so far (SAN): {san_history_str}\n"
        f"ASCII board (ranks 8→1, files a→h):\n{ascii_board_str}\n\n"
        "Respond as JSON following the schema."
    )
