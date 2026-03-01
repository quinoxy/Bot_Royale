import json
import time
import sys

# ============================================================================
# Precomputation for 7x7 Chain Reaction board
# All lookups are flat arrays/tuples indexed by (row*7+col) for max speed.
# ============================================================================
ROWS, COLS, SIZE = 7, 7, 49
INF = 999999

# Critical mass: corners=2, edges=3, center=4
CRITICAL = [0] * SIZE
NEIGHBORS = [None] * SIZE
POS_TYPE = [0] * SIZE        # 2=corner, 1=edge, 0=interior
POS_WEIGHT = [0] * SIZE      # static positional value per cell

for _i in range(ROWS):
    for _j in range(COLS):
        _idx = _i * COLS + _j
        t = 4
        if _i == 0 or _i == ROWS - 1:
            t -= 1
        if _j == 0 or _j == COLS - 1:
            t -= 1
        CRITICAL[_idx] = t

        nbrs = []
        for _di, _dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ni, nj = _i + _di, _j + _dj
            if 0 <= ni < ROWS and 0 <= nj < COLS:
                nbrs.append(ni * COLS + nj)
        NEIGHBORS[_idx] = tuple(nbrs)

        if t == 2:
            POS_TYPE[_idx] = 2
            POS_WEIGHT[_idx] = 6   # corners: hardest to attack, crit mass 2
        elif t == 3:
            POS_TYPE[_idx] = 1
            POS_WEIGHT[_idx] = 3   # edges: crit mass 3
        else:
            POS_TYPE[_idx] = 0
            POS_WEIGHT[_idx] = 1   # interior: easiest to attack, crit mass 4

CRITICAL = tuple(CRITICAL)
NEIGHBORS = tuple(NEIGHBORS)
POS_TYPE = tuple(POS_TYPE)
POS_WEIGHT = tuple(POS_WEIGHT)

# Strategic cell groups
CORNERS = (0, 6, 42, 48)
EDGES = tuple(i for i in range(SIZE) if POS_TYPE[i] == 1)
DIAGONAL_CORNER = {0: 48, 6: 42, 42: 6, 48: 0}
CORNER_ADJ_EDGES = {
    0: (1, 7),
    6: (5, 13),
    42: (35, 43),
    48: (41, 47),
}

# 2nd-ring edges (one step further from corner along border)
CORNER_2ND_RING = {
    0: (2, 14),
    6: (4, 20),
    42: (28, 44),
    48: (34, 46),
}


# ============================================================================
# Simulation – exact replica of the game engine's BFS chain-reaction logic
# ============================================================================
def simulate(counts, players, idx, pid):
    """Place an orb at idx for player pid.  Modifies counts/players in-place."""
    q = [idx]
    iters = 0
    while q:
        iters += 1
        if iters > 300:          # safety valve for infinite loops
            break
        nxt = []
        for ci in q:
            counts[ci] += 1
            players[ci] = pid
            if counts[ci] >= CRITICAL[ci]:
                counts[ci] = 0
                players[ci] = 0
                nxt.extend(NEIGHBORS[ci])
        q = nxt


# ============================================================================
# Fast terminal-state helpers
# ============================================================================
def count_players(players, pid, oid):
    """Return (my_cells, opp_cells) counts."""
    mc = oc = 0
    for p in players:
        if p == pid:
            mc += 1
        elif p == oid:
            oc += 1
    return mc, oc


def is_terminal(players, pid, oid, mn):
    if mn < 2:
        return False, 0
    mc, oc = count_players(players, pid, oid)
    if oc == 0 and mc > 0:
        return True, INF
    if mc == 0 and oc > 0:
        return True, -INF
    return False, 0


