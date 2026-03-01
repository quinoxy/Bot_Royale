import json
import time
import random
from enum import Enum

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2


class BoardCell:
    __slots__ = ("player", "count")

    def __init__(self):
        self.player = Player.NONE
        self.count = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))

# V(s) heuristic weights
W1 = 2.0    # ΔA  – atom difference
W2 = 6.0    # ΔC  – critical-cell difference (raised — critical mass IS the game)
W3 = 4.0    # S_cluster – cluster stability (super-linear)
W4 = 8.0    # T(i) – threat / vulnerability penalty (DOUBLED — #1 cause of losses)
W5 = 1.5    # E(j) – opponent entropy
W6 = 3.5    # Corner/edge ownership bonus
W7 = 3.0    # Chain potential (TRIPLED — captures are the whole point)
W8 = 7.0    # Edge chain continuity (NEAR DOUBLED — edge sweeps win games)
W9 = 3.0    # Territorial dominance
W10 = 7.0   # Corner control premium (raised — corners = chain-reaction engines)

# Search tuning
MAX_DEPTH = 5
QUIESCENCE_DEPTH = 3
TIME_FRACTION = 0.08
TIME_CAP = 1.5
LMR_THRESHOLD = 3     # moves beyond this index get reduced-depth search
LMR_REDUCTION = 1     # reduce by this many plies

WIN_SCORE = 100000

# ---------------------------------------------------------------------------
# Zobrist Hashing
# ---------------------------------------------------------------------------

_zobrist_table = None
_zobrist_turn = 0


def _init_zobrist(rows: int, cols: int):
    global _zobrist_table, _zobrist_turn
    random.seed(42)  # deterministic for reproducibility
    # [row][col][player 0..2][count 0..4]
    _zobrist_table = [
        [
            [[random.getrandbits(64) for _ in range(5)]
             for _ in range(3)]
            for _ in range(cols)
        ]
        for _ in range(rows)
    ]
    _zobrist_turn = random.getrandbits(64)


def _compute_hash(board) -> int:
    h = 0
    for i in range(board.rows):
        for j in range(board.cols):
            cell = board.board[i][j]
            h ^= _zobrist_table[i][j][cell.player.value][cell.count]
    return h


# ---------------------------------------------------------------------------
# Transposition Table
# ---------------------------------------------------------------------------

TT_EXACT = 0
TT_LOWER = 1   # alpha (fail-high)
TT_UPPER = 2   # beta  (fail-low)

_tt: dict[int, tuple[int, float, int, tuple[int, int] | None]] = {}
# key -> (depth, score, flag, best_move)

TT_MAX_SIZE = 500_000


def _tt_store(key: int, depth: int, score: float, flag: int,
              best_move: tuple[int, int] | None):
    if len(_tt) > TT_MAX_SIZE:
        _tt.clear()
    _tt[key] = (depth, score, flag, best_move)


def _tt_probe(key: int, depth: int, alpha: float, beta: float):
    """Returns (hit: bool, score: float, best_move)"""
    entry = _tt.get(key)
    if entry is None:
        return False, 0.0, None
    e_depth, e_score, e_flag, e_move = entry
    if e_depth >= depth:
        if e_flag == TT_EXACT:
            return True, e_score, e_move
        if e_flag == TT_LOWER and e_score >= beta:
            return True, e_score, e_move
        if e_flag == TT_UPPER and e_score <= alpha:
            return True, e_score, e_move
    return False, 0.0, e_move   # return best_move even on miss for ordering


# ---------------------------------------------------------------------------
# Killer / History Tables
# ---------------------------------------------------------------------------

_killer_moves: list[list[tuple[int, int] | None]] = []
_history_table: dict[tuple[int, int, int], int] = {}   # (player, r, c) -> score


def _init_search_tables(max_depth: int):
    global _killer_moves, _history_table
    _killer_moves = [[None, None] for _ in range(max_depth + QUIESCENCE_DEPTH + 2)]
    _history_table.clear()


def _record_killer(depth: int, move: tuple[int, int]):
    if depth < len(_killer_moves):
        if _killer_moves[depth][0] != move:
            _killer_moves[depth][1] = _killer_moves[depth][0]
            _killer_moves[depth][0] = move


