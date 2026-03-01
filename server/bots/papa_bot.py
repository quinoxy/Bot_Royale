import json
import time

# Raw ints for maximum speed (Enum comparisons are slow in Python)
NONE = 0
RED = 1
BLUE = 2

ROWS = 7
COLS = 7
N = ROWS * COLS

# Precomputed grid data (computed once at module load)
_neighbors = []
_thresholds = []
_is_corner = []
_is_edge = []
_pos_type = []  # 0=interior, 1=edge, 2=corner

for _r in range(ROWS):
    for _c in range(COLS):
        adj = []
        if _r > 0: adj.append((_r - 1) * COLS + _c)
        if _r < ROWS - 1: adj.append((_r + 1) * COLS + _c)
        if _c > 0: adj.append(_r * COLS + _c - 1)
        if _c < COLS - 1: adj.append(_r * COLS + _c + 1)
        _neighbors.append(tuple(adj))
        _thresholds.append(len(adj))

        ic = (_r == 0 or _r == ROWS - 1) and (_c == 0 or _c == COLS - 1)
        ie = not ic and (_r == 0 or _r == ROWS - 1 or _c == 0 or _c == COLS - 1)
        _is_corner.append(ic)
        _is_edge.append(ie)
        if ic:
            _pos_type.append(2)
        elif ie:
            _pos_type.append(1)
        else:
            _pos_type.append(0)

_neighbors = tuple(_neighbors)
_thresholds = tuple(_thresholds)
_is_corner = tuple(_is_corner)
_is_edge = tuple(_is_edge)
_pos_type = tuple(_pos_type)


class Board:
    __slots__ = ('counts', 'players', 'my_time', 'opp_time', 'me', 'move_number')

    def __init__(self, line=None):
        if line is None:
            return
        state = json.loads(line)
        self.my_time = state['my_time']
        self.opp_time = state['opp_time']
        self.me = state["player"]
        self.move_number = state.get('move_number', 0)

        self.counts = [0] * N
        self.players = [0] * N
        for r, row in enumerate(state['board']):
            for c, cell in enumerate(row):
                idx = r * COLS + c
                self.counts[idx] = cell[0]
                self.players[idx] = cell[1]

    def copy(self):
        b = Board()
        b.counts = self.counts[:]
        b.players = self.players[:]
        b.my_time = self.my_time
        b.opp_time = self.opp_time
        b.me = self.me
        b.move_number = self.move_number
        return b

    def make_move(self, idx, player):
        """Apply move with undo tracking. Returns history dict or None if illegal."""
        if self.players[idx] not in (NONE, player):
            return None

        history = {}
        counts = self.counts
        players = self.players
        queue = [idx]

        while queue:
            nxt = []
            for cur in queue:
                if cur not in history:
                    history[cur] = (players[cur], counts[cur])
                counts[cur] += 1
                players[cur] = player
                if counts[cur] >= _thresholds[cur]:
                    counts[cur] = 0
                    players[cur] = NONE
                    nxt.extend(_neighbors[cur])
            queue = nxt

        return history

    def undo_move(self, history):
        counts = self.counts
        players = self.players
        for idx, (old_p, old_c) in history.items():
            players[idx] = old_p
            counts[idx] = old_c

    def is_terminal(self, move_counter):
        if move_counter < 2:
            return False
        has_red = RED in self.players
        has_blue = BLUE in self.players
        return not (has_red and has_blue)

    def get_legal_moves(self, player):
        players = self.players
        return [i for i in range(N) if players[i] == NONE or players[i] == player]

    def evaluate(self, player, move_counter):
        """Enhanced heuristic evaluation with tuned weights."""
        opponent = RED if player == BLUE else BLUE
        counts = self.counts
        players = self.players

        player_count = 0
        opp_count = 0
        my_dots = 0
        opp_dots = 0
        score = 0

        for idx in range(N):
            p = players[idx]
            if p == NONE:
                continue

            c = counts[idx]
            th = _thresholds[idx]
            is_crit = (c == th - 1)
            proximity = c / th  # how close to exploding (0.0 to ~0.99)

            if p == player:
                player_count += 1
                my_dots += c

                # Base cell value + proximity pressure
                delta = 10 + int(proximity * 20)

                # Critical cell bonus
                if is_crit:
                    delta += 18
                    # Threat: adjacent enemy cells we'd capture on explosion
                    for ni in _neighbors[idx]:
                        if players[ni] == opponent:
                            delta += 8  # capture threat bonus

                # Danger penalty: adjacent enemy critical cells threaten us
                for ni in _neighbors[idx]:
                    if players[ni] == opponent and counts[ni] == _thresholds[ni] - 1:
                        delta -= 15

                # Position bonus (safe positions)
                pt = _pos_type[idx]
                if pt == 2:
                    delta += 6   # corner — hardest to attack
                elif pt == 1:
                    delta += 3   # edge

                score += delta
            else:
                opp_count += 1
                opp_dots += c

                delta = 10 + int(proximity * 20)

                if is_crit:
                    delta += 18
                    for ni in _neighbors[idx]:
                        if players[ni] == player:
                            delta += 8

                for ni in _neighbors[idx]:
                    if players[ni] == player and counts[ni] == _thresholds[ni] - 1:
                        delta -= 15

                pt = _pos_type[idx]
                if pt == 2:
                    delta += 6
                elif pt == 1:
                    delta += 3

                score -= delta

        # Terminal detection
        if move_counter >= 2:
            if player_count == 0 and opp_count > 0:
                return -100000
            if opp_count == 0 and player_count > 0:
                return 100000

        # Cell count and dot advantage
        score += (player_count - opp_count) * 8
        score += (my_dots - opp_dots) * 5

        # Ownership ratio bonus
        total = player_count + opp_count
        if total > 0:
            score += int((player_count / total - 0.5) * 50)

        # Critical chain bonus (connected critical cells = devastating cascade potential)
        visited = [False] * N
        for idx in range(N):
            if visited[idx]:
                continue
            p = players[idx]
            if p == NONE:
                continue
            if counts[idx] != _thresholds[idx] - 1:
                continue
            block_size = 0
            stack = [idx]
            while stack:
                cur = stack.pop()
                if visited[cur]:
                    continue
                visited[cur] = True
                if players[cur] != p or counts[cur] != _thresholds[cur] - 1:
                    continue
                block_size += 1
                for ni in _neighbors[cur]:
                    if not visited[ni]:
                        stack.append(ni)
            chain_bonus = 5 * block_size
            if p == player:
                score += chain_bonus
            else:
                score -= chain_bonus

        return score