# ============================================================================
# Evaluation Function  (from pid's perspective)
#
# Components:
#   1. Territory  – cell count diff (losing all = losing)
#   2. Material   – total orb diff
#   3. Pressure   – cells at critical-1 (loaded guns)
#   4. Threats    – my loaded cells adjacent to enemy cells
#   5. Vulnerability – enemy loaded cells adjacent to my cells
#   6. Chain      – clusters of near-critical friendly cells (cascade power)
#   7. Stability  – my cells NOT adjacent to any enemy critical cell
#   8. Position   – corner > edge > interior
# ============================================================================
def evaluate(counts, players, pid, oid, mn):
    mc = oc = mo = oo = 0
    m_crit = o_crit = 0
    m_threat = o_threat = 0
    m_chain = o_chain = 0
    m_stable = o_stable = 0
    m_pos = o_pos = 0

    for idx in range(SIZE):
        p = players[idx]
        if p == 0:
            continue
        c = counts[idx]
        cm = CRITICAL[idx]
        is_crit = (c >= cm - 1)
        pw = POS_WEIGHT[idx]

        if p == pid:
            mo += c
            mc += 1
            m_pos += pw
            vulnerable = False
            if is_crit:
                m_crit += 1
                for ni in NEIGHBORS[idx]:
                    np_ = players[ni]
                    if np_ == oid:
                        m_threat += 1
                        if counts[ni] >= CRITICAL[ni] - 1:
                            m_chain += 2   # will cascade into enemy chain
                    elif np_ == pid and counts[ni] >= CRITICAL[ni] - 1:
                        m_chain += 1       # friendly chain potential
            # Check stability (not adjacent to any enemy critical cell)
            for ni in NEIGHBORS[idx]:
                if players[ni] == oid and counts[ni] >= CRITICAL[ni] - 1:
                    vulnerable = True
                    break
            if not vulnerable:
                m_stable += 1
        else:  # opponent
            oo += c
            oc += 1
            o_pos += pw
            vulnerable = False
            if is_crit:
                o_crit += 1
                for ni in NEIGHBORS[idx]:
                    np_ = players[ni]
                    if np_ == pid:
                        o_threat += 1
                        if counts[ni] >= CRITICAL[ni] - 1:
                            o_chain += 2
                    elif np_ == oid and counts[ni] >= CRITICAL[ni] - 1:
                        o_chain += 1
            for ni in NEIGHBORS[idx]:
                if players[ni] == pid and counts[ni] >= CRITICAL[ni] - 1:
                    vulnerable = True
                    break
            if not vulnerable:
                o_stable += 1

    # Terminal
    if mn >= 2:
        if oc == 0 and mc > 0:
            return INF
        if mc == 0 and oc > 0:
            return -INF

    s  = (mc - oc) * 12        # territory dominance
    s += (mo - oo) * 2         # material
    s += (m_crit - o_crit) * 8 # pressure (loaded guns)
    s += m_threat * 16         # offensive: my loaded → enemy cell
    s -= o_threat * 20         # defensive: enemy loaded → my cell (higher!)
    s += (m_chain - o_chain) * 9  # cascade potential
    s += (m_stable - o_stable) * 5  # stability (safe cells)
    s += (m_pos - o_pos) * 3   # positional quality
    return s


# ============================================================================
# Move Ordering with Killer Heuristic
# ============================================================================
_killer = {}   # depth -> [move1, move2]  (two killer slots per depth)


def _record_killer(depth, move):
    """Record a move that caused a beta cutoff at this depth."""
    if depth not in _killer:
        _killer[depth] = [move, -1]
    elif _killer[depth][0] != move:
        _killer[depth][1] = _killer[depth][0]
        _killer[depth][0] = move


def score_move(counts, players, idx, pid, oid, depth):
    c = counts[idx]
    cm = CRITICAL[idx]
    s = POS_WEIGHT[idx] * 8

    # Killer bonus
    if depth in _killer:
        if _killer[depth][0] == idx:
            s += 200
        elif _killer[depth][1] == idx:
            s += 150

    explodes = (c + 1 >= cm)

    if explodes:
        s += 350
        for ni in NEIGHBORS[idx]:
            if players[ni] == oid:
                s += 120          # capturing enemy cell
                if counts[ni] + 1 >= CRITICAL[ni]:
                    s += 70       # chain into enemy critical
            elif players[ni] == pid and counts[ni] + 1 >= CRITICAL[ni]:
                s += 40           # friendly chain cascade

    # Building pressure on own cells
    if players[idx] == pid:
        s += 10 + c * 5

    # Danger: feeding an enemy loaded cell that we can't counter-explode
    if not explodes:
        for ni in NEIGHBORS[idx]:
            if players[ni] == oid and counts[ni] >= CRITICAL[ni] - 1:
                s -= 60

    return s