def _record_history(player: Player, move: tuple[int, int], depth: int):
    key = (player.value, move[0], move[1])
    _history_table[key] = _history_table.get(key, 0) + depth * depth


# ---------------------------------------------------------------------------
# Time management
# ---------------------------------------------------------------------------

_search_deadline: float = 0.0


def _is_time_up() -> bool:
    return time.time() >= _search_deadline


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

class Board:
    def __init__(self, line=None):
        if line is not None:
            state = json.loads(line)
            self.rows: int = state["rows"]
            self.cols: int = state["cols"]
            self.my_time: float = state["my_time"]
            self.opp_time: float = state["opp_time"]
            self.me: int = state["player"]
            self.move_number: int = state.get("move_number", 0)
            self.board = [[BoardCell() for _ in range(self.cols)]
                          for _ in range(self.rows)]
            for i, row in enumerate(state["board"]):
                for j, cell_data in enumerate(row):
                    self.board[i][j].count = cell_data[0]
                    self.board[i][j].player = Player(cell_data[1])
            self._cap = [[self._compute_cap(i, j)
                          for j in range(self.cols)]
                         for i in range(self.rows)]
            # Initialise Zobrist on first board
            global _zobrist_table
            if _zobrist_table is None:
                _init_zobrist(self.rows, self.cols)

    def _compute_cap(self, x: int, y: int) -> int:
        c = 4
        if x == 0 or x == self.rows - 1:
            c -= 1
        if y == 0 or y == self.cols - 1:
            c -= 1
        return c

    def copy(self):
        nb = Board.__new__(Board)
        nb.rows = self.rows
        nb.cols = self.cols
        nb.my_time = self.my_time
        nb.opp_time = self.opp_time
        nb.me = self.me
        nb.move_number = self.move_number
        nb._cap = self._cap
        nb.board = [[BoardCell() for _ in range(self.cols)]
                    for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(self.cols):
                nb.board[i][j].player = self.board[i][j].player
                nb.board[i][j].count = self.board[i][j].count
        return nb

    def checkValidCell(self, x: int, y: int) -> bool:
        return 0 <= x < self.rows and 0 <= y < self.cols

    def getCapacity(self, x: int, y: int) -> int:
        return self._cap[x][y]

    def cellExploding(self, x: int, y: int) -> bool:
        if not self.checkValidCell(x, y):
            return False
        return self.board[x][y].count >= self._cap[x][y]

    def isCritical(self, x: int, y: int) -> bool:
        cell = self.board[x][y]
        return cell.player != Player.NONE and cell.count == self._cap[x][y] - 1

    # -- simulation -------------------------------------------------------

    def makeMove(self, x: int, y: int, player: Player) -> bool:
        if player == Player.NONE:
            return False
        if not (0 <= x < self.rows and 0 <= y < self.cols):
            return False
        if self.board[x][y].player != Player.NONE and self.board[x][y].player != player:
            return False

        queue = [(x, y)]
        safety = 200
        rows, cols, cap, board = self.rows, self.cols, self._cap, self.board

        while queue and safety > 0:
            safety -= 1
            nxt: list[tuple[int, int]] = []
            for tx, ty in queue:
                cell = board[tx][ty]
                cell.count += 1
                cell.player = player
                if cell.count >= cap[tx][ty]:
                    cell.count = 0
                    cell.player = Player.NONE
                    for dx, dy in DIRECTIONS:
                        nx, ny = tx + dx, ty + dy
                        if 0 <= nx < rows and 0 <= ny < cols:
                            nxt.append((nx, ny))
            queue = nxt
        return True

    # -- queries ----------------------------------------------------------

    def isTerminal(self, move_counter: int) -> bool:
        if move_counter < 2:
            return False
        has_red = has_blue = False
        for i in range(self.rows):
            for j in range(self.cols):
                p = self.board[i][j].player
                if p == Player.RED:
                    has_red = True
                elif p == Player.BLUE:
                    has_blue = True
                if has_red and has_blue:
                    return False
        return True

    def getWinner(self) -> Player:
        has_red = has_blue = False
        for i in range(self.rows):
            for j in range(self.cols):
                p = self.board[i][j].player
                if p == Player.RED:
                    has_red = True
                elif p == Player.BLUE:
                    has_blue = True
        if has_red and not has_blue:
            return Player.RED
        if has_blue and not has_red:
            return Player.BLUE
        return Player.NONE

    def getLegalMoves(self, player: Player) -> list[tuple[int, int]]:
        moves: list[tuple[int, int]] = []
        for i in range(self.rows):
            for j in range(self.cols):
                p = self.board[i][j].player
                if p == Player.NONE or p == player:
                    moves.append((i, j))
        return moves

    # ===================================================================
    # V(s) — Advanced Heuristic Evaluation (SINGLE-PASS OPTIMISED)
    # ===================================================================

    def evaluate(self, player: Player, is_opponent_turn: bool = False) -> float:
        """
        Unified evaluation: threat, entropy, corner control, territorial
        dominance, and basic stats all computed in ONE board scan.
        Only cluster stability + edge chains need a separate BFS pass.
        """
        opponent = Player.RED if player == Player.BLUE else Player.BLUE
        rows, cols, board, cap = self.rows, self.cols, self.board, self._cap
        NONE = Player.NONE

        my_atoms = opp_atoms = 0
        my_critical = opp_critical = 0
        my_cells = opp_cells = 0
        my_corner_edge = opp_corner_edge = 0
        chain_potential = 0.0
        threat_penalty = 0.0
        opp_entropy = 0.0
        corner_score = 0.0

        # Territorial dominance accumulators: [row0, row_last] / [col0, col_last]
        er_my0 = er_my1 = er_op0 = er_op1 = 0
        ec_my0 = ec_my1 = ec_op0 = ec_op1 = 0

        amp = 2.5 if is_opponent_turn else 1.0
        last_r = rows - 1
        last_c = cols - 1

        for i in range(rows):
            row = board[i]
            cap_row = cap[i]
            i_is_0 = (i == 0)
            i_is_last = (i == last_r)
            for j in range(cols):
                cell = row[j]
                p = cell.player
                if p == NONE:
                    continue
                cnt = cell.count
                c = cap_row[j]
                is_crit = (cnt == c - 1)

                if p == player:
                    my_atoms += cnt
                    my_cells += 1
                    if is_crit:
                        my_critical += 1
                        # Chain potential
                        for dx, dy in DIRECTIONS:
                            nx, ny = i + dx, j + dy
                            if 0 <= nx < rows and 0 <= ny < cols:
                                nb = board[nx][ny]
                                if nb.player == opponent:
                                    chain_potential += nb.count
                    if c <= 3:
                        my_corner_edge += (4 - c)
                    # Threat: adjacent to opponent critical?
                    # BUT only for non-critical cells — our critical cells
                    # next to opponent are KILL SHOTS, not vulnerabilities!
                    if not is_crit:
                        for dx, dy in DIRECTIONS:
                            nx, ny = i + dx, j + dy
                            if (0 <= nx < rows and 0 <= ny < cols
                                    and board[nx][ny].player == opponent
                                    and board[nx][ny].count == cap[nx][ny] - 1):
                                threat_penalty += cnt * amp
                                break
                    # Territorial
                    if i_is_0:    er_my0 += 1
                    if i_is_last: er_my1 += 1
                    if j == 0:    ec_my0 += 1
                    if j == last_c: ec_my1 += 1
                    # Corner control
                    if c == 2:
                        corner_score += 3.0
                        if cnt == 1:
                            corner_score += 2.0

                else:  # opponent
                    opp_atoms += cnt
                    opp_cells += 1
                    if is_crit:
                        opp_critical += 1
                        # Entropy
                        for dx, dy in DIRECTIONS:
                            nx, ny = i + dx, j + dy
                            if 0 <= nx < rows and 0 <= ny < cols:
                                nb = board[nx][ny]
                                if nb.player == NONE:
                                    opp_entropy += 1.0
                                elif nb.player == player:
                                    opp_entropy -= 0.5
                    if c <= 3:
                        opp_corner_edge += (4 - c)
                    # Territorial
                    if i_is_0:    er_op0 += 1
                    if i_is_last: er_op1 += 1
                    if j == 0:    ec_op0 += 1
                    if j == last_c: ec_op1 += 1
                    # Corner control
                    if c == 2:
                        corner_score -= 3.0
                        if cnt == 1:
                            corner_score -= 2.0

        # Terminal shortcuts
        if my_cells == 0 and self.move_number >= 2:
            return -WIN_SCORE
        if opp_cells == 0 and self.move_number >= 2:
            return WIN_SCORE

        # Territorial dominance (computed from accumulators)
        terr_dom = 0.0
        thresh_c = cols * 0.6
        thresh_r = rows * 0.6
        for mc, oc in ((er_my0, er_op0), (er_my1, er_op1)):
            if oc >= thresh_c: terr_dom -= oc * 2.0
            if mc >= thresh_c: terr_dom += mc * 2.0
            terr_dom += (mc - oc) * 0.5
        for mc, oc in ((ec_my0, ec_op0), (ec_my1, ec_op1)):
            if oc >= thresh_r: terr_dom -= oc * 2.0
            if mc >= thresh_r: terr_dom += mc * 2.0
            terr_dom += (mc - oc) * 0.5

        # BFS passes (cluster stability + edge chains) — computed together
        s_cluster, edge_chain = self._bfs_scores(player, opponent)

        return (W1 * (my_atoms - opp_atoms)
                + W2 * (my_critical - opp_critical)
                + W3 * s_cluster
                - W4 * threat_penalty
                + W5 * opp_entropy
                + W6 * (my_corner_edge - opp_corner_edge)
                + W7 * chain_potential
                + W8 * edge_chain
                + W9 * terr_dom
                + W10 * corner_score)

    # -- Combined BFS for cluster stability + edge chains ----------------

    def _bfs_scores(self, player: Player, opponent: Player) -> tuple[float, float]:
        """
        Single traversal that computes:
          - cluster stability (contiguous critical-cell clusters, size²)
          - edge chain bonus (contiguous edge cells, size³, corner ×1.5)
        for both players, returning (cluster_my, edge_my - edge_opp).
        """
        rows, cols, board, cap = self.rows, self.cols, self.board, self._cap
        last_r, last_c = rows - 1, cols - 1

        # -- Cluster stability (player only — main value) ----
        vis_c = [[False] * cols for _ in range(rows)]
        cluster_total = 0.0
        for i in range(rows):
            for j in range(cols):
                if vis_c[i][j]:
                    continue
                cell = board[i][j]
                if cell.player != player or cell.count != cap[i][j] - 1:
                    continue
                size = 0
                stk = [(i, j)]
                vis_c[i][j] = True
                while stk:
                    cx, cy = stk.pop()
                    size += 1
                    for dx, dy in DIRECTIONS:
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < rows and 0 <= ny < cols
                                and not vis_c[nx][ny]
                                and board[nx][ny].player == player
                                and board[nx][ny].count == cap[nx][ny] - 1):
                            vis_c[nx][ny] = True
                            stk.append((nx, ny))
                cluster_total += size * size

        # -- Edge chain bonus (both players in one scan) ----
        vis_e = [[False] * cols for _ in range(rows)]
        edge_my = edge_opp = 0.0
        for i in range(rows):
            for j in range(cols):
                if vis_e[i][j]:
                    continue
                if not (i == 0 or i == last_r or j == 0 or j == last_c):
                    continue
                cell = board[i][j]
                owner = cell.player
                if owner != player and owner != opponent:
                    continue
                size = 0
                has_corner = False
                stk = [(i, j)]
                vis_e[i][j] = True
                while stk:
                    cx, cy = stk.pop()
                    size += 1
                    if cap[cx][cy] == 2:
                        has_corner = True
                    for dx, dy in DIRECTIONS:
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < rows and 0 <= ny < cols
                                and not vis_e[nx][ny]
                                and (nx == 0 or nx == last_r
                                     or ny == 0 or ny == last_c)
                                and board[nx][ny].player == owner):
                            vis_e[nx][ny] = True
                            stk.append((nx, ny))
                bonus = size * size * size
                if has_corner:
                    bonus *= 1.5
                if owner == player:
                    edge_my += bonus
                else:
                    edge_opp += bonus

        return cluster_total, edge_my - edge_opp

    def isVolatile(self) -> bool:
        rows, cols, board, cap = self.rows, self.cols, self.board, self._cap
        count = 0
        for i in range(rows):
            for j in range(cols):
                cell = board[i][j]
                if cell.player == Player.NONE or cell.count != cap[i][j] - 1:
                    continue
                for dx, dy in DIRECTIONS:
                    nx, ny = i + dx, j + dy
                    if (0 <= nx < rows and 0 <= ny < cols
                            and board[nx][ny].player != Player.NONE
                            and board[nx][ny].player != cell.player
                            and board[nx][ny].count == cap[nx][ny] - 1):
                        count += 1
                        if count >= 2:
                            return True
        return False


