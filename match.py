"""Play a chess game."""

import io
import os
import time
import json

import chess
import chess.pgn
from prompts import SYSTEM_PROMPT, build_user_prompt, build_retry_prompt

PGN_DIR = "games"
if not os.path.isdir(PGN_DIR):
    os.makedirs(PGN_DIR, exist_ok=True)


def play_game(white, black, round_no=1, max_moves=200):
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

    while not board.is_game_over() and board.fullmove_number <= max_moves:
        player = white if board.turn == chess.WHITE else black

        response = player.get_next_move(
            SYSTEM_PROMPT,
            build_user_prompt(board),
        )
        print(f"- {player.name()}: {response}")
        move = extract_move_from_response(response)

        if not move:
            # Give a second chance
            response = player.get_next_move(
                SYSTEM_PROMPT,
                build_retry_prompt(board, "empty or missing response"),
            )
            move = extract_move_from_response(response)

        # If still nothing, resign
        if not move:
            if board.turn == chess.WHITE:
                game.headers["Result"] = "0-1"
                game.headers["Termination"] = "No valid move"
            else:
                game.headers["Result"] = "1-0"
                game.headers["Termination"] = "No valid move"
            break

        # Allow explicit resignation
        if move == "resign":
            if board.turn == chess.WHITE:
                game.headers["Result"] = "0-1"
                game.headers["Termination"] = "White resigned"
            else:
                game.headers["Result"] = "1-0"
                game.headers["Termination"] = "Black resigned"
            break

        # If the move is not legal, ask the model to retry
        if move not in board.legal_moves:
            response = player.get_next_move(
                SYSTEM_PROMPT,
                build_retry_prompt(
                    board,
                    "invalid format or illegal move; provide exactly one legal UCI move",
                ),
            )
            move = extract_move_from_response(response)

            # If still nothing, resign
            if not move:
                if board.turn == chess.WHITE:
                    game.headers["Result"] = "0-1"
                    game.headers["Termination"] = "White resigned (no move)"
                else:
                    game.headers["Result"] = "1-0"
                    game.headers["Termination"] = "Black resigned (no move)"
                break

            if move == "resign":
                if board.turn == chess.WHITE:
                    game.headers["Result"] = "0-1"
                    game.headers["Termination"] = "White resigned"
                else:
                    game.headers["Result"] = "1-0"
                    game.headers["Termination"] = "Black resigned"
                break

        # If after retry we still don't have a legal move, resign
        if move not in board.legal_moves:
            if board.turn == chess.WHITE:
                game.headers["Result"] = "0-1"
                game.headers["Termination"] = "Illegal move"
            else:
                game.headers["Result"] = "1-0"
                game.headers["Termination"] = "Illegal move"
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

    print(f"Game result: {game.headers['Result']}")
    print(f"Termination reason: {game.headers['Termination']}")

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


def extract_move_from_response(response):
    """Extract the move from the response."""
    response = json.loads(response.strip())
    # TODO: add retry in case of invalid json
    move = response["move"].strip()
    if move == "resign":
        return move
    try:
        return chess.Move.from_uci(move)
    except ValueError:
        return None