def get_ordered_moves(counts, players, pid, oid, depth):
    moves = []
    for i in range(SIZE):
        p = players[i]
        if p == 0 or p == pid:
            moves.append((score_move(counts, players, i, pid, oid, depth), i))
    moves.sort(reverse=True)
    return [m[1] for m in moves]


# ============================================================================
# Transposition Table (simple hash → (depth, flag, score, best_move))
# ============================================================================
_tt = {}
_TT_EXACT = 0
_TT_ALPHA = 1
_TT_BETA = 2
_TT_MAX = 500000  # cap to avoid memory issues


def _board_key(counts, players, pid):
    return (tuple(counts), tuple(players), pid)


# ============================================================================
# Negamax + Alpha-Beta + PVS + LMR + Killers + TT
# ============================================================================
_node_count = 0
_timed_out = False


def negamax(counts, players, depth, alpha, beta, pid, oid, mn, deadline):
    global _node_count, _timed_out
    _node_count += 1

    # Time check every 1024 nodes
    if _node_count & 1023 == 0 and time.time() > deadline:
        _timed_out = True
        return 0, -1

    # Terminal?
    term, tv = is_terminal(players, pid, oid, mn)
    if term:
        return tv + (depth * 100 if tv > 0 else -depth * 100), -1

    # Leaf
    if depth <= 0:
        return evaluate(counts, players, pid, oid, mn), -1

    # TT probe
    key = _board_key(counts, players, pid)
    tt_move = -1
    if key in _tt:
        tt_depth, tt_flag, tt_score, tt_mv = _tt[key]
        if tt_depth >= depth:
            if tt_flag == _TT_EXACT:
                return tt_score, tt_mv
            elif tt_flag == _TT_BETA and tt_score >= beta:
                return tt_score, tt_mv
            elif tt_flag == _TT_ALPHA and tt_score <= alpha:
                return tt_score, tt_mv
        tt_move = tt_mv  # use for ordering even if depth insufficient

    moves = get_ordered_moves(counts, players, pid, oid, depth)
    if not moves:
        return evaluate(counts, players, pid, oid, mn), -1

    # Put TT best move first if available
    if tt_move >= 0 and tt_move in moves:
        moves.remove(tt_move)
        moves.insert(0, tt_move)

    # Adaptive width: limit branching at shallow remaining depth
    lim = len(moves)
    if depth == 1:
        lim = min(lim, 10)
    elif depth == 2:
        lim = min(lim, 16)

    orig_alpha = alpha
    best_val = -INF - 1
    best_move = moves[0]

    for i in range(min(lim, len(moves))):
        m = moves[i]
        nc = counts[:]
        np_ = players[:]
        simulate(nc, np_, m, pid)

        if i == 0:
            # PV node: full window
            v, _ = negamax(nc, np_, depth - 1, -beta, -alpha,
                           oid, pid, mn + 1, deadline)
            v = -v
        else:
            # Late Move Reduction
            reduction = 0
            if i >= 6 and depth >= 3:
                reduction = 1
            if i >= 12 and depth >= 4:
                reduction = 2

            # Null-window scout
            v, _ = negamax(nc, np_, depth - 1 - reduction,
                           -alpha - 1, -alpha, oid, pid, mn + 1, deadline)
            v = -v

            # Re-search if needed
            if not _timed_out and v > alpha and (v < beta or reduction > 0):
                v, _ = negamax(nc, np_, depth - 1, -beta, -alpha,
                               oid, pid, mn + 1, deadline)
                v = -v

        if _timed_out:
            if v > best_val:
                best_val = v
                best_move = m
            return best_val, best_move

        if v > best_val:
            best_val = v
            best_move = m

        if v > alpha:
            alpha = v

        if alpha >= beta:
            _record_killer(depth, m)
            break

    # TT store
    if len(_tt) < _TT_MAX:
        if best_val <= orig_alpha:
            flag = _TT_ALPHA
        elif best_val >= beta:
            flag = _TT_BETA
        else:
            flag = _TT_EXACT
        _tt[key] = (depth, flag, best_val, best_move)

    return best_val, best_move