# ======================================================================
# Move Ordering (with killer + history + TT move)
# ======================================================================

def _order_moves(board: Board,
                 moves: list[tuple[int, int]],
                 player: Player,
                 depth: int = 0,
                 tt_move: tuple[int, int] | None = None) -> list[tuple[int, int]]:
    opponent = Player.RED if player == Player.BLUE else Player.BLUE
    brd = board.board
    cap = board._cap
    rows, cols = board.rows, board.cols

    opp_crit: set[tuple[int, int]] = set()
    for i in range(rows):
        for j in range(cols):
            if brd[i][j].player == opponent and brd[i][j].count == cap[i][j] - 1:
                opp_crit.add((i, j))

    killers = set()
    if depth < len(_killer_moves):
        for k in _killer_moves[depth]:
            if k is not None:
                killers.add(k)

    def _key(move: tuple[int, int]) -> tuple[int, int]:
        x, y = move

        # TT best move always first
        if move == tt_move:
            return (-10, 0)

        cell = brd[x][y]
        cell_cap = cap[x][y]
        will_explode = (cell.count + 1 >= cell_cap)

        adj_oc = 0
        for dx, dy in DIRECTIONS:
            if (x + dx, y + dy) in opp_crit:
                adj_oc += 1

        # 0 – Kill shots
        if will_explode and adj_oc > 0:
            return (0, -adj_oc)

        # Killer moves get priority
        if move in killers:
            return (1, 0)

        # 2 – Threat neutralisation
        if will_explode and cell.player == player:
            for dx, dy in DIRECTIONS:
                if (x + dx, y + dy) in opp_crit:
                    return (2, -cell.count)

        near = any(abs(x - ox) + abs(y - oy) < 2 for ox, oy in opp_crit)

        is_edge = (x == 0 or x == rows - 1 or y == 0 or y == cols - 1)
        is_corner = (x == 0 or x == rows - 1) and (y == 0 or y == cols - 1)

        # Edge connectivity bonus: edge move adjacent to our own edge cell
        my_edge_adj = 0
        if is_edge or is_corner:
            for dx, dy in DIRECTIONS:
                nx, ny = x + dx, y + dy
                if (0 <= nx < rows and 0 <= ny < cols
                        and brd[nx][ny].player == player
                        and (nx == 0 or nx == rows - 1
                             or ny == 0 or ny == cols - 1)):
                    my_edge_adj += 1

        # 3 – Corner grab (corners are chain engines — high priority)
        if is_corner and not near:
            return (2, -5 - my_edge_adj)

        # 3b – Edge expansion connected to our chain
        if is_edge and not near and my_edge_adj > 0:
            return (3, -my_edge_adj)

        # 3c – Safe edge expansion (unconnected)
        if is_edge and not near:
            return (3, 0)

        # 6 – Suicide
        if adj_oc > 0 and not will_explode:
            return (6, adj_oc)

        # 4/5 – Quiet moves, ordered by history heuristic
        hist = _history_table.get((player.value, x, y), 0)
        return (4, -hist)

    return sorted(moves, key=_key)


