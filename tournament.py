"""
Bot Royale — Headless Tournament Runner
========================================
Runs all nC2 bot matchups in parallel, logs every move + timing,
handles infinite chain reactions, and produces a summary leaderboard.

Usage:
    python3 tournament.py
"""

import json
import os
import subprocess
import time
import itertools
import datetime
from enum import Enum
from concurrent.futures import ProcessPoolExecutor, as_completed

# ── Game constants (mirrored from constants.py, pygame-free) ──────────────────

ROWS = 7
COLS = 7
MAX_MOVES = 1000
INITIAL_TIME = 60.0  # 1 minute overall per player
MAX_CHAIN_ITERATIONS = 1000  # if a chain reaction exceeds this, it's infinite
BOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tournament_logs")
MAX_WORKERS = os.cpu_count() or 4


# ── Enums / helpers ──────────────────────────────────────────────────────────

class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2


# ── Headless board (no pygame) ───────────────────────────────────────────────

class BoardCell:
    __slots__ = ("player", "count")

    def __init__(self):
        self.player = Player.NONE
        self.count = 0


class SimBoard:
    """Chain-reaction board with infinite-loop detection."""

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.board = [[BoardCell() for _ in range(cols)] for _ in range(rows)]

    # ── helpers ───────────────────────────────────────────────────────────
    def _valid(self, x, y):
        return 0 <= x < self.rows and 0 <= y < self.cols

    def _threshold(self, x, y):
        t = 4
        if x == 0 or x == self.rows - 1:
            t -= 1
        if y == 0 or y == self.cols - 1:
            t -= 1
        return t

    # ── serialization (same JSON format bots expect) ─────────────────────
    def serialize(self, current_player: Player, move_number: int,
                  my_time: float, opp_time: float) -> str:
        cells = []
        for i in range(self.rows):
            row = []
            for j in range(self.cols):
                c = self.board[i][j]
                row.append([c.count, c.player.value])
            cells.append(row)
        return json.dumps({
            "rows": self.rows,
            "cols": self.cols,
            "player": current_player.value,
            "move_number": move_number,
            "my_time": my_time,
            "opp_time": opp_time,
            "board": cells,
        })

    # ── make a move (returns: "ok" | "invalid" | "infinite") ────────────
    def make_move(self, x: int, y: int, player: Player) -> str:
        if player == Player.NONE:
            return "invalid"
        if not self._valid(x, y):
            return "invalid"
        cell = self.board[x][y]
        if cell.player != Player.NONE and cell.player != player:
            return "invalid"

        queue = [(x, y)]
        iterations = 0

        while queue:
            iterations += 1
            if iterations > MAX_CHAIN_ITERATIONS:
                return "infinite"  # unstoppable chain → current player wins

            next_queue = []
            for cx, cy in queue:
                c = self.board[cx][cy]
                c.count += 1
                c.player = player

                if c.count >= self._threshold(cx, cy):
                    c.count = 0
                    c.player = Player.NONE
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = cx + dx, cy + dy
                        if self._valid(nx, ny):
                            next_queue.append((nx, ny))
            queue = next_queue

        return "ok"

    # ── win check ────────────────────────────────────────────────────────
    def check_win(self, move_counter: int, player: Player) -> bool:
        if move_counter < 2:
            return False
        for i in range(self.rows):
            for j in range(self.cols):
                p = self.board[i][j].player
                if p != Player.NONE and p != player:
                    return False
        return True

    # ── snapshot for logging ─────────────────────────────────────────────
    def snapshot(self):
        """Return a lightweight representation of the board for logs."""
        return [
            [
                (self.board[i][j].count, self.board[i][j].player.value)
                for j in range(self.cols)
            ]
            for i in range(self.rows)
        ]


# ── Bot communication ────────────────────────────────────────────────────────