# ============================================================================
# Opening Book  (corners → adjacent edges → 2nd ring edges)
# ============================================================================
def opening_move(counts, players, pid, oid, mn):
    # Move 0-1: grab corners
    if mn <= 1:
        # Counter opponent's corner with diagonal opposite
        for c in CORNERS:
            if players[c] != 0 and players[c] != pid:
                diag = DIAGONAL_CORNER[c]
                if players[diag] == 0 or players[diag] == pid:
                    return diag
        for c in CORNERS:
            if players[c] == 0 or players[c] == pid:
                return c

    # Moves 2-5: build edges adjacent to our corners
    if mn <= 5:
        my_corners = [c for c in CORNERS if players[c] == pid]
        if my_corners:
            # First fill immediate edges
            for c in my_corners:
                for e in CORNER_ADJ_EDGES[c]:
                    if players[e] == 0 or players[e] == pid:
                        return e
            # Then 2nd ring
            for c in my_corners:
                for e in CORNER_2ND_RING[c]:
                    if players[e] == 0 or players[e] == pid:
                        return e
        # Grab remaining corners
        for c in CORNERS:
            if players[c] == 0 or players[c] == pid:
                return c

    return None


# ============================================================================
# Instant Win / Instant Loss Detection
# ============================================================================
def find_instant_win(counts, players, pid, oid, mn):
    """Check if any single move wins the game outright."""
    if mn < 2:
        return None
    candidates = []
    for idx in range(SIZE):
        if (players[idx] == 0 or players[idx] == pid) and counts[idx] + 1 >= CRITICAL[idx]:
            # Only bother simulating if explosion touches an enemy cell
            touches_opp = False
            for ni in NEIGHBORS[idx]:
                if players[ni] == oid:
                    touches_opp = True
                    break
            if touches_opp:
                candidates.append(idx)

    for idx in candidates:
        nc = counts[:]
        np_ = players[:]
        simulate(nc, np_, idx, pid)
        if not any(p == oid for p in np_):
            return idx
    return None


def find_losing_moves(counts, players, pid, oid, mn):
    """Return set of opponent moves that would win instantly (so we can block)."""
    if mn < 2:
        return set()
    losing = set()
    for idx in range(SIZE):
        if (players[idx] == 0 or players[idx] == oid) and counts[idx] + 1 >= CRITICAL[idx]:
            touches_me = False
            for ni in NEIGHBORS[idx]:
                if players[ni] == pid:
                    touches_me = True
                    break
            if touches_me:
                nc = counts[:]
                np_ = players[:]
                simulate(nc, np_, idx, oid)
                if not any(p == pid for p in np_):
                    losing.add(idx)
    return losing


def find_block_move(counts, players, pid, oid, mn, losing_moves):
    """If opponent has instant-win moves, try to find a move that blocks ALL."""
    if not losing_moves:
        return None

    # Strategy: find a move of ours that, after we play it, removes all
    # opponent instant-win possibilities.
    legal = [i for i in range(SIZE) if players[i] == 0 or players[i] == pid]

    # Sort by heuristic: prefer explosive moves near the threat
    def block_score(idx):
        s = score_move(counts, players, idx, pid, oid, 0)
        for lm in losing_moves:
            for ni in NEIGHBORS[lm]:
                if ni == idx:
                    s += 50
        return s

    legal.sort(key=block_score, reverse=True)

    for idx in legal[:20]:  # only check top candidates for speed
        nc = counts[:]
        np_ = players[:]
        simulate(nc, np_, idx, pid)
        # Check if opponent still has any instant win
        still_loses = False
        for opp_move in range(SIZE):
            if (np_[opp_move] == 0 or np_[opp_move] == oid) and nc[opp_move] + 1 >= CRITICAL[opp_move]:
                touches = False
                for ni in NEIGHBORS[opp_move]:
                    if np_[ni] == pid:
                        touches = True
                        break
                if touches:
                    nc2 = nc[:]
                    np2 = np_[:]
                    simulate(nc2, np2, opp_move, oid)
                    if not any(p == pid for p in np2):
                        still_loses = True
                        break
        if not still_loses:
            return idx

    # If no perfect block, return the best heuristic move (search will handle)
    return None