# ======================================================================
# Opening Theory — OPPOSITE Edge Strategy
# ======================================================================
#
# VINTAGE's strategy: claim an entire edge row using corners as chain-
# reaction engines (cap 2 → cheapest bomb).
#
# COUNTER: Build on the OPPOSITE edge. NEVER contest their edge.
# Their explosions hit empty space in the middle, while our edge chain
# is safe and ready to counter-sweep.
#
# Contesting their edge = giving them free atom captures.
# Building opposite = safe chain that sweeps from the other side.
# ======================================================================

def _opening_move(board: Board, player: Player):
    opponent = Player.RED if player == Player.BLUE else Player.BLUE
    mn = board.move_number
    rows, cols = board.rows, board.cols
    brd = board.board
    cap = board._cap

    # Hand off to search after ~7 moves per side
    if mn > 14:
        return None

    # --- Move 1: Grab a corner far from opponent ---
    if mn <= 1:
        # Try bottom corners first (opponent typically starts top)
        for r, c in [(rows - 1, cols - 1), (rows - 1, 0),
                     (0, cols - 1), (0, 0)]:
            cell = brd[r][c]
            if cell.player == Player.NONE or cell.player == player:
                return (r, c)

    # --- Detect opponent's dominant edge ---
    edge_counts: dict[str, int] = {}
    for i in range(rows):
        for j in range(cols):
            if brd[i][j].player != opponent:
                continue
            if i == 0:
                edge_counts['r0'] = edge_counts.get('r0', 0) + 1
            if i == rows - 1:
                edge_counts['rN'] = edge_counts.get('rN', 0) + 1
            if j == 0:
                edge_counts['c0'] = edge_counts.get('c0', 0) + 1
            if j == cols - 1:
                edge_counts['cN'] = edge_counts.get('cN', 0) + 1

    # --- Determine our target edge (OPPOSITE to opponent) ---
    opposites = {'r0': 'rN', 'rN': 'r0', 'c0': 'cN', 'cN': 'c0'}
    if edge_counts:
        opp_dominant = max(edge_counts, key=edge_counts.get)
        primary = opposites[opp_dominant]
        # Also consider perpendicular edges as secondary
        if opp_dominant in ('r0', 'rN'):
            secondaries = ['c0', 'cN']
        else:
            secondaries = ['r0', 'rN']
    else:
        # Opponent not on perimeter — default to bottom row
        primary = 'rN'
        secondaries = ['cN', 'c0']

    # --- Collect candidate cells (our edges, NOT opponent's edge) ---
    opp_edge_cells: set[tuple[int, int]] = set()
    if edge_counts:
        opp_dom = max(edge_counts, key=edge_counts.get)
        if opp_dom == 'r0':
            opp_edge_cells = {(0, j) for j in range(cols)}
        elif opp_dom == 'rN':
            opp_edge_cells = {(rows - 1, j) for j in range(cols)}
        elif opp_dom == 'c0':
            opp_edge_cells = {(i, 0) for i in range(rows)}
        elif opp_dom == 'cN':
            opp_edge_cells = {(i, cols - 1) for i in range(rows)}

    def _edge_cells(key: str) -> list[tuple[int, int]]:
        if key == 'r0':  return [(0, j) for j in range(cols)]
        if key == 'rN':  return [(rows - 1, j) for j in range(cols)]
        if key == 'c0':  return [(i, 0) for i in range(rows)]
        if key == 'cN':  return [(i, cols - 1) for i in range(rows)]
        return []

    candidates: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for cell_rc in _edge_cells(primary):
        if cell_rc not in opp_edge_cells and cell_rc not in seen:
            candidates.append(cell_rc)
            seen.add(cell_rc)
    for sec in secondaries:
        for cell_rc in _edge_cells(sec):
            if cell_rc not in opp_edge_cells and cell_rc not in seen:
                candidates.append(cell_rc)
                seen.add(cell_rc)

    # --- Score candidates ---
    best, best_sc = None, float('-inf')
    for r, c in candidates:
        cell = brd[r][c]
        if cell.player != Player.NONE and cell.player != player:
            continue

        sc = 0.0

        # Corners are chain-reaction engines (cap 2 = cheapest bomb)
        if cap[r][c] == 2:
            sc += 25
        elif cap[r][c] == 3:
            sc += 10

        # On primary target edge → preferred
        is_primary = False
        if primary == 'r0' and r == 0:          is_primary = True
        elif primary == 'rN' and r == rows - 1: is_primary = True
        elif primary == 'c0' and c == 0:        is_primary = True
        elif primary == 'cN' and c == cols - 1: is_primary = True
        if is_primary:
            sc += 6

        # Adjacent to our existing cells → extends our chain
        for dx, dy in DIRECTIONS:
            nx, ny = r + dx, c + dy
            if 0 <= nx < rows and 0 <= ny < cols:
                nb = brd[nx][ny]
                if nb.player == player:
                    sc += 8
                elif (nb.player == opponent
                      and nb.count == cap[nx][ny] - 1):
                    sc -= 20  # NEVER place next to opponent critical!

        # Stacking on our own cell (builds toward critical mass)
        if cell.player == player:
            sc += 4

        if sc > best_sc:
            best_sc = sc
            best = (r, c)

    return best


