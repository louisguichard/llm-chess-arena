"""Prompts for the LLM."""

import chess
from enum import Enum


class RetryReason(Enum):
    """Enumeration of retry reasons with custom messages."""

    EMPTY_RESPONSE = (
        "Your response was empty. Return ONLY one JSON object matching the schema."
    )
    INVALID_JSON = "Your output was not valid JSON or contained extra text. Return ONLY one JSON object matching the schema (no code fences, no extra text)."
    ILLEGAL_MOVE = "Your move is illegal in the current position. Make sure you are generating a valid move."
    MISSING_MOVE_KEY = "Your JSON is missing the required 'move' key."
    MISSING_RATIONALE_KEY = "Your JSON is missing the required 'rationale' key."
    MISSING_REASONING_KEY = "Your JSON is missing the required 'reasoning' key."
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


SYSTEM_PROMPT = """You are a professional chess player. Your goal is to win the game by making the best possible moves.

Follow these steps to decide on your move:
1.  **Analyze the board**: Review the current game state, threats, and opportunities.
2.  **Think step-by-step**: Use the `reasoning` field to explain your thought process. Document your analysis, candidate moves, and why you are choosing your final move. Double-check that your chosen move in the `move` field is legal in the current board position. This is your internal monologue and should be detailed.
3.  **Summarize your rationale**: In the `rationale` field, provide a brief, one or two-sentence summary of your reason for the move. This will be shown in the UI.

Return your final decision as a SINGLE JSON object with three keys, in this exact order: `reasoning`, `rationale`, `move`.

Example response (reasoning could be a lot longer):
{
  "reasoning": "The opponent's last move, Nf6, develops a piece and controls the center. My main options are to challenge the center with d4, develop my own knight with Nc3, or make a quieter move like g3. Pushing the d-pawn seems most aggressive and best. It will attack the center and open lines for my pieces. I've double-checked, and d2d4 is a legal move.",
  "rationale": "I'm pushing my d-pawn to challenge the opponent's control of the center and open up lines for my other pieces.",
  "move": "d2d4"
}

Hard rules:
- Output ONLY the JSON object. No code fences, no text before or after the JSON.
- The `move` MUST be a legal move in the current position.
- If you are checkmated: `{"reasoning": "...", "rationale": "...", "move": "resign"}`
- If the game is a stalemate: `{"reasoning": "...", "rationale": "...", "move": "pass"}`"""


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
        "Task: Choose ONE legal move and return ONLY the JSON, per the system prompt."
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
                f"The move '{attempted}' is illegal and cannot be played in the current position. "
                "Please analyze the board again and provide a legal move in UCI format. "
                "Return ONLY the JSON object."
            )
        return (
            "Your previous move was illegal. Please choose a legal move and return it "
            "in the JSON format."
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
            "with keys 'reasoning', 'rationale' and 'move' (no code fences, no text before/after)."
        )

    if reason == RetryReason.MISSING_MOVE_KEY:
        return "Your JSON is missing the required 'move' key. Return a JSON object with 'reasoning', 'rationale', and 'move' keys."

    if reason == RetryReason.MISSING_RATIONALE_KEY:
        return "Your JSON is missing the required 'rationale' key. Return a JSON object with 'reasoning', 'rationale', and 'move' keys."

    if reason == RetryReason.MISSING_REASONING_KEY:
        return "Your JSON is missing the required 'reasoning' key. Return a JSON object with 'reasoning', 'rationale', and 'move' keys."

    if reason == RetryReason.EMPTY_RESPONSE:
        return "Your response was empty. Return ONLY a single JSON object matching the schema (no extra text)."