def get_bot_move(bot_path: str, board: SimBoard, player: Player,
                 move_counter: int, my_time: float, opp_time: float):
    """Spawn bot, send state JSON, read back 'row col'.

    Returns (move_or_None, time_spent).
    """
    state_json = board.serialize(player, move_counter, my_time, opp_time)

    start = time.monotonic()
    proc = None
    try:
        proc = subprocess.Popen(
            ["python3", bot_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(state_json + "\n", timeout=my_time)
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
            proc.communicate()  # reap
        return None, time.monotonic() - start, "timeout"
    except Exception as exc:
        if proc:
            proc.kill()
            proc.communicate()
        return None, time.monotonic() - start, f"crash: {exc}"

    elapsed = time.monotonic() - start

    if stderr:
        pass  # ignore stderr in tournament mode

    if stdout:
        try:
            row, col = map(int, stdout.strip().split())
            return (row, col), elapsed, None
        except Exception:
            return None, elapsed, f"bad_output: {stdout.strip()!r}"

    return None, elapsed, "no_output"


# ── Single game simulation ───────────────────────────────────────────────────

def simulate_game(red_bot_path: str, blue_bot_path: str):
    """Play one full game.  Returns a dict with the complete game log."""
    board = SimBoard(ROWS, COLS)
    move_counter = 0
    red_time = INITIAL_TIME
    blue_time = INITIAL_TIME

    red_name = os.path.splitext(os.path.basename(red_bot_path))[0]
    blue_name = os.path.splitext(os.path.basename(blue_bot_path))[0]

    moves_log = []  # list of per-move dicts
    result = {
        "red_bot": red_name,
        "blue_bot": blue_name,
        "winner": None,          # "red" | "blue" | "draw"
        "reason": None,
        "total_moves": 0,
        "moves": moves_log,
    }

    while move_counter < MAX_MOVES:
        if move_counter % 2 == 0:
            player = Player.RED
            bot_path = red_bot_path
            my_time = red_time
            opp_time = blue_time
        else:
            player = Player.BLUE
            bot_path = blue_bot_path
            my_time = blue_time
            opp_time = red_time

        side = "red" if player == Player.RED else "blue"
        opponent_side = "blue" if side == "red" else "red"

        move, elapsed, err = get_bot_move(
            bot_path, board, player, move_counter, my_time, opp_time
        )

        # Update clock
        if player == Player.RED:
            red_time -= elapsed
        else:
            blue_time -= elapsed

        remaining = red_time if player == Player.RED else blue_time

        entry = {
            "move_number": move_counter,
            "player": side,
            "move": None,
            "time_taken": round(elapsed, 6),
            "remaining_time": round(remaining, 6),
            "result": None,
            "board_after": None,
        }

        # ── Timeout ──────────────────────────────────────────────────
        if remaining <= 0 or err == "timeout":
            entry["result"] = "timeout"
            moves_log.append(entry)
            result["winner"] = opponent_side
            result["reason"] = f"{side} ran out of time"
            break

        # ── No valid move returned ───────────────────────────────────
        if move is None:
            entry["result"] = f"forfeit ({err})"
            moves_log.append(entry)
            result["winner"] = opponent_side
            result["reason"] = f"{side} failed to return a move ({err})"
            break

        entry["move"] = list(move)

        # ── Apply move ───────────────────────────────────────────────
        status = board.make_move(move[0], move[1], player)

        if status == "invalid":
            entry["result"] = "invalid_move"
            moves_log.append(entry)
            result["winner"] = opponent_side
            result["reason"] = f"{side} made invalid move {move}"
            break

        if status == "infinite":
            # Infinite chain reaction means this player's pieces are
            # propagating endlessly — they effectively captured everything.
            entry["result"] = "infinite_chain_win"
            entry["board_after"] = board.snapshot()
            moves_log.append(entry)
            result["winner"] = side
            result["reason"] = (
                f"{side} triggered an unstoppable chain reaction"
            )
            break

        # status == "ok"
        entry["board_after"] = board.snapshot()

        if board.check_win(move_counter, player):
            entry["result"] = "win"
            moves_log.append(entry)
            result["winner"] = side
            result["reason"] = f"{side} captured all opponent pieces"
            break

        entry["result"] = "ok"
        moves_log.append(entry)
        move_counter += 1
    else:
        # Exceeded MAX_MOVES
        result["winner"] = "draw"
        result["reason"] = f"Game reached {MAX_MOVES} moves without a winner"

    result["total_moves"] = move_counter
    result["red_time_remaining"] = round(red_time, 6)
    result["blue_time_remaining"] = round(blue_time, 6)
    return result


# ── Worker wrapper (picklable for ProcessPoolExecutor) ────────────────────────

def _run_matchup(args):
    red_path, blue_path, game_id, games_dir = args
    try:
        game_result = simulate_game(red_path, blue_path)

        # Write the full detailed log (every move + board snapshots) to its own file
        game_file = os.path.join(
            games_dir,
            f"game_{game_id:04d}__{game_result['red_bot']}_vs_{game_result['blue_bot']}.json",
        )
        with open(game_file, "w") as f:
            json.dump(game_result, f, indent=2)

        # Return a lightweight summary (no moves list / board snapshots)
        summary = {k: v for k, v in game_result.items() if k != "moves"}
        summary["log_file"] = os.path.basename(game_file)
        summary["num_moves"] = len(game_result["moves"])
        return game_id, summary

    except Exception as exc:
        return game_id, {
            "red_bot": os.path.basename(red_path),
            "blue_bot": os.path.basename(blue_path),
            "winner": None,
            "reason": f"engine crash: {exc}",
            "total_moves": 0,
            "num_moves": 0,
            "log_file": None,
        }


# ── Tournament orchestrator ──────────────────────────────────────────────────

def discover_bots(bots_dir: str):
    """Return sorted list of .py files in the bots directory."""
    bots = []
    for f in sorted(os.listdir(bots_dir)):
        if f.endswith(".py"):
            bots.append(os.path.join(bots_dir, f))
    return bots


def run_tournament():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    games_dir = os.path.join(LOG_DIR, f"games_{timestamp}")
    os.makedirs(games_dir, exist_ok=True)

    bots = discover_bots(BOTS_DIR)
    bot_names = [os.path.splitext(os.path.basename(b))[0] for b in bots]
    n = len(bots)
    pairs = list(itertools.combinations(range(n), 2))
    total_games = len(pairs) * 2  # each pair plays twice (swap sides)

    print(f"Bot Royale Tournament — {timestamp}")
    print(f"Bots found: {n}")
    for name in bot_names:
        print(f"  • {name}")
    print(f"Total games (nC2 × 2): {total_games}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)

    # Build work items — each pair plays two games, swapping RED/BLUE sides
    work = []
    game_id = 0
    for i, j in pairs:
        work.append((bots[i], bots[j], game_id, games_dir))      # i=RED, j=BLUE
        game_id += 1
        work.append((bots[j], bots[i], game_id, games_dir))      # j=RED, i=BLUE
        game_id += 1

    # ── Run in parallel ──────────────────────────────────────────────
    results = [None] * total_games
    start_all = time.monotonic()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run_matchup, w): w[2] for w in work}
        completed = 0
        for fut in as_completed(futures):
            game_id, game_result = fut.result()
            results[game_id] = game_result
            completed += 1
            r = game_result
            tag = f"[{completed}/{total_games}]"
            print(
                f"{tag} {r['red_bot']} (RED) vs {r['blue_bot']} (BLUE)  →  "
                f"winner: {r['winner']}  ({r['reason']})"
            )

    elapsed_all = time.monotonic() - start_all
    print("=" * 60)
    print(f"All games finished in {elapsed_all:.1f}s")

    # ── Save detailed logs ───────────────────────────────────────────
    log_path = os.path.join(LOG_DIR, f"tournament_{timestamp}.json")
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Summary saved to {log_path}")
    print(f"Per-game logs saved to {games_dir}/")

    # ── Leaderboard ──────────────────────────────────────────────────
    stats = {name: {"wins": 0, "losses": 0, "draws": 0, "forfeits_against": 0}
             for name in bot_names}

    for r in results:
        if r is None:
            continue
        red = r["red_bot"]
        blue = r["blue_bot"]
        w = r["winner"]
        if w == "red":
            stats[red]["wins"] += 1
            stats[blue]["losses"] += 1
        elif w == "blue":
            stats[blue]["wins"] += 1
            stats[red]["losses"] += 1
        elif w == "draw":
            stats[red]["draws"] += 1
            stats[blue]["draws"] += 1
        else:
            # engine crash or unknown
            pass

    # Sort by wins desc, then losses asc
    leaderboard = sorted(
        stats.items(),
        key=lambda kv: (-kv[1]["wins"], kv[1]["losses"]),
    )

    print("\n" + "=" * 60)
    print("LEADERBOARD")
    print("=" * 60)
    print(f"{'#':<4} {'Bot':<40} {'W':>4} {'L':>4} {'D':>4}")
    print("-" * 60)
    for rank, (name, s) in enumerate(leaderboard, 1):
        print(f"{rank:<4} {name:<40} {s['wins']:>4} {s['losses']:>4} {s['draws']:>4}")

    # Save leaderboard
    lb_path = os.path.join(LOG_DIR, f"leaderboard_{timestamp}.json")
    with open(lb_path, "w") as f:
        json.dump(leaderboard, f, indent=2)
    print(f"\nLeaderboard saved to {lb_path}")


if __name__ == "__main__":
    run_tournament()