# ======================================================================
# Quiescence Search
# ======================================================================

def _quiescence(board: Board, alpha: float, beta: float,
                maximizing: bool, player: Player,
                move_counter: int, q_depth: int) -> float:
    opponent = Player.RED if player == Player.BLUE else Player.BLUE
    current = player if maximizing else opponent

    stand_pat = board.evaluate(player, is_opponent_turn=not maximizing)

    if board.isTerminal(move_counter):
        w = board.getWinner()
        if w == player:
            return WIN_SCORE
        if w == opponent:
            return -WIN_SCORE
        return 0

    if q_depth <= 0 or _is_time_up():
        return stand_pat

    # Collect explosion-triggering moves AND forced responses
    explosive: list[tuple[int, int]] = []
    brd, cap = board.board, board._cap
    for i in range(board.rows):
        for j in range(board.cols):
            cell = brd[i][j]
            if ((cell.player == Player.NONE or cell.player == current)
                    and cell.count + 1 >= cap[i][j]):
                explosive.append((i, j))

    if not explosive:
        return stand_pat

    if maximizing:
        if stand_pat >= beta:
            return beta
        alpha = max(alpha, stand_pat)
        for move in explosive:
            nb = board.copy()
            nb.makeMove(move[0], move[1], current)
            nb.move_number = move_counter + 1
            score = _quiescence(nb, alpha, beta, False, player,
                                move_counter + 1, q_depth - 1)
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return alpha
    else:
        if stand_pat <= alpha:
            return alpha
        beta = min(beta, stand_pat)
        for move in explosive:
            nb = board.copy()
            nb.makeMove(move[0], move[1], current)
            nb.move_number = move_counter + 1
            score = _quiescence(nb, alpha, beta, True, player,
                                move_counter + 1, q_depth - 1)
            if score < beta:
                beta = score
            if alpha >= beta:
                break
        return beta


