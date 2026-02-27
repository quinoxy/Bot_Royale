"""
Tournament runner — schedules and runs matches between bots.
Run this script manually to start matches.

Usage:
    python run_tournament.py --round-robin          Run all-vs-all
    python run_tournament.py --match team1 team2    Run a single match
    python run_tournament.py --list                 List registered teams
"""

import argparse
import os
import sys
import time
from itertools import combinations

sys.path.insert(0, os.path.dirname(__file__))
from database import init_db, get_all_teams, get_team, record_match, get_setting
from bot_runner import run_match


def list_teams():
    teams = get_all_teams()
    if not teams:
        print("No teams registered. Upload bots first via the Upload Server.")
        return
    print(f"\n{'#':<4} {'Team':<25} {'Uploaded':<20}")
    print("-" * 50)
    for i, t in enumerate(teams, 1):
        print(f"{i:<4} {t['name']:<25} {t['uploaded_at'][:16]}")
    print(f"\nTotal: {len(teams)} teams")


def run_single_match(team1_name: str, team2_name: str):
    t1 = get_team(team1_name)
    t2 = get_team(team2_name)

    if not t1:
        print(f"Error: Team '{team1_name}' not found.")
        return
    if not t2:
        print(f"Error: Team '{team2_name}' not found.")
        return

    print(f"\n[MATCH] {team1_name} (RED) vs {team2_name} (BLUE)")
    print("-" * 50)

    # Read configurable settings
    move_timeout = float(get_setting("move_timeout", "2"))
    max_moves = int(get_setting("max_moves", "1000"))

    start = time.time()
    result = run_match(team1_name, t1["file_path"], team2_name, t2["file_path"], move_timeout=move_timeout, max_moves=max_moves)
    elapsed = time.time() - start

    print(f"\n{result['result_desc']}")
    print(f"Total moves: {len(result['moves'])}")
    print(f"Time: {elapsed:.1f}s")

    # Record in database
    record_match(team1_name, team2_name, result["winner"], result["result_desc"], result["moves"])
    print("[OK] Match recorded in database.")


def run_round_robin():
    teams = get_all_teams()
    if len(teams) < 2:
        print("Need at least 2 teams for a round-robin. Upload more bots!")
        return

    matchups = list(combinations(teams, 2))
    total = len(matchups)
    print(f"\n[TOURNAMENT] Round Robin - {len(teams)} teams, {total} matches\n")

    # Read configurable settings
    move_timeout = float(get_setting("move_timeout", "2"))
    max_moves = int(get_setting("max_moves", "1000"))

    for i, (t1, t2) in enumerate(matchups, 1):
        print(f"[{i}/{total}] {t1['name']} vs {t2['name']} ... ", end="", flush=True)

        start = time.time()
        result = run_match(t1["name"], t1["file_path"], t2["name"], t2["file_path"], move_timeout=move_timeout, max_moves=max_moves)
        elapsed = time.time() - start

        # Short summary
        if result["winner"] is None:
            print(f"DRAW ({len(result['moves'])} moves, {elapsed:.1f}s)")
        elif result["winner"].startswith("DQ:"):
            dq = result["winner"].split(":", 1)[1]
            print(f"DQ: {dq} ({elapsed:.1f}s)")
        else:
            print(f"WINNER: {result['winner']} ({len(result['moves'])} moves, {elapsed:.1f}s)")

        record_match(t1["name"], t2["name"], result["winner"], result["result_desc"], result["moves"])

    print(f"\nDone! All {total} matches complete. Check the leaderboard!")


def main():
    parser = argparse.ArgumentParser(description="Bot Royale Tournament Runner")
    parser.add_argument("--list", action="store_true", help="List all registered teams")
    parser.add_argument("--match", nargs=2, metavar=("TEAM1", "TEAM2"), help="Run a single match")
    parser.add_argument("--round-robin", action="store_true", help="Run all-vs-all round robin")

    args = parser.parse_args()

    init_db()

    if args.list:
        list_teams()
    elif args.match:
        run_single_match(args.match[0], args.match[1])
    elif args.round_robin:
        run_round_robin()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
