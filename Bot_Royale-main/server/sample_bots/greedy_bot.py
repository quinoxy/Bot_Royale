"""
Sample Bot: Greedy (plays cells closest to exploding)
Strategy: Prioritizes cells that are 1 away from their critical mass.
         If no such cell exists, picks a random valid cell.
"""
import json
import random

def get_critical_mass(r, c, rows, cols):
    """Calculate the explosion threshold for a cell."""
    threshold = 4
    if r == 0 or r == rows - 1:
        threshold -= 1
    if c == 0 or c == cols - 1:
        threshold -= 1
    return threshold

while True:
    line = input()
    state = json.loads(line)
    me = state["player"]
    board = state["board"]
    rows = state["rows"]
    cols = state["cols"]

    best_moves = []
    good_moves = []
    ok_moves = []

    for r in range(rows):
        for c in range(cols):
            count, owner = board[r][c]
            if owner == 0 or owner == me:
                crit = get_critical_mass(r, c, rows, cols)
                if owner == me and count == crit - 1:
                    # One away from exploding — highest priority
                    best_moves.append((r, c))
                elif owner == me:
                    good_moves.append((r, c))
                else:
                    ok_moves.append((r, c))

    # Pick from best available category
    if best_moves:
        r, c = random.choice(best_moves)
    elif good_moves:
        r, c = random.choice(good_moves)
    else:
        r, c = random.choice(ok_moves)

    print(f"{r} {c}", flush=True)