# ======================================================================
# Minimax + Alpha-Beta + TT + Killers + LMR + Quiescence
# ======================================================================

def _minimax(board: Board, depth: int,
             alpha: float, beta: float,
             maximizing: bool, player: Player,
             move_counter: int,
             ply: int = 0) -> tuple[float, tuple[int, int] | None]:
    opponent = Player.RED if player == Player.BLUE else Player.BLUE
    current = player if maximizing else opponent

    # Terminal?
    if board.isTerminal(move_counter):
        w = board.getWinner()
        if w == player:
            return WIN_SCORE, None
        if w == opponent:
            return -WIN_SCORE, None
        return 0, None

    if _is_time_up():
        return board.evaluate(player, is_opponent_turn=not maximizing), None

    # --- Transposition Table probe ---
    z_hash = _compute_hash(board)
    # Encode whose turn it is
    if not maximizing:
        z_hash ^= _zobrist_turn

    tt_hit, tt_score, tt_move = _tt_probe(z_hash, depth, alpha, beta)
    if tt_hit:
        return tt_score, tt_move

    # Depth exhausted → quiescence or static eval
    if depth <= 0:
        if board.isVolatile():
            score = _quiescence(board, alpha, beta, maximizing,
                                player, move_counter, QUIESCENCE_DEPTH)
            return score, None
        return board.evaluate(player, is_opponent_turn=not maximizing), None

    legal = board.getLegalMoves(current)
    if not legal:
        return board.evaluate(player, is_opponent_turn=not maximizing), None

    # ---- Move Ordering (with TT move, killers, history) ----
    legal = _order_moves(board, legal, current, ply, tt_move)
    best_move = legal[0]
    orig_alpha = alpha

    if maximizing:
        max_eval = float("-inf")
        for idx, move in enumerate(legal):
            nb = board.copy()
            nb.makeMove(move[0], move[1], current)
            nb.move_number = move_counter + 1

            # Late Move Reduction: reduce depth for quiet moves
            reduction = 0
            if (idx >= LMR_THRESHOLD and depth >= 3
                    and not nb.isVolatile()):
                reduction = LMR_REDUCTION

            score, _ = _minimax(nb, depth - 1 - reduction, alpha, beta,
                                False, player, move_counter + 1, ply + 1)

            # Re-search at full depth if reduced search beats alpha
            if reduction > 0 and score > alpha:
                score, _ = _minimax(nb, depth - 1, alpha, beta,
                                    False, player, move_counter + 1, ply + 1)

            if score > max_eval:
                max_eval = score
                best_move = move
            alpha = max(alpha, score)
            if beta <= alpha:
                _record_killer(ply, move)
                _record_history(current, move, depth)
                break

        # Store in TT
        if max_eval <= orig_alpha:
            flag = TT_UPPER
        elif max_eval >= beta:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        _tt_store(z_hash, depth, max_eval, flag, best_move)

        return max_eval, best_move
    else:
        min_eval = float("inf")
        for idx, move in enumerate(legal):
            nb = board.copy()
            nb.makeMove(move[0], move[1], current)
            nb.move_number = move_counter + 1

            reduction = 0
            if (idx >= LMR_THRESHOLD and depth >= 3
                    and not nb.isVolatile()):
                reduction = LMR_REDUCTION

            score, _ = _minimax(nb, depth - 1 - reduction, alpha, beta,
                                True, player, move_counter + 1, ply + 1)

            if reduction > 0 and score < beta:
                score, _ = _minimax(nb, depth - 1, alpha, beta,
                                    True, player, move_counter + 1, ply + 1)

            if score < min_eval:
                min_eval = score
                best_move = move
            beta = min(beta, score)
            if beta <= alpha:
                _record_killer(ply, move)
                _record_history(current, move, depth)
                break

        if min_eval >= beta:
            flag = TT_LOWER
        elif min_eval <= orig_alpha:
            flag = TT_UPPER
        else:
            flag = TT_EXACT
        _tt_store(z_hash, depth, min_eval, flag, best_move)

        return min_eval, best_move


