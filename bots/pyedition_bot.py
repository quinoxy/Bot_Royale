import json
from enum import Enum
import copy
import random
import time  # for time control

class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2

class BoardCell:
    __slots__ = ('player', 'count')
    def __init__(self):
        self.player = Player.NONE
        self.count = 0

class Position:
    __slots__ = ('x', 'y')
    def __init__(self, x, y):
        self.x = x
        self.y = y

# ---------- Zobrist Hashing for Transposition Table ----------
class ZobristHash:
    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.table = {}
        for i in range(rows):
            for j in range(cols):
                for p in Player:
                    for c in range(16):
                        self.table[(i, j, p.value, c)] = random.getrandbits(64)
    def hash_board(self, board):
        h = 0
        for i in range(self.rows):
            for j in range(self.cols):
                cell = board.board[i][j]
                if cell.player != Player.NONE:
                    h ^= self.table[(i, j, cell.player.value, cell.count)]
        return h

# Global transposition table (kept during iterative deepening)
transposition_table = {}

class Board:
    __slots__ = ('rows', 'cols', 'my_time', 'opp_time', 'me', 'move_number', 'board',
                 'threshold', 'pos_weight', 'zobrist')
    def __init__(self, line):
        state = json.loads(line)
        self.rows = state['rows']
        self.cols = state['cols']
        self.my_time = state['my_time']
        self.opp_time = state['opp_time']
        self.me = state["player"]
        self.move_number = state.get('move_number', 0)
        self.board = [[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]
        for i, row in enumerate(state['board']):
            for j, cell_data in enumerate(row):
                self.board[i][j].count = cell_data[0]
                self.board[i][j].player = Player(cell_data[1])

        # Precomputed tables for instant evaluation
        self.threshold = [[0]*self.cols for _ in range(self.rows)]
        self.pos_weight = [[0]*self.cols for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(self.cols):
                is_corner = (i == 0 or i == self.rows-1) and (j == 0 or j == self.cols-1)
                is_edge = (i == 0 or i == self.rows-1) or (j == 0 or j == self.cols-1)
                if is_corner:
                    self.pos_weight[i][j] = 5
                    self.threshold[i][j] = 2
                elif is_edge:
                    self.pos_weight[i][j] = 3
                    self.threshold[i][j] = 3
                else:
                    self.pos_weight[i][j] = 1
                    self.threshold[i][j] = 4

        self.zobrist = ZobristHash(self.rows, self.cols)

    def copy(self):
        """Fast copy – shares precomputed tables"""
        new_board = Board.__new__(Board)
        new_board.rows = self.rows
        new_board.cols = self.cols
        new_board.my_time = self.my_time
        new_board.opp_time = self.opp_time
        new_board.me = self.me
        new_board.move_number = self.move_number
        new_board.board = [[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]
        for i in range(self.rows):
            row = self.board[i]
            new_row = new_board.board[i]
            for j in range(self.cols):
                cell = row[j]
                new_cell = new_row[j]
                new_cell.player = cell.player
                new_cell.count = cell.count
        new_board.threshold = self.threshold
        new_board.pos_weight = self.pos_weight
        new_board.zobrist = self.zobrist
        return new_board

    def hash(self):
        return self.zobrist.hash_board(self)

    def checkValidCell(self, x, y):
        return 0 <= x < self.rows and 0 <= y < self.cols

    def cellExploding(self, x, y):
        if not self.checkValidCell(x, y):
            return False
        threshold = 4
        if x == 0 or x == self.rows - 1:
            threshold -= 1
        if y == 0 or y == self.cols - 1:
            threshold -= 1
        return self.board[x][y].count >= threshold

    def makeMove(self, x, y, player):
        if player == Player.NONE:
            return False
        if not self.checkValidCell(x, y):
            return False
        if self.board[x][y].player != Player.NONE and self.board[x][y].player != player:
            return False

        update_queue = [[Position(x, y), Position(x, y)]]

        while update_queue:
            num_updates = len(update_queue)
            next_update_queue = []
            for i in range(num_updates):
                update = update_queue[i]
                to_pos = update[1]
                cell = self.board[to_pos.x][to_pos.y]

                cell.count += 1
                cell.player = player

                if self.cellExploding(to_pos.x, to_pos.y):
                    cell.count = 0
                    cell.player = Player.NONE
                    directions = ((-1,0),(1,0),(0,-1),(0,1))
                    for dx, dy in directions:
                        nx = to_pos.x + dx
                        ny = to_pos.y + dy
                        if self.checkValidCell(nx, ny):
                            next_update_queue.append([Position(to_pos.x, to_pos.y), Position(nx, ny)])
            update_queue = next_update_queue
        return True

    def isTerminal(self, move_counter):
        if move_counter < 2:
            return False
        red = blue = 0
        for row in self.board:
            for cell in row:
                if cell.player == Player.RED:
                    red += 1
                elif cell.player == Player.BLUE:
                    blue += 1
        return red == 0 or blue == 0

    # ---------- AGGRESSIVE EVALUATION ----------
    def evaluate(self, player):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE
        score = 0
        EXPLOSION_WEIGHT = 12       # increased to favour chain reactions

        for i in range(self.rows):
            row_th = self.threshold[i]
            row_w = self.pos_weight[i]
            board_row = self.board[i]
            for j in range(self.cols):
                cell = board_row[j]
                if cell.player == Player.NONE:
                    continue
                th = row_th[j]
                base = cell.count + row_w[j]
                explosion_bonus = (EXPLOSION_WEIGHT * cell.count * cell.count) // (th * th)
                if cell.player == player:
                    score += base + explosion_bonus
                else:
                    score -= base + explosion_bonus
        return score

    # ---------- ENHANCED MOVE ORDERING ----------
    def getOrderedMoves(self, player):
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE or cell.player == player:
                    # Base priority from position (1,3,5)
                    pos_priority = self.pos_weight[i][j]
                    threshold = self.threshold[i][j]
                    count = cell.count
                    # Does playing here cause an immediate explosion?
                    explosion_now = (count + 1 >= threshold)
                    # How close to explosion? (count+1)/threshold
                    proximity = (count + 1) / threshold
                    # Combined priority: position weight * 10, count * 2,
                    # huge bonus if explosion now, and proximity bonus
                    priority = (pos_priority * 10) + (count * 2) + (100 if explosion_now else 0) + (proximity * 20)
                    moves.append((priority, i, j))
        moves.sort(reverse=True)
        return [(i, j) for _, i, j in moves]


# ---------- MINIMAX with TRANSPOSITION TABLE (now used with iterative deepening) ----------
def minimax(board, depth, alpha, beta, maximizing_player, player, move_counter):
    board_hash = board.hash()
    tt_entry = transposition_table.get(board_hash)
    if tt_entry and tt_entry['depth'] >= depth:
        if tt_entry['flag'] == 'exact':
            return tt_entry['score'], tt_entry['move']
        elif tt_entry['flag'] == 'lower':
            alpha = max(alpha, tt_entry['score'])
        elif tt_entry['flag'] == 'upper':
            beta = min(beta, tt_entry['score'])
        if alpha >= beta:
            return tt_entry['score'], tt_entry['move']

    opponent = Player.RED if player == Player.BLUE else Player.BLUE

    if depth == 0 or board.isTerminal(move_counter):
        eval_score = board.evaluate(player)
        transposition_table[board_hash] = {'score': eval_score, 'depth': depth, 'flag': 'exact', 'move': None}
        return eval_score, None

    best_move = None
    original_alpha = alpha

    if maximizing_player:
        max_eval = float('-inf')
        legal_moves = board.getOrderedMoves(player)
        if not legal_moves:
            eval_score = board.evaluate(player)
            transposition_table[board_hash] = {'score': eval_score, 'depth': depth, 'flag': 'exact', 'move': None}
            return eval_score, None

        for move in legal_moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)
            eval_score, _ = minimax(new_board, depth-1, alpha, beta, False, player, move_counter+1)
            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break

        flag = 'exact'
        if max_eval <= original_alpha:
            flag = 'upper'
        elif max_eval >= beta:
            flag = 'lower'
        transposition_table[board_hash] = {'score': max_eval, 'depth': depth, 'flag': flag, 'move': best_move}
        return max_eval, best_move

    else:
        min_eval = float('inf')
        legal_moves = board.getOrderedMoves(opponent)
        if not legal_moves:
            eval_score = board.evaluate(player)
            transposition_table[board_hash] = {'score': eval_score, 'depth': depth, 'flag': 'exact', 'move': None}
            return eval_score, None

        for move in legal_moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)
            eval_score, _ = minimax(new_board, depth-1, alpha, beta, True, player, move_counter+1)
            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move
            beta = min(beta, eval_score)
            if beta <= alpha:
                break

        flag = 'exact'
        if min_eval <= original_alpha:
            flag = 'upper'
        elif min_eval >= beta:
            flag = 'lower'
        transposition_table[board_hash] = {'score': min_eval, 'depth': depth, 'flag': flag, 'move': best_move}
        return min_eval, best_move


def getBestMove(board):
    global transposition_table
    player = Player.RED if board.me == 1 else Player.BLUE

    # Time management: use up to 10% of remaining time, at least 0.1s, at most 1s
    time_limit = max(0.1, min(1.0, board.my_time / 20))
    start_time = time.time()

    best_move = None
    depth = 1
    # Iterative deepening: search deeper until time runs out (at least depth 2)
    while True:
        transposition_table.clear()   # fresh table for each move (optional, but safe)
        _, move = minimax(board, depth, float('-inf'), float('inf'), True, player, board.move_number)
        if move is not None:
            best_move = move
        depth += 1

        # Stop if time exceeded or we reached a reasonable maximum depth
        if time.time() - start_time > time_limit or depth > 6:
            break

    # Fallback in case no move was found (should not happen)
    if best_move is None:
        legal = board.getOrderedMoves(player)
        if legal:
            best_move = legal[0]
    return best_move


def play_move(row, col):
    print(f"{row} {col}", flush=True)


# ---------- MAIN LOOP ----------
while True:
    line = input()
    board = Board(line)
    best_move = getBestMove(board)
    if best_move:
        play_move(best_move[0], best_move[1])
