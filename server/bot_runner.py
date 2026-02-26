"""
Bot Runner — executes a match between two bots.

Each bot is a Python script that communicates via stdin/stdout:
  - Receives: one line of JSON with the board state
  - Sends:    one line with "row col" (e.g. "3 4")
"""

import subprocess
import sys
import os
import time
import json
import threading

from game_engine import Board, Player, MAX_MOVES

MOVE_TIMEOUT = 2  # seconds per move
MAX_BOT_FILE_SIZE = 100 * 1024  # 100 KB


class BotProcess:
    """Wraps a subprocess running a bot script."""

    def __init__(self, name: str, script_path: str):
        self.name = name
        self.script_path = script_path
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-u", self.script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )

    def send_state(self, state_json: str):
        """Send a line of JSON to the bot's stdin."""
        self.process.stdin.write(state_json + "\n")
        self.process.stdin.flush()

    def read_move(self, timeout: float = MOVE_TIMEOUT) -> str:
        """Read one line from the bot's stdout, with a timeout.
        Uses threading for Windows compatibility (selectors doesn't
        work with subprocess pipes on Windows)."""
        result = [None]

        def _read():
            try:
                result[0] = self.process.stdout.readline().strip()
            except Exception:
                result[0] = None

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        reader.join(timeout=timeout)

        if reader.is_alive():
            return None  # timeout
        return result[0] if result[0] else None

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def is_alive(self):
        return self.process and self.process.poll() is None


def parse_move(move_str: str):
    """Parse 'row col' string into (int, int) or None if invalid."""
    if not move_str:
        return None
    parts = move_str.strip().split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def run_match(team1_name: str, team1_path: str, team2_name: str, team2_path: str, move_timeout: float = MOVE_TIMEOUT):
    """
    Run a full match between two bots.

    Returns:
        dict with keys:
            winner:      team name (str) or None for draw, or "DQ:<team>" for disqualification
            result_desc: human-readable description
            moves:       list of dicts recording every move for replay
    """
    board = Board()
    bot1 = BotProcess(team1_name, team1_path)
    bot2 = BotProcess(team2_name, team2_path)

    moves = []  # [{move_number, team, player, row, col, board_after}, ...]

    # Start both bots
    try:
        bot1.start()
    except Exception as e:
        return {
            "winner": f"DQ:{team1_name}",
            "result_desc": f"{team1_name} bot failed to start: {e}",
            "moves": moves,
        }

    try:
        bot2.start()
    except Exception as e:
        bot1.stop()
        return {
            "winner": f"DQ:{team2_name}",
            "result_desc": f"{team2_name} bot failed to start: {e}",
            "moves": moves,
        }

    result = None

    try:
        for move_number in range(MAX_MOVES):
            if move_number % 2 == 0:
                current_player = Player.RED
                current_bot = bot1
                current_name = team1_name
            else:
                current_player = Player.BLUE
                current_bot = bot2
                current_name = team2_name

            # Check if bot is still running
            if not current_bot.is_alive():
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} bot crashed (process exited)",
                    "moves": moves,
                }
                break

            # Send board state to current bot
            state_json = board.to_json(current_player, move_number)
            try:
                current_bot.send_state(state_json)
            except (BrokenPipeError, OSError):
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} bot crashed (broken pipe)",
                    "moves": moves,
                }
                break

            # Read move from bot
            move_str = current_bot.read_move(move_timeout)
            if move_str is None:
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} timed out (>{move_timeout}s)",
                    "moves": moves,
                }
                break

            # Parse and validate move
            parsed = parse_move(move_str)
            if parsed is None:
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} sent invalid output: '{move_str}'",
                    "moves": moves,
                }
                break

            row, col = parsed

            # Apply move
            if not board.make_move(row, col, current_player):
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} made an invalid move: ({row}, {col})",
                    "moves": moves,
                }
                break

            # Record move for replay
            moves.append(
                {
                    "move_number": move_number,
                    "team": current_name,
                    "player": int(current_player),
                    "row": row,
                    "col": col,
                    "board_after": board.snapshot(),
                }
            )

            # Check win
            if board.check_win(move_number, current_player):
                result = {
                    "winner": current_name,
                    "result_desc": f"{current_name} wins by eliminating all opponent pieces! (move {move_number + 1})",
                    "moves": moves,
                }
                break

        # If we exhausted all moves without a result
        if result is None:
            result = {
                "winner": None,
                "result_desc": f"Draw — game reached {MAX_MOVES} moves without a winner",
                "moves": moves,
            }

    finally:
        bot1.stop()
        bot2.stop()

    return result


if __name__ == "__main__":
    # Quick test: run a match between two bots passed as command-line args
    if len(sys.argv) != 5:
        print("Usage: python bot_runner.py <team1_name> <team1_path> <team2_name> <team2_path>")
        sys.exit(1)

    result = run_match(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    print(f"\nResult: {result['result_desc']}")
    print(f"Winner: {result['winner']}")
    print(f"Total moves: {len(result['moves'])}")