# ======================================================================
# Top-level: iterative deepening with time management
# ======================================================================

def getBestMove(board: Board, max_depth: int = MAX_DEPTH):
    global _search_deadline
    player = Player.RED if board.me == 1 else Player.BLUE

    # 1) Opening book
    opening = _opening_move(board, player)
    if opening is not None:
        return opening

    # 2) Time budget
    time_budget = min(board.my_time * TIME_FRACTION, TIME_CAP)
    _search_deadline = time.time() + time_budget

    # 3) Init search tables
    _init_search_tables(max_depth)

    best_move = None

    # 4) Iterative deepening
    for depth in range(1, max_depth + 1):
        if _is_time_up():
            break
        score, move = _minimax(board, depth,
                               float("-inf"), float("inf"),
                               True, player, board.move_number,
                               ply=0)
        if move is not None:
            best_move = move
        if score >= WIN_SCORE - 1:
            break

    # 5) Fallback
    if best_move is None:
        legal = board.getLegalMoves(player)
        if legal:
            best_move = legal[0]

    return best_move


# ======================================================================
# I/O
# ======================================================================

def play_move(row: int, col: int):
    print(f"{row} {col}", flush=True)


while True:
    try:
        line = input()
    except EOFError:
        break
    board = Board(line)
    best_move = getBestMove(board)
    if best_move:
        play_move(best_move[0], best_move[1])