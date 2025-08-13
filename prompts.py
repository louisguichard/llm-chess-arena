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
    """Return the last UCI move."""
    if not board.move_stack:
        return "(no move yet, game is just starting)"
    try:
        return board.move_stack[-1].uci()
    except Exception:
        return "-"


SYSTEM_PROMPT = """You are a professional chess player. Your goal is to win the game by making the best possible moves.

Follow these steps to decide on your move:
1.  Opponent’s last move: Identify what it changed. List immediate threats (checks, captures, mating nets, forks, discovered attacks), new weaknesses, and squares they now control.
2.  Generate candidates: Consider a few promising candidates (checks, captures, and forcing moves first), then strong positional options.
3.  Choose the best: Compare candidates with concrete lines as needed. Be explicit about the key variations that influence your choice.
4.  Safety and legality check:
    - If you are in check, your move MUST resolve the check.
    - Your move must be legal and must not leave your king in check.
    - Sliding pieces (bishop, rook, queen): for multi-square moves, verify EACH intermediate square on the path is empty; the destination must be empty or contain an opponent’s piece.
    - Pawns: forward moves require empty squares (including the intermediate square on a two-step from the starting rank); diagonal pawn moves must capture an opponent piece; en passant only if allowed by the last move; promotions must include a piece letter (prefer 'q' unless clearly worse).
    - Knights can jump; kings move one square; castling requires the path is clear, the king is not in check, and none of the squares the king passes through are attacked.
    - Confirm the exact UCI string and that the final move is legal. If a tempting idea fails these checks, switch to a legal alternative.

Output format:
- Return your decision as ONE JSON object with keys in this exact order: `reasoning`, `rationale`, `move`.
- `reasoning`: Your detailed internal analysis (step-by-step). Include candidate moves considered, concrete lines and detailed checks for legality.
- `rationale`: A brief 1–2 sentence summary of why the chosen move is best.
- `move`: Exactly one UCI move (e.g., "e2e4", "e7e8q"), or "resign" if checkmated, or "pass" only if the position is a stalemate.

Example response:
{
  "reasoning": "Opponent just played Nf6, developing and increasing control over e4 and g4. Threat scan: no direct threat against my king now, but ...Nxe4 could become possible if I neglect the center; also ...Bb4+ might be annoying after Nc3. Candidate checks/captures/forcing: 1) d2d4 (strike the center), 2) c2c4 (space, but concedes d4), 3) g1f3 (develop, defend e5/d4 squares), 4) c1g5 (? pin idea). First I consider c1g5 to pin the knight. Legality/path check for c1g5: squares d2, e3, f4 must be empty and g5 must be empty or hold an opponent piece; that is satisfied here, but after ...Ne4 and ...Bb4+ tactics my bishop may be misplaced and it doesn’t contest the center. Next I consider e2e4 to seize space; legality check: e2 to e4 is a two-step pawn push from the starting rank, so e3 must be empty and e4 must be empty. That is true here, but tactically ...Nxe4 might follow; safer is central tension first. Now d2d4: legality check: path is clear (d3 empty), destination d4 empty; it challenges the center, opens my c1-bishop, and blunts ...Nxe4 because d4xe5 gains time if Black captures. Calculate key lines: 1.d2d4 exd4 2.g1f3 Nc6 3.c2c3 with a solid center; or 1...Nxe4 2.d4e5 (illegal, correction: capture notation must be d4xe5; the UCI string is d4e5 if legal). Re-check: after 1.d2d4, ...Nxe4 loses a central pawn after d4xe5 with tempo; king safety is fine. Final legality check: d2d4 is legal and correctly formatted in UCI. Conclude d2d4.",
  "rationale": "Challenge the center, improve piece activity, and reduce Black’s ...Nxe4 ideas while keeping king safety.",
  "move": "d2d4"
}

Hard rules:
- Output ONLY the JSON object. No code fences, no text before or after the JSON.
- The `move` MUST be legal in the current position and in UCI format.
- If you are checkmated: {"reasoning": "...", "rationale": "...", "move": "resign"}
- If the game is a stalemate: {"reasoning": "...", "rationale": "...", "move": "pass"}
- Always consider the opponent’s last move and ensure your king is not in check."""


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


def build_retry_message(reason, attempted=None, is_in_check=None):
    """Return a detailed retry instruction for the assistant.

    The returned string is meant to be appended as a new user message to
    steer the next attempt toward a valid, legal, and well-formed answer.
    """
    pattern = "^[a-h][1-8][a-h][1-8][qrbn]?$"

    if reason == RetryReason.ILLEGAL_MOVE:
        check_message = ""
        if is_in_check:
            check_message = " Your king is currently in check. You must make a move to resolve the check."
        if attempted:
            return (
                f"The move '{attempted}' is illegal and cannot be played in the current position.{check_message} "
                "Please analyze the board again and provide a legal move in UCI format. "
                "Return ONLY the JSON object."
            )
        return (
            f"Your previous move was illegal.{check_message} Please choose a legal move and return it "
            "in the JSON format."
        )

    if reason == RetryReason.INVALID_UCI_FORMAT:
        if attempted:
            return f"""The move '{attempted}' is not valid UCI. It must match {pattern}. UCI is from-square + to-square (+ optional promotion piece). Do NOT include 'x', '+', '-' or piece letters. For captures, just write the to-square.

Bad examples and corrections:
- 'd4xe5' -> 'd4e5'
- 'Nf3' -> 'g1f3'
- 'Nb8d7' -> 'b8d7'
- 'e2-e4' -> 'e2e4'

Valid examples:
- 'e2e4', 'd4e5', 'g1f3', 'c1g5', 'e7e8q' (promotion).

Return ONLY the JSON object."""
        return f"""The 'move' value is not valid UCI. It must match {pattern}. UCI is from-square + to-square (+ optional promotion piece). Do NOT include 'x', '+', '-' or piece letters. For captures, just write the to-square.

Bad examples and corrections:
- 'd4xe5' -> 'd4e5'
- 'Nf3' -> 'g1f3'
- 'Nb8d7' -> 'b8d7'
- 'e2-e4' -> 'e2e4'

Valid examples:
- 'e2e4', 'd4e5', 'g1f3', 'c1g5', 'e7e8q' (promotion).

Return ONLY the JSON object."""

    if reason == RetryReason.INVALID_JSON:
        return """Your output was not valid JSON or contained extra text. Return ONLY one JSON object that starts with '{' and ends with '}', with absolutely no text before or after it. The JSON must have keys in this exact order: 'reasoning', 'rationale', 'move'. Do not use code fences or text before or after the JSON.

Valid output example:
{
  "reasoning": "Sorry for the invalid response before. I considered central control and king safety...",
  "rationale": "Develop and control the center while keeping the king safe.",
  "move": "e2e4"
}
"""

    if reason == RetryReason.MISSING_MOVE_KEY:
        return "Your JSON is missing the required 'move' key. Return a JSON object with 'reasoning', 'rationale', and 'move' keys."

    if reason == RetryReason.MISSING_RATIONALE_KEY:
        return "Your JSON is missing the required 'rationale' key. Return a JSON object with 'reasoning', 'rationale', and 'move' keys."

    if reason == RetryReason.MISSING_REASONING_KEY:
        return "Your JSON is missing the required 'reasoning' key. Return a JSON object with 'reasoning', 'rationale', and 'move' keys."

    if reason == RetryReason.EMPTY_RESPONSE:
        return "Your response was empty. Return ONLY a single JSON object matching the schema (no extra text)."
