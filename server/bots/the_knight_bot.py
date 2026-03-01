import json
from enum import Enum
import copy
import time
import random


# ================== ENUM ==================
class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2


# ================== CELL ==================
class BoardCell:
    def __init__(self):
        self.player = Player.NONE
        self.count = 0


# ================== BOARD ==================
class Board:
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

    def copy(self):
        new_board = Board.__new__(Board)
        new_board.rows = self.rows
        new_board.cols = self.cols
        new_board.my_time = self.my_time
        new_board.opp_time = self.opp_time
        new_board.me = self.me
        new_board.move_number = self.move_number
        new_board.board = [[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]

        for i in range(self.rows):
            for j in range(self.cols):
                new_board.board[i][j].player = self.board[i][j].player
                new_board.board[i][j].count = self.board[i][j].count
        return new_board

    def checkValidCell(self, x, y):
        return 0 <= x < self.rows and 0 <= y < self.cols

    def cellExploding(self, x, y):
        threshold = 4
        if x == 0 or x == self.rows - 1:
            threshold -= 1
        if y == 0 or y == self.cols - 1:
            threshold -= 1
        return self.board[x][y].count >= threshold

    def makeMove(self, x, y, player):
        if not self.checkValidCell(x, y):
            return False
        if self.board[x][y].player not in [Player.NONE, player]:
            return False

        queue = [(x, y)]

        while queue:
            cx, cy = queue.pop(0)
            cell = self.board[cx][cy]
            cell.count += 1
            cell.player = player

            if self.cellExploding(cx, cy):
                cell.count = 0
                cell.player = Player.NONE

                for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx, ny = cx + dx, cy + dy
                    if self.checkValidCell(nx, ny):
                        queue.append((nx, ny))
        return True

    def isTerminal(self, move_counter):
        if move_counter < 2:
            return False

        red, blue = 0, 0
        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player == Player.RED:
                    red += 1
                elif self.board[i][j].player == Player.BLUE:
                    blue += 1

        return red == 0 or blue == 0

    def evaluate(self, player):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        my_score = 0
        opp_score = 0

        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE:
                    continue

                threshold = 4
                if i == 0 or i == self.rows - 1:
                    threshold -= 1
                if j == 0 or j == self.cols - 1:
                    threshold -= 1

                position_weight = 3 if threshold == 2 else 2 if threshold == 3 else 1
                readiness = cell.count / threshold
                chain_bonus = 2 if cell.count == threshold - 1 else 0

                value = 5 + position_weight*2 + readiness*3 + chain_bonus

                if cell.player == player:
                    my_score += value
                else:
                    opp_score += value

        return my_score - opp_score

    def getLegalMoves(self, player):
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player in [Player.NONE, player]:
                    moves.append((i, j))
        return moves


# ================== MOVE ORDERING ==================
def orderMoves(board, moves):
    def score(move):
        x, y = move
        cell = board.board[x][y]

        threshold = 4
        if x == 0 or x == board.rows - 1:
            threshold -= 1
        if y == 0 or y == board.cols - 1:
            threshold -= 1

        if cell.count == threshold - 1:
            return 100
        return cell.count

    return sorted(moves, key=score, reverse=True)


# ================== MINIMAX WITH TIME LIMIT ==================
def minimax(board, depth, alpha, beta, maximizing, player, move_counter, start_time, time_limit):

    if time.time() - start_time > time_limit:
        return None, None

    opponent = Player.RED if player == Player.BLUE else Player.BLUE

    if depth == 0 or board.isTerminal(move_counter):
        return board.evaluate(player), None

    legal_moves = board.getLegalMoves(player if maximizing else opponent)
    legal_moves = orderMoves(board, legal_moves)

    best_move = None

    if maximizing:
        max_eval = float('-inf')

        for move in legal_moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)

            eval_score, _ = minimax(
                new_board, depth - 1, alpha, beta,
                False, player, move_counter + 1,
                start_time, time_limit
            )

            if eval_score is None:
                return None, None

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break

        return max_eval, best_move

    else:
        min_eval = float('inf')

        for move in legal_moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)

            eval_score, _ = minimax(
                new_board, depth - 1, alpha, beta,
                True, player, move_counter + 1,
                start_time, time_limit
            )

            if eval_score is None:
                return None, None

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move

            beta = min(beta, eval_score)
            if beta <= alpha:
                break

        return min_eval, best_move


# ================== MOVE SELECTION ==================
def getBestMove(board, depth=4):
    player = Player.RED if board.me == 1 else Player.BLUE
    legal_moves = board.getLegalMoves(player)

    if not legal_moves:
        return None

    start_time = time.time()
    time_limit = 1.0  # 🔥 1 second limit

    score, best_move = minimax(
        board, depth,
        float('-inf'), float('inf'),
        True, player, board.move_number,
        start_time, time_limit
    )

    # 🔥 Timeout fallback
    if best_move is None:
        for move in legal_moves:
            x, y = move
            cell = board.board[x][y]

            threshold = 4
            if x == 0 or x == board.rows - 1:
                threshold -= 1
            if y == 0 or y == board.cols - 1:
                threshold -= 1

            if cell.count == threshold - 1:
                return move  # burst move

        return random.choice(legal_moves)

    return best_move


# ================== MAIN LOOP ==================
def play_move(row, col):
    print(f"{row} {col}", flush=True)


while True:
    line = input()
    board = Board(line)
    best_move = getBestMove(board, depth=4)
    if best_move:
        play_move(best_move[0], best_move[1])