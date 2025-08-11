"""Prompts for the LLM."""

import chess
from enum import Enum


class RetryReason(Enum):
    """Enumeration of retry reasons with custom messages."""

    EMPTY_RESPONSE = (
        "Your response was empty. Return ONLY one JSON object matching the schema."
    )
    INVALID_JSON = "Your output was not valid JSON or contained extra text. Return ONLY one JSON object matching the schema (no code fences, no extra text)."
    ILLEGAL_MOVE = (
        "Your move is illegal in the current position. Return a legal UCI move."
    )
    MISSING_MOVE_KEY = "Your JSON is missing the required 'move' key. Return EXACTLY one JSON object with keys 'rationale' and 'move'."
    INVALID_UCI_FORMAT = "The 'move' value is not valid UCI. It must match ^[a-h][1-8][a-h][1-8][qrbn]?$."


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


def last_uci_from_board(board):
    """Return the last UCI move or '-' if no moves were played yet."""
    if not board.move_stack:
        return "-"
    try:
        return board.move_stack[-1].uci()
    except Exception:
        return "-"


SYSTEM_PROMPT = """You are a professional chess player in a turn-based chat.

Return exactly ONE move to PLAY now, as a SINGLE JSON object:
{
  "rationale": string,  // explain your move
  "move": string        // one legal UCI move, e.g. "e2e4","e7e8q"
}

Hard rules:
- Output ONLY the JSON object. No code fences, no text before/after.
- "move" MUST match ^[a-h][1-8][a-h][1-8][qrbn]?$ and MUST be LEGAL in the latest Turn Context.
- Make sure that the move you are proposing is legal.
- Promotion: use "q" unless another promotion is clearly better and legal.
- If checkmated: {"rationale":"…","move":"resign"}
- If stalemate:  {"rationale":"…","move":"pass"}"""


def build_user_prompt(board):
    """Return the user prompt with clear, compact board context."""
    color_str = "White" if board.turn == chess.WHITE else "Black"
    last_uci = last_uci_from_board(board)
    ascii_board_str = board_to_ascii(board)

    def piece_lists(board):
        pieces_positions = {}

        for position, piece in board.piece_map().items():
            piece_symbol = piece.symbol()
            if piece_symbol not in pieces_positions:
                pieces_positions[piece_symbol] = []
            position_name = chess.square_name(position)
            pieces_positions[piece_symbol].append(position_name)

        white_description = (
            " ; ".join(
                f"{symbol} {' '.join(sorted(pieces_positions.get(symbol, [])))}"
                for symbol in "KQRBNP"
                if pieces_positions.get(symbol)
            )
            or "-"
        )

        black_description = (
            " ; ".join(
                f"{symbol} {' '.join(sorted(pieces_positions.get(symbol, [])))}"
                for symbol in "kqrbnp"
                if pieces_positions.get(symbol)
            )
            or "-"
        )

        return white_description, black_description

    white_pieces_str, black_pieces_str = piece_lists(board)

    return (
        f"You play {color_str} and it's your turn.\n"
        f"Opponent just played {last_uci}.\n"
        f"White pieces: {white_pieces_str}\n"
        f"Black pieces: {black_pieces_str}\n"
        f"ASCII board (ranks 8→1, files a→h):\n{ascii_board_str}\n\n"
        "Task: choose ONE legal move now and return ONLY the JSON per the schema."
    )


def build_retry_message(reason, attempted=None):
    """Return a detailed retry instruction for the assistant.

    The returned string is meant to be appended as a new user message to
    steer the next attempt toward a valid, legal, and well-formed answer.
    """
    pattern = "^[a-h][1-8][a-h][1-8][qrbn]?$"

    if reason == RetryReason.ILLEGAL_MOVE:
        if attempted:
            return (
                f"The move '{attempted}' you made is illegal and cannot be played. "
                f"Please respond with a move that is legal and in the UCI chess format "
                f"(e.g., 'e2e4', 'e7e8q'). Return ONLY the JSON object."
            )
        return (
            "Your move is illegal in the current position. Please respond with a legal "
            "UCI move (e.g., 'e2e4', 'e7e8q'). Return ONLY the JSON object."
        )

    if reason == RetryReason.INVALID_UCI_FORMAT:
        if attempted:
            return (
                f"The move '{attempted}' is not valid UCI. It must match {pattern}. "
                "Use lowercase files and ranks; include a promotion piece 'q','r','b','n' when promoting "
                "(prefer 'q' unless clearly better). Examples: 'e2e4', 'e7e8q'. "
                "Return ONLY the JSON object."
            )
        return (
            f"The 'move' value is not valid UCI. It must match {pattern}. "
            "Examples: 'e2e4', 'e7e8q'. Return ONLY the JSON object."
        )

    if reason == RetryReason.INVALID_JSON:
        return (
            "Your output was not valid JSON or contained extra text. Return ONLY a single JSON object "
            "with keys 'rationale' and 'move' (no code fences, no text before/after)."
        )

    if reason == RetryReason.MISSING_MOVE_KEY:
        return (
            "Your JSON is missing the required 'move' key. Return EXACTLY one JSON object with keys "
            "'rationale' and 'move'."
        )

    if reason == RetryReason.EMPTY_RESPONSE:
        return "Your response was empty. Return ONLY a single JSON object matching the schema (no extra text)."
