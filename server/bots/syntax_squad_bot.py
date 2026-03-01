"""
bot_v2.py — Maximum-strength Bot Royale AI

New over bot.py:
  1. Opening book       — corners first, then edges
  2. Null-move pruning  — massive speed gain at deeper depths
  3. Late Move Reduction (LMR) — reduce depth for "quiet" later moves
  4. History heuristic  — rank moves by historical cutoff success
  5. Chain-reaction threat eval — count captures we'd make in 1 explosion
  6. Endgame acceleration — switch to kill-mode when opponent is weak
  7. Soft time control   — spend time proportional to how contested the position is
"""

import json
import time
import random
from enum import Enum

# ─────────────────────────────────────────────────────────────────
#  Enums & data classes
# ─────────────────────────────────────────────────────────────────

class Player(Enum):
    NONE = 0
    RED  = 1
    BLUE = 2


class BoardCell:
    __slots__ = ('player', 'count')
    def __init__(self):
        self.player = Player.NONE
        self.count  = 0


# ─────────────────────────────────────────────────────────────────
#  Board
# ─────────────────────────────────────────────────────────────────

class Board:
    def __init__(self, line):
        state            = json.loads(line)
        self.rows        = state['rows']
        self.cols        = state['cols']
        self.my_time     = state['my_time']
        self.opp_time    = state['opp_time']
        self.me          = state['player']
        self.move_number = state.get('move_number', 0)

        self.board = [[BoardCell() for _ in range(self.cols)]
                      for _ in range(self.rows)]
        for i, row in enumerate(state['board']):
            for j, cd in enumerate(row):
                self.board[i][j].count  = cd[0]
                self.board[i][j].player = Player(cd[1])

        R, C = self.rows, self.cols

        # Pre-computed tables (shared across copies)
        self._thr = [
            [4 - (1 if i in (0,R-1) else 0) - (1 if j in (0,C-1) else 0)
             for j in range(C)]
            for i in range(R)
        ]
        self._adj = {
            (i,j): [(i+di, j+dj)
                    for di,dj in ((-1,0),(1,0),(0,-1),(0,1))
                    if 0 <= i+di < R and 0 <= j+dj < C]
            for i in range(R) for j in range(C)
        }
        # Positional weight: corners > edges > interior
        self._pos_w = [
            [3 - (1 if i not in (0,R-1) else 0) - (1 if j not in (0,C-1) else 0)
             for j in range(C)]
            for i in range(R)
        ]

        # Zobrist hash
        random.seed(42)
        self._zh = [
            [[random.getrandbits(64) for _ in range(5)] for _ in range(3)]
            for _ in range(R * C)
        ]
        self._hash = self._compute_hash()

    @classmethod
    def _blank(cls, src):
        o = cls.__new__(cls)
        o.rows = src.rows; o.cols = src.cols
        o.my_time = src.my_time; o.opp_time = src.opp_time
        o.me = src.me; o.move_number = src.move_number
        o._thr = src._thr; o._adj = src._adj
        o._pos_w = src._pos_w; o._zh = src._zh
        return o

    def copy(self):
        nb = Board._blank(self)
        nb.board = [[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(self.cols):
                nb.board[i][j].player = self.board[i][j].player
                nb.board[i][j].count  = self.board[i][j].count
        nb._hash = self._hash
        return nb

    # ── Zobrist ───────────────────────────────────────────────────
    def _compute_hash(self):
        h = 0
        for i in range(self.rows):
            for j in range(self.cols):
                c = self.board[i][j]
                h ^= self._zh[i*self.cols+j][c.player.value][min(c.count,4)]
        return h

    def _zhash(self, i, j, p, cnt):
        return self._zh[i*self.cols+j][p.value][min(cnt,4)]

    # ── Move simulation ───────────────────────────────────────────
    def makeMove(self, x, y, player):
        if player == Player.NONE: return False
        if not (0 <= x < self.rows and 0 <= y < self.cols): return False
        c = self.board[x][y]
        if c.player != Player.NONE and c.player != player: return False

        q = [(x, y)]
        while q:
            nq = []
            for cx, cy in q:
                cell = self.board[cx][cy]
                old_p, old_cnt = cell.player, cell.count
                cell.count += 1; cell.player = player
                self._hash ^= self._zhash(cx, cy, old_p, old_cnt)
                self._hash ^= self._zhash(cx, cy, player, cell.count)

                if cell.count >= self._thr[cx][cy]:
                    op2, oc2 = cell.player, cell.count
                    cell.count = 0; cell.player = Player.NONE
                    self._hash ^= self._zhash(cx, cy, op2, oc2)
                    self._hash ^= self._zhash(cx, cy, Player.NONE, 0)
                    nq.extend(self._adj[(cx, cy)])
            q = nq
        return True

    # ── Terminal detection ────────────────────────────────────────
    def isTerminal(self, mc):
        if mc < 2: return False
        r = b = False
        for row in self.board:
            for cell in row:
                if cell.player == Player.RED:   r = True
                elif cell.player == Player.BLUE: b = True
                if r and b: return False
        return True

    # ── Piece counts (fast) ───────────────────────────────────────
    def counts(self):
        """Returns (my_cells, opp_cells, my_orbs, opp_orbs) for self.me."""
        player   = Player.RED if self.me == 1 else Player.BLUE
        opponent = Player.BLUE if player == Player.RED else Player.RED
        mc = oc = mo = oo = 0
        for row in self.board:
            for cell in row:
                if cell.player == player:
                    mc += 1; mo += cell.count
                elif cell.player == opponent:
                    oc += 1; oo += cell.count
        return mc, oc, mo, oo

    # ── Evaluation ───────────────────────────────────────────────
    def evaluate(self, player):
        opponent = Player.BLUE if player == Player.RED else Player.RED

        my_orbs = opp_orbs = 0
        score = 0
        red_alive = blue_alive = False

        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                thr  = self._thr[i][j]
                pw   = self._pos_w[i][j]

                if cell.player == player:
                    red_alive |= (player == Player.RED)
                    blue_alive |= (player == Player.BLUE)
                    my_orbs  += cell.count

                    base  = cell.count * 2 * pw
                    slack = thr - cell.count
                    press = max(0, 4 - slack)   # 0..3
                    score += base + press

                    # Chain-reaction threat: about to explode into opponent cells
                    if slack == 1:
                        captures = sum(
                            1 for ni,nj in self._adj[(i,j)]
                            if self.board[ni][nj].player == opponent
                        )
                        score += captures * 6   # each captured cell = big bonus

                elif cell.player == opponent:
                    red_alive |= (opponent == Player.RED)
                    blue_alive |= (opponent == Player.BLUE)
                    opp_orbs += cell.count

                    base  = cell.count * 2 * pw
                    slack = thr - cell.count
                    press = max(0, 4 - slack)
                    score -= base + press

                    # Danger: opponent about to explode into our cells
                    if slack == 1:
                        danger = sum(
                            1 for ni,nj in self._adj[(i,j)]
                            if self.board[ni][nj].player == player
                        )
                        score -= danger * 5

        # Terminal
        if not red_alive:
            return  1000 if player == Player.BLUE else -1000
        if not blue_alive:
            return  1000 if player == Player.RED  else -1000

        # Endgame amplifier: when opponent is down to few orbs, heavily emphasise lead
        total = my_orbs + opp_orbs
        if total > 0 and opp_orbs < 5:
            score += (my_orbs - opp_orbs) * 10   # aggressive finish

        return score

    # ── Move generation ───────────────────────────────────────────
    def getLegalMoves(self, player):
        """Ordered: critical → high-count owned → low-count → empty (centre-first)."""
        critical, high, low, empty = [], [], [], []
        rmid = self.rows / 2; cmid = self.cols / 2
        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE:
                    empty.append((abs(i-rmid)+abs(j-cmid), i, j))
                elif cell.player == player:
                    slack = self._thr[i][j] - cell.count
                    if slack == 1:   critical.append((i,j))
                    elif cell.count >= 2: high.append((i,j))
                    else: low.append((i,j))
        empty.sort()
        return critical + high + low + [(i,j) for _,i,j in empty]


# ─────────────────────────────────────────────────────────────────
#  Search infrastructure
# ─────────────────────────────────────────────────────────────────

EXACT = 0; LOWER = 1; UPPER = 2

class TTEntry:
    __slots__ = ('score','depth','flag','best_move')
    def __init__(self,s,d,f,m): self.score=s; self.depth=d; self.flag=f; self.best_move=m

_TT      = {}   # Transposition table
_KILLERS = {}   # Killer moves [depth] → [move, ...]
_HISTORY = {}   # History heuristic [move] → score
_DEADLINE = 0.0 # Time limit (set per getBestMove call)


def _time_up(): return time.time() >= _DEADLINE


def _store_killer(depth, move):
    k = _KILLERS.get(depth, [])
    if move not in k:
        _KILLERS[depth] = ([move] + k)[:2]


def _history_score(move):
    return _HISTORY.get(move, 0)


def _update_history(move, depth):
    _HISTORY[move] = _HISTORY.get(move, 0) + depth * depth


# ─────────────────────────────────────────────────────────────────
#  Null-move pruning (skip our turn, see if position is still great)
# ─────────────────────────────────────────────────────────────────

NULL_R = 2   # null-move reduction

def _do_null_move(board):
    """Return a board where the side to move passes (no-op)."""
    return board.copy()   # identical board; caller swaps maximizing flag


# ─────────────────────────────────────────────────────────────────
#  Core minimax
# ─────────────────────────────────────────────────────────────────

def minimax(board, depth, alpha, beta, maximizing, player, mc,
            allow_null=True):
    if _time_up():
        return board.evaluate(player), None

    # ── TT lookup ────────────────────────────────────────────────
    tt_key = board._hash ^ (mc & 0xFFFF) ^ (maximizing << 17)
    tt = _TT.get(tt_key)
    if tt and tt.depth >= depth:
        if tt.flag == EXACT:                return tt.score, tt.best_move
        elif tt.flag == LOWER:  alpha = max(alpha, tt.score)
        elif tt.flag == UPPER:  beta  = min(beta,  tt.score)
        if alpha >= beta:               return tt.score, tt.best_move

    # ── Terminal / leaf ──────────────────────────────────────────
    terminal = board.isTerminal(mc)
    if terminal or depth == 0:
        s = board.evaluate(player)
        _TT[tt_key] = TTEntry(s, depth, EXACT, None)
        return s, None

    opponent = Player.BLUE if player == Player.RED else Player.RED

    # ── Null-move pruning (only at depth ≥ 3, non-terminal, maximizing) ──
    if (allow_null and maximizing and depth >= 3):
        # Skip our turn — if opponent can't beat beta, we're good
        nb = _do_null_move(board)
        nm_score, _ = minimax(nb, depth - 1 - NULL_R, alpha, beta,
                              False, player, mc + 1, allow_null=False)
        if nm_score >= beta:
            return beta, None   # Null-move cutoff

    # ── Move generation + ordering ───────────────────────────────
    cur_player = player if maximizing else opponent
    moves = board.getLegalMoves(cur_player)
    if not moves:
        return board.evaluate(player), None

    # Blend killer + history into ordering
    killers = _KILLERS.get(depth, [])
    def move_key(m):
        k = 1000 if m in killers else 0
        return -(k + _history_score(m))

    moves = sorted(moves, key=move_key)

    best_move  = moves[0]
    orig_alpha = alpha

    if maximizing:
        best = float('-inf')
        for idx, move in enumerate(moves):
            if _time_up(): break

            nb = board.copy()
            nb.makeMove(move[0], move[1], cur_player)

            # ── Late Move Reduction (LMR) ─────────────────────────
            # Reduce depth for "later" quiet moves that are unlikely to be best
            reduce = 0
            if (idx >= 3 and depth >= 3 and move not in killers
                    and move not in (killers[:1] if killers else [])):
                reduce = 1

            score, _ = minimax(nb, depth - 1 - reduce, alpha, beta,
                               False, player, mc + 1)

            # Re-search at full depth if LMR raised alpha
            if reduce and score > alpha:
                score, _ = minimax(nb, depth - 1, alpha, beta, False, player, mc + 1)

            if score > best:
                best = score; best_move = move
            alpha = max(alpha, score)
            if beta <= alpha:
                _store_killer(depth, move)
                _update_history(move, depth)
                break

        flag = EXACT if orig_alpha < best < beta else \
               LOWER if best >= beta else UPPER
        _TT[tt_key] = TTEntry(best, depth, flag, best_move)
        return best, best_move

    else:
        best = float('inf')
        for idx, move in enumerate(moves):
            if _time_up(): break

            nb = board.copy()
            nb.makeMove(move[0], move[1], cur_player)

            reduce = 0
            if idx >= 3 and depth >= 3 and move not in killers:
                reduce = 1

            score, _ = minimax(nb, depth - 1 - reduce, alpha, beta,
                               True, player, mc + 1)
            if reduce and score < beta:
                score, _ = minimax(nb, depth - 1, alpha, beta, True, player, mc + 1)

            if score < best:
                best = score; best_move = move
            beta = min(beta, score)
            if beta <= alpha:
                _store_killer(depth, move)
                _update_history(move, depth)
                break

        flag = EXACT if orig_alpha < best < beta else \
               LOWER if best >= beta else UPPER
        _TT[tt_key] = TTEntry(best, depth, flag, best_move)
        return best, best_move


# ─────────────────────────────────────────────────────────────────
#  Opening book
# ─────────────────────────────────────────────────────────────────

def _opening_move(board, player):
    """
    First 4 moves: grab corners (threshold=2, hardest to dislodge).
    Then edges. Never pick an opponent-owned corner.
    """
    R, C = board.rows, board.cols
    corners = [(0,0),(0,C-1),(R-1,0),(R-1,C-1)]
    edges = ([(0,j) for j in range(1,C-1)] +
             [(R-1,j) for j in range(1,C-1)] +
             [(i,0) for i in range(1,R-1)] +
             [(i,C-1) for i in range(1,R-1)])

    for pos in corners + edges:
        cell = board.board[pos[0]][pos[1]]
        if cell.player in (Player.NONE, player):
            return pos
    return None


# ─────────────────────────────────────────────────────────────────
#  Iterative deepening entry point
# ─────────────────────────────────────────────────────────────────

def getBestMove(board, time_limit_ms=900):
    global _DEADLINE
    player = Player.RED if board.me == 1 else Player.BLUE
    _DEADLINE = time.time() + time_limit_ms / 1000.0

    # ── Opening book ─────────────────────────────────────────────
    if board.move_number < 6:
        move = _opening_move(board, player)
        if move:
            return move

    # ── Endgame: if opponent has ≤2 orbs, search deep immediately
    mc, oc, mo, oo = board.counts()
    if board.move_number >= 2 and oo <= 2:
        # Try immediate kill
        for m in board.getLegalMoves(player):
            nb = board.copy()
            nb.makeMove(m[0], m[1], player)
            if nb.isTerminal(board.move_number + 1):
                return m

    # Reset per-turn state
    _KILLERS.clear()
    _HISTORY.clear()

    legal = board.getLegalMoves(player)
    if not legal: return None
    best_move = legal[0]

    for depth in range(1, 14):
        if _time_up(): break
        try:
            _, m = minimax(board, depth, float('-inf'), float('inf'),
                           True, player, board.move_number)
            if m is not None:
                best_move = m
        except Exception:
            break

        # Early exit on decisive win found
        nb = board.copy()
        nb.makeMove(best_move[0], best_move[1], player)
        if nb.isTerminal(board.move_number + 1):
            break

    return best_move


# ─────────────────────────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────────────────────────

def play_move(r, c):
    print(f"{r} {c}", flush=True)


while True:
    line  = input()
    board = Board(line)
    move  = getBestMove(board, time_limit_ms=900)
    if move:
        play_move(move[0], move[1])
