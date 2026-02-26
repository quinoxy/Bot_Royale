"""
Sample Bot: Random Move
Strategy: Picks a random valid cell each turn.
Slightly better than first-valid since it's unpredictable.
"""
import json
import random

while True:
    line = input()
    state = json.loads(line)
    me = state["player"]
    board = state["board"]
    rows = state["rows"]
    cols = state["cols"]

    # Collect all valid cells
    valid_moves = []
    for r in range(rows):
        for c in range(cols):
            count, owner = board[r][c]
            if owner == 0 or owner == me:
                valid_moves.append((r, c))

    # Pick a random valid move
    r, c = random.choice(valid_moves)
    print(f"{r} {c}", flush=True)
