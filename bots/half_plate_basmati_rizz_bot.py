import json
import time

NONE, RED, BLUE = 0, 1, 2
MAX_VALUE = 1000000
MAX_DEPTH = 60

# ── Module-level topology (computed once per board size) ──────────────
_CM = None       # bytearray – critical mass per flat cell index
_NBRS = None     # list[tuple[int,...]] – neighbor flat indices
_SZ = 0          # total cell count (rows * cols)
_R = _C = 0

def _init_topo(R, C):
    global _CM, _NBRS, _SZ, _R, _C
    if _R == R and _C == C:
        return
    _R, _C, _SZ = R, C, R * C
    cm = bytearray(R * C)
    nbrs = [None] * (R * C)
    for i in range(R):
        for j in range(C):
            idx = i * C + j
            m = 4
            if i == 0 or i == R - 1:
                m -= 1
            if j == 0 or j == C - 1:
                m -= 1
            cm[idx] = m
            n = []
            if i > 0:
                n.append(idx - C)
            if i < R - 1:
                n.append(idx + C)
            if j > 0:
                n.append(idx - 1)
            if j < C - 1:
                n.append(idx + 1)
            nbrs[idx] = tuple(n)
    _CM, _NBRS = cm, nbrs


# ── Board ─────────────────────────────────────────────────────────────
# Flat bytearray for owners/counts → single C-level memcpy on copy.
# Incremental cc[] (cell count per player) and cr[] (critical count per
# player) give O(1) heuristic evaluation and terminal detection.

class Board:
    __slots__ = ('owners', 'counts', 'cc', 'cr')

    def copy(self):
        b = Board.__new__(Board)
        b.owners = bytearray(self.owners)
        b.counts = bytearray(self.counts)
        b.cc = self.cc[:]
        b.cr = self.cr[:]
        return b

    def copy_move(self, pos, player):
        """Copy board and apply move in one step (avoids an intermediate object)."""
        b = Board.__new__(Board)
        ow = bytearray(self.owners)
        ct = bytearray(self.counts)
        cc = self.cc[:]
        cr = self.cr[:]
        cm = _CM
        nbrs = _NBRS
        queue = [pos]
        while queue:
            nq = []
            nq_extend = nq.extend
            for p in queue:
                oo = ow[p]
                oc = ct[p]
                pcm = cm[p]
                if oo:
                    cc[oo] -= 1
                    if oc == pcm - 1:
                        cr[oo] -= 1
                nc = oc + 1
                if nc >= pcm:
                    ct[p] = 0
                    ow[p] = 0
                    nq_extend(nbrs[p])
                else:
                    ct[p] = nc
                    ow[p] = player
                    cc[player] += 1
                    if nc == pcm - 1:
                        cr[player] += 1
            queue = nq
            if nq and (cc[1] | cc[2]) > 1 and (cc[1] == 0 or cc[2] == 0):
                break
        b.owners = ow
        b.counts = ct
        b.cc = cc
        b.cr = cr
        return b


def _parse(line):
    state = json.loads(line)
    R, C = state['rows'], state['cols']
    _init_topo(R, C)
    sz = R * C
    ow = bytearray(sz)
    ct = bytearray(sz)
    cc = [0, 0, 0]
    cr = [0, 0, 0]
    cm = _CM
    for i, row in enumerate(state['board']):
        base = i * C
        for j, cell in enumerate(row):
            idx = base + j
            c, o = cell[0], cell[1]
            ct[idx] = c
            ow[idx] = o
            if o:
                cc[o] += 1
                if c == cm[idx] - 1:
                    cr[o] += 1
    b = Board.__new__(Board)
    b.owners = ow
    b.counts = ct
    b.cc = cc
    b.cr = cr
    return b, state['player'], state['my_time']


# ── Search engine ─────────────────────────────────────────────────────

_mono = time.monotonic


class _Timeout(Exception):
    __slots__ = ()


