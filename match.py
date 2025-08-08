"""Play a chess game."""

import io
import os
import time

import chess
import chess.pgn

SYSTEM_PROMPT = """You are a professional chess player. After careful consideration, announce your next move by ending your response with "Move: your_move" where your_move is your move in UCI notation (e.g., e2e4, e7e5, e1g1, or e7e8q). Do not add anything after announcing your move: no punctuation, no explanation, nothing else."""
PGN_DIR = "games"
if not os.path.isdir(PGN_DIR):
    os.makedirs(PGN_DIR, exist_ok=True)


def play_game(white, black, round_no=1, max_fullmoves=200):
    """Play a single game and return result.

    Result can be either:
    - "1-0": White wins
    - "0-1": Black wins
    - "1/2-1/2": Draw
    """

    board = chess.Board()  # game state (pieces, turn, legal moves, result, etc.)
    game = chess.pgn.Game()  # PGN representation
    node = game

    # PGN headers add useful metadata to the saved game
    game.headers["Event"] = "LLM Chess Arena"
    game.headers["Site"] = "Local"
    game.headers["Round"] = str(round_no)
    game.headers["White"] = white.name()
    game.headers["Black"] = black.name()
    game.headers["Date"] = time.strftime("%Y.%m.%d")

    while not board.is_game_over() and board.fullmove_number <= max_fullmoves:
        actor = white if board.turn == chess.WHITE else black

        proposal = actor.get_next_move(
            SYSTEM_PROMPT,
            f"Position (FEN): {board.fen()}\nPlease end your response with 'Move: your_move' where your_move is your move in UCI notation (e.g., e2e4, e7e5, e1g1, or e7e8q).",
        )
        # If the actor can't provide a move, we treat it as a resignation
        if not proposal:
            # Resign if no move returned
            if board.turn == chess.WHITE:
                game.headers["Result"] = "0-1"
                game.headers["Termination"] = "White resigned (no move)"
            else:
                game.headers["Result"] = "1-0"
                game.headers["Termination"] = "Black resigned (no move)"
            break

        try:
            # Convert the proposed UCI string into a chess.Move
            move = chess.Move.from_uci(proposal)
        except Exception:
            move = None

        if move is None or move not in board.legal_moves:
            # Illegal move means resignation for the side to move
            if board.turn == chess.WHITE:
                game.headers["Result"] = "0-1"
                game.headers["Termination"] = (
                    f"White resigned (illegal move: {proposal})"
                )
            else:
                game.headers["Result"] = "1-0"
                game.headers["Termination"] = (
                    f"Black resigned (illegal move: {proposal})"
                )
            break

        board.push(move)
        node = node.add_variation(move)

    # If result not set yet, derive it from board state or move limit
    if game.headers.get("Result", "*") == "*":
        if board.is_game_over():
            result = board.result(claim_draw=True)
            game.headers["Result"] = result
            if board.is_checkmate():
                game.headers["Termination"] = "checkmate"
            elif board.is_stalemate():
                game.headers["Termination"] = "stalemate"
            elif board.can_claim_fifty_moves():
                game.headers["Termination"] = "50-move rule"
            elif board.can_claim_threefold_repetition():
                game.headers["Termination"] = "threefold repetition"
            else:
                game.headers["Termination"] = "draw"
        else:
            game.headers["Result"] = "1/2-1/2"
            game.headers["Termination"] = "adjudication: move limit"

    # Save PGN
    pgn_io = io.StringIO()
    exporter = chess.pgn.FileExporter(pgn_io)
    game.accept(exporter)
    pgn_text = pgn_io.getvalue()

    safe_white = white.name().replace("/", "-")
    safe_black = black.name().replace("/", "-")
    filename = f"{time.time_ns()}_{safe_white}_vs_{safe_black}.pgn"
    pgn_path = os.path.join(PGN_DIR, filename)
    with open(pgn_path, "w", encoding="utf-8") as f:
        f.write(pgn_text)

    return game.headers["Result"]