# ============================================================================
# Time Management for 60-second total bank
#
# Philosophy: be VERY stingy. A typical game lasts 30-80 moves.
# Early game: use opening book (free). Mid-game: ~0.8-1.5s. Late: <0.3s.
# ============================================================================
def compute_deadline(my_time, move_num):
    # Estimate remaining moves (heuristic)
    if move_num < 6:
        est_remaining = 40
    elif move_num < 20:
        est_remaining = 30
    else:
        est_remaining = max(15, 50 - move_num)

    # Target time per move: leave a 3-second buffer
    safe_time = max(my_time - 3.0, my_time * 0.15)
    target = safe_time / est_remaining

    # Clamp
    if my_time > 40:
        target = min(target, 1.8)
    elif my_time > 20:
        target = min(target, 1.0)
    elif my_time > 10:
        target = min(target, 0.5)
    elif my_time > 5:
        target = min(target, 0.25)
    else:
        target = min(target, 0.10)

    target = max(target, 0.03)  # absolute minimum

    return time.time() + target


# ============================================================================
# Main Decision Engine
# ============================================================================
def get_best_move(counts, players, my_id, opp_id, move_num, my_time):
    global _node_count, _timed_out, _tt, _killer

    # Clear TT and killers each turn (positions change completely)
    _tt = {}
    _killer = {}

    # 1. Instant win?
    win = find_instant_win(counts, players, my_id, opp_id, move_num)
    if win is not None:
        return win

    # 2. Opponent about to win? Try to block.
    losing = find_losing_moves(counts, players, my_id, opp_id, move_num)
    if losing:
        block = find_block_move(counts, players, my_id, opp_id, move_num, losing)
        if block is not None:
            return block
        # If no clean block, search will naturally prioritize survival

    # 3. Opening book (essentially free, no time spent)
    if move_num <= 5:
        om = opening_move(counts, players, my_id, opp_id, move_num)
        if om is not None:
            return om

    # 4. Iterative deepening with time control
    deadline = compute_deadline(my_time, move_num)

    best_move = None
    best_score = -INF - 1

    for depth in range(1, 30):
        _node_count = 0
        _timed_out = False

        score, move = negamax(counts, players, depth, -INF - 1, INF + 1,
                              my_id, opp_id, move_num, deadline)

        if not _timed_out and move >= 0:
            best_move = move
            best_score = score
        elif _timed_out and move >= 0 and best_move is None:
            best_move = move

        if _timed_out or time.time() > deadline:
            break
        if best_score > INF - 10000:  # found forced win
            break

    # 5. Fallback
    if best_move is None:
        moves = get_ordered_moves(counts, players, my_id, opp_id, 0)
        if moves:
            best_move = moves[0]

    return best_move


# ============================================================================
# I/O — identical to original interface
# ============================================================================
def play_move(row, col):
    print(f"{row} {col}", flush=True)


# Main game loop with crash protection
while True:
    try:
        line = input()
        state = json.loads(line)

        counts = [0] * SIZE
        players = [0] * SIZE
        for i, row in enumerate(state['board']):
            for j, cell in enumerate(row):
                idx = i * COLS + j
                counts[idx] = cell[0]
                players[idx] = cell[1]

        my_id = state['player']
        opp_id = 2 if my_id == 1 else 1
        move_num = state.get('move_number', 0)
        my_time = state.get('my_time', 60.0)

        best = get_best_move(counts, players, my_id, opp_id, move_num, my_time)
        if best is None:
            # Emergency: play first legal move
            for i in range(SIZE):
                if players[i] == 0 or players[i] == my_id:
                    best = i
                    break
        r, c = divmod(best, COLS)
        play_move(r, c)
    except EOFError:
        break
    except Exception:
        # Last resort: never crash, play cell 0,0 or first legal
        try:
            for i in range(SIZE):
                if players[i] == 0 or players[i] == my_id:
                    r, c = divmod(i, COLS)
                    play_move(r, c)
                    break
            else:
                play_move(0, 0)
        except Exception:
            play_move(0, 0)