class Engine:
    __slots__ = ('_st', '_tl', '_to', '_nc',
                 '_km', '_ke', '_hist')

    def __init__(self, time_limit_s):
        self._st = _mono()
        self._tl = time_limit_s
        self._to = False
        self._nc = 0
        self._km = [[-1, -1] for _ in range(MAX_DEPTH)]
        self._ke = [[0, 0] for _ in range(MAX_DEPTH)]
        self._hist = [[0] * _SZ, [0] * _SZ, [0] * _SZ]

    # ── negamax ───────────────────────────────────────────────────────

    def _negamax(self, bd, player, depth, level, alpha, beta):
        nc = self._nc + 1
        self._nc = nc
        if nc & 255 == 0 and _mono() - self._st >= self._tl:
            raise _Timeout()

        cc = bd.cc
        c1, c2 = cc[1], cc[2]
        if (c1 | c2) > 1 and (c1 == 0 or c2 == 0):
            if (c1 == 0) == (player == RED):
                return -MAX_VALUE + level
            return MAX_VALUE - level

        opp = 3 - player
        if depth <= 0:
            return (cc[player] - cc[opp]) + (bd.cr[player] - bd.cr[opp])

        ow = bd.owners
        sz = _SZ
        moves = [p for p in range(sz) if ow[p] == 0 or ow[p] == player]
        if not moves:
            return (cc[player] - cc[opp]) + (bd.cr[player] - bd.cr[opp])

        # Cheap move ordering: killers → history + critical-cell bonus.
        # No board-copy/simulation needed — keeps ordering overhead tiny.
        km0, km1 = self._km[level]
        hist = self._hist[player]
        ct = bd.counts
        cm = _CM
        if len(moves) > 1:
            moves.sort(key=lambda p: -(
                2000000 if p == km0 else
                1999999 if p == km1 else
                hist[p] + (100 if ow[p] == player and ct[p] == cm[p] - 1 else 0)
            ))

        negamax = self._negamax
        copy_move = bd.copy_move
        for mv in moves:
            nb = copy_move(mv, player)
            val = -negamax(nb, opp, depth - 1, level + 1, -beta, -alpha)
            if val > alpha:
                alpha = val
                if alpha >= MAX_VALUE - 100:
                    hist[mv] += depth * depth
                    return alpha
            if alpha >= beta:
                hist[mv] += depth * depth
                km = self._km[level]
                ke = self._ke[level]
                if mv == km[0]:
                    ke[0] += 1
                elif mv == km[1]:
                    ke[1] += 1
                    if ke[0] < ke[1]:
                        km[0], km[1] = km[1], km[0]
                        ke[0], ke[1] = ke[1], ke[0]
                else:
                    if km[0] < 0:
                        km[0] = mv; ke[0] = 1
                    elif km[1] < 0:
                        km[1] = mv; ke[1] = 1
                return alpha
            elif mv == km0 or mv == km1:
                km = self._km[level]
                ke = self._ke[level]
                idx = 0 if mv == km[0] else 1
                ke[idx] -= 1
                if ke[0] < ke[1]:
                    km[0], km[1] = km[1], km[0]
                    ke[0], ke[1] = ke[1], ke[0]
                if ke[1] <= 0:
                    ke[1] = 0
                    km[1] = -1
        return alpha

    # ── root search (one iteration of iterative deepening) ───────────

    def _root_search(self, configs, player, depth):
        opp = 3 - player
        alpha = -MAX_VALUE
        best = configs[0][0]
        negamax = self._negamax
        for cfg in configs:
            mv, mb, _ = cfg
            nc = self._nc + 1
            self._nc = nc
            if nc & 63 == 0 and _mono() - self._st >= self._tl:
                raise _Timeout()
            val = -negamax(mb, opp, depth - 1, 1, -MAX_VALUE, -alpha)
            cfg[2] = val
            if val > alpha:
                alpha = val
                best = mv
                if alpha >= MAX_VALUE - 100:
                    break
        configs.sort(key=lambda c: -c[2])
        return best

    # ── entry point ──────────────────────────────────────────────────

    def go(self, board, player):
        ow = board.owners
        sz = _SZ
        legal = [p for p in range(sz) if ow[p] == 0 or ow[p] == player]
        if not legal:
            return -1
        if len(legal) == 1:
            return legal[0]

        opp = 3 - player
        configs = []
        for p in legal:
            nb = board.copy_move(p, player)
            h = (nb.cc[player] - nb.cc[opp]) + (nb.cr[player] - nb.cr[opp])
            configs.append([p, nb, h])
        configs.sort(key=lambda c: -c[2])
        best = configs[0][0]

        depth = 1
        while depth < MAX_DEPTH and not self._to:
            try:
                best = self._root_search(configs, player, depth)
            except _Timeout:
                self._to = True
                break
            depth += 1
        return best


# ── Main loop ─────────────────────────────────────────────────────────

while True:
    line = input()
    board, player, my_time = _parse(line)
    time_limit = max(0.1, min(my_time / 50, 1.5))
    engine = Engine(time_limit)
    move = engine.go(board, player)
    if move >= 0:
        print(f"{move // _C} {move % _C}", flush=True)
    else:
        ow = board.owners
        for p in range(_SZ):
            if ow[p] == 0 or ow[p] == player:
                print(f"{p // _C} {p % _C}", flush=True)
                break

