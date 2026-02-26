"""
Headless Chain Reaction game engine — no pygame dependency.
Pure game logic that can be used by the bot runner.
"""

from enum import IntEnum
import json
import copy


class Player(IntEnum):
    NONE = 0
    RED = 1
    BLUE = 2


ROWS = 7
COLS = 7
MAX_MOVES = 1000
MAX_CASCADE = 200  # safety limit on explosion cascade iterations


class BoardCell:
    __slots__ = ("player", "count")

    def __init__(self, player=Player.NONE, count=0):
        self.player = player
        self.count = count

    def to_list(self):
        return [self.count, int(self.player)]

    def copy(self):
        return BoardCell(self.player, self.count)


class Board:
    """Chain Reaction board — headless (no display)."""

    def __init__(self, rows=ROWS, cols=COLS):
        self.rows = rows
        self.cols = cols
        self.grid = [[BoardCell() for _ in range(cols)] for _ in range(rows)]

    # ------------------------------------------------------------------ #
    #  Core game logic (unchanged from your board.py)                     #
    # ------------------------------------------------------------------ #

    def make_move(self, x: int, y: int, player: Player) -> bool:
        """Place a piece at (x, y) for *player*.  Returns False if invalid."""
        if player == Player.NONE:
            return False
        if not self._valid(x, y):
            return False
        if (
            self.grid[x][y].player != Player.NONE
            and self.grid[x][y].player != player
        ):
            return False

        # BFS explosion cascade
        queue = [(x, y)]
        cascade_count = 0
        while queue and cascade_count < MAX_CASCADE:
            cascade_count += 1
            next_queue = []
            for cx, cy in queue:
                cell = self.grid[cx][cy]
                cell.count += 1
                cell.player = player

                if self._exploding(cx, cy):
                    cell.count = 0
                    cell.player = Player.NONE
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = cx + dx, cy + dy
                        if self._valid(nx, ny):
                            next_queue.append((nx, ny))
            queue = next_queue
        return True

    def check_win(self, move_counter: int, player: Player) -> bool:
        """Returns True if *player* has won (no opponent pieces remain)."""
        if move_counter < 2:
            return False
        for row in self.grid:
            for cell in row:
                if cell.player != Player.NONE and cell.player != player:
                    return False
        return True

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _valid(self, x: int, y: int) -> bool:
        return 0 <= x < self.rows and 0 <= y < self.cols

    def _exploding(self, x: int, y: int) -> bool:
        if not self._valid(x, y):
            return False
        threshold = 4
        if x == 0 or x == self.rows - 1:
            threshold -= 1
        if y == 0 or y == self.cols - 1:
            threshold -= 1
        return self.grid[x][y].count >= threshold

    # ------------------------------------------------------------------ #
    #  Serialization                                                      #
    # ------------------------------------------------------------------ #

    def to_state(self, player: Player, move_number: int) -> dict:
        """Return the full game state as a JSON-serializable dict.

        This is what gets sent to bots via stdin.
        Format:
            {
                "board": [[count, owner], ...],   # 7x7
                "player": 1 or 2,
                "move_number": int,
                "rows": 7,
                "cols": 7
            }
        """
        return {
            "board": [[cell.to_list() for cell in row] for row in self.grid],
            "player": int(player),
            "move_number": move_number,
            "rows": self.rows,
            "cols": self.cols,
        }

    def to_json(self, player: Player, move_number: int) -> str:
        """Serialize state to a single-line JSON string."""
        return json.dumps(self.to_state(player, move_number))

    def snapshot(self) -> list:
        """Return a lightweight snapshot of the board for replays."""
        return [[cell.to_list() for cell in row] for row in self.grid]

    def display(self):
        """Simple text display for debugging."""
        for i in range(self.rows):
            parts = []
            for j in range(self.cols):
                c = self.grid[i][j]
                if c.player == Player.NONE:
                    parts.append(" . ")
                elif c.player == Player.RED:
                    parts.append(f"R{c.count} ")
                else:
                    parts.append(f"B{c.count} ")
            print("|".join(parts))
        print()