def get_instant_win(board, player, move_counter):
    """Check if any move wins immediately."""
    moves = board.get_legal_moves(player)
    for idx in moves:
        history = board.make_move(idx, player)
        if history is None:
            continue
        won = board.is_terminal(move_counter + 1)
        board.undo_move(history)
        if won:
            # Verify we actually won (not opponent)
            # After undoing, check: if we make this move, does opponent have 0 cells?
            return idx
    return None


def order_moves(board, moves, player):
    """Light move ordering: critical cells first, then corners, then edges."""
    counts = board.counts
    players = board.players
    scored = []
    for idx in moves:
        p = players[idx]
        c = counts[idx]
        th = _thresholds[idx]
        priority = 0

        # Moves that trigger chain reaction (own cell about to explode)
        if p == player and c == th - 1:
            priority += 30

        # Position value
        pt = _pos_type[idx]
        if pt == 2:
            priority += 15  # corner
        elif pt == 1:
            priority += 8   # edge

        # Building pressure (high count relative to threshold)
        if p == player:
            priority += c * 3

        scored.append((priority, idx))

    scored.sort(reverse=True)
    return [idx for _, idx in scored]


_INF = float('inf')
_NINF = float('-inf')
_node_count = 0


def minimax(board, depth, alpha, beta, maximizing, player, move_counter,
            pv_move=None, deadline=None):
    """Minimax with alpha-beta, PV ordering, move ordering, undo/redo, and deadline."""
    global _node_count

    # Time check every 512 nodes
    _node_count += 1
    if deadline and (_node_count & 511) == 0 and time.time() > deadline:
        return None, None

    opponent = RED if player == BLUE else BLUE

    if depth == 0 or board.is_terminal(move_counter):
        return board.evaluate(player, move_counter), None

    if maximizing:
        max_eval = _NINF
        best_move = None
        moves = board.get_legal_moves(player)

        # PV move first
        if pv_move is not None and pv_move in moves:
            moves.remove(pv_move)
            moves.insert(0, pv_move)
        elif depth >= 2:
            moves = order_moves(board, moves, player)

        for idx in moves:
            history = board.make_move(idx, player)
            if history is None:
                continue

            score, _ = minimax(board, depth - 1, alpha, beta, False,
                               player, move_counter + 1, deadline=deadline)
            board.undo_move(history)

            if score is None:
                return None, None

            if score > max_eval:
                max_eval = score
                best_move = idx

            alpha = max(alpha, score)
            if beta <= alpha:
                break

        if best_move is None:
            return board.evaluate(player, move_counter), None
        return max_eval, best_move

    else:
        min_eval = _INF
        best_move = None
        moves = board.get_legal_moves(opponent)

        if depth >= 2:
            moves = order_moves(board, moves, opponent)

        for idx in moves:
            history = board.make_move(idx, opponent)
            if history is None:
                continue

            score, _ = minimax(board, depth - 1, alpha, beta, True,
                               player, move_counter + 1, deadline=deadline)
            board.undo_move(history)

            if score is None:
                return None, None

            if score < min_eval:
                min_eval = score
                best_move = idx

            beta = min(beta, score)
            if beta <= alpha:
                break

        if best_move is None:
            return board.evaluate(player, move_counter), None
        return min_eval, best_move


def get_best_move(board):
    """Iterative deepening with PV ordering and time management."""
    global _node_count
    player = RED if board.me == 1 else BLUE

    # Instant win check
    win = get_instant_win(board, player, board.move_number)
    if win is not None:
        return win

    max_time = max(board.my_time * 0.05, 0.1)
    start = time.time()
    deadline = start + max_time
    best_move = None
    prev_time = 0

    for depth in range(1, 20):
        elapsed = time.time() - start
        remaining = max_time - elapsed
        if remaining <= 0:
            break
        if depth > 1 and prev_time * 3.5 > remaining:
            break

        _node_count = 0
        depth_start = time.time()
        score, move = minimax(board, depth, _NINF, _INF, True, player,
                              board.move_number, pv_move=best_move, deadline=deadline)
        prev_time = time.time() - depth_start

        if score is None:
            break

        if move is not None:
            best_move = move

    if best_move is None:
        moves = board.get_legal_moves(player)
        if moves:
            best_move = moves[0]

    return best_move


def play_move(idx):
    r = idx // COLS
    c = idx % COLS
    print(f"{r} {c}", flush=True)


if __name__ == '__main__':
    while True:
        try:
            line = input()
            board = Board(line)
            move = get_best_move(board)
            if move is not None:
                play_move(move)
            else:
                print("0 0", flush=True)
        except EOFError:
            break
        except:
            print("0 0", flush=True)
