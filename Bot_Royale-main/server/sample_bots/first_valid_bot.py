"""
Sample Bot: First Valid Move
Strategy: Picks the first valid cell (left-to-right, top-to-bottom).
This is the simplest possible bot — use it as a template.
"""
import json

while True:
    line = input()
    state = json.loads(line)
    me = state["player"]
    board = state["board"]
    rows = state["rows"]
    cols = state["cols"]

    moved = False
    for r in range(rows):
        for c in range(cols):
            count, owner = board[r][c]
            if owner == 0 or owner == me:
                print(f"{r} {c}", flush=True)
                moved = True
                break
        if moved:
            break
