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
import queue

from game_engine import Board, Player, MAX_MOVES

# Timers will now be passed dynamically, this is just a default fallback for backwards compat if needed.
MOVE_TIMEOUT = 2  # seconds per move


class BotProcess:
    """Wraps a subprocess running a bot script."""

    def __init__(self, name: str, script_path: str):
        self.name = name
        self.script_path = script_path
        self.process = None
        self.output_queue = None
        self.reader_thread = None

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-u", self.script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        self.output_queue = queue.Queue()
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

    def _reader_loop(self):
        try:
            for line in self.process.stdout:
                self.output_queue.put(line.strip())
        except Exception:
            pass
        finally:
            self.output_queue.put("EOF_SENTINEL")

    def send_state(self, state_json: str):
        """Send a line of JSON to the bot's stdin."""
        self.process.stdin.write(state_json + "\n")
        self.process.stdin.flush()

    def read_move(self, timeout: float = MOVE_TIMEOUT) -> str:
        """Read one line from the bot's stdout, with a timeout.
        Uses a threaded queue for Windows compatibility without leaking threads."""
        try:
            val = self.output_queue.get(timeout=timeout)
            if val == "EOF_SENTINEL":
                return None
            return val
        except queue.Empty:
            return None

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


def run_match(team1_name: str, team1_path: str, team2_name: str, team2_path: str, max_moves: int = MAX_MOVES, time_bank: float = 60.0):
    """
    Run a full match between two bots using a global timebank.

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

    # Initialize global timebanks
    time_bank_p1 = time_bank
    time_bank_p2 = time_bank

    result = None

    try:
        for move_number in range(max_moves):
            if move_number % 2 == 0:
                current_player = Player.RED
                current_bot = bot1
                current_name = team1_name
                current_time_remaining = time_bank_p1
                opp_time_remaining = time_bank_p2
            else:
                current_player = Player.BLUE
                current_bot = bot2
                current_name = team2_name
                current_time_remaining = time_bank_p2
                opp_time_remaining = time_bank_p1

            # Check if bot is still running
            if not current_bot.is_alive():
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} bot crashed (process exited)",
                    "moves": moves,
                }
                break

            # Send board state and time arrays to current bot
            state_json = board.to_json(current_player, move_number, current_time_remaining, opp_time_remaining)
            try:
                current_bot.send_state(state_json)
            except (BrokenPipeError, OSError):
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} bot crashed (broken pipe)",
                    "moves": moves,
                }
                break

            # Read move from bot, subtracting exactly elapsed time
            start_time = time.time()
            move_str = current_bot.read_move(current_time_remaining)
            elapsed_time = time.time() - start_time
            
            # Apply time deductions
            if move_number % 2 == 0:
                time_bank_p1 -= elapsed_time
                current_time_remaining = time_bank_p1
            else:
                time_bank_p2 -= elapsed_time
                current_time_remaining = time_bank_p2
                
            if current_time_remaining <= 0 or move_str is None:
                result = {
                    "winner": f"DQ:{current_name}",
                    "result_desc": f"{current_name} ran out of time! (Bank: {current_time_remaining:.2f}s left)",
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
                "result_desc": f"Draw — game reached {max_moves} moves without a winner",
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
