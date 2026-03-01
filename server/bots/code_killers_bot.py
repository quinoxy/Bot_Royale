import json
import sys
import time
from enum import Enum

sys.setrecursionlimit(10000)


# ==============================
# ENUMS AND BASIC STRUCTURES
# ==============================

class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2


class BoardCell:
    def __init__(self):
        self.player = Player.NONE
        self.count = 0


class Position:
    def __init__(self, x, y):
        self.x = x
        self.y = y


# ==============================
# BOARD CLASS
# ==============================

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

    def cellThreshold(self, x, y):
        threshold = 4
        if x == 0 or x == self.rows - 1:
            threshold -= 1
        if y == 0 or y == self.cols - 1:
            threshold -= 1
        return threshold

    def cellExploding(self, x, y):
        return self.board[x][y].count >= self.cellThreshold(x, y)

    # ==============================
    # MOVE SIMULATION
    # ==============================

    def makeMove(self, x, y, player):
        if player == Player.NONE:
            return False
        if not self.checkValidCell(x, y):
            return False
        if self.board[x][y].player not in (Player.NONE, player):
            return False

        queue = [Position(x, y)]
        safety_counter = 0

        while queue and safety_counter < 1000:
            safety_counter += 1
            current = queue.pop(0)
            cell = self.board[current.x][current.y]

            cell.count += 1
            cell.player = player

            if self.cellExploding(current.x, current.y):
                cell.count = 0
                cell.player = Player.NONE

                directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

                for dx, dy in directions:
                    nx, ny = current.x + dx, current.y + dy
                    if self.checkValidCell(nx, ny):
                        queue.append(Position(nx, ny))

        return True

    # ==============================
    # TERMINAL CHECK
    # ==============================

    def isTerminal(self):
        red = 0
        blue = 0

        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player == Player.RED:
                    red += 1
                elif self.board[i][j].player == Player.BLUE:
                    blue += 1

        return red == 0 or blue == 0

    # ==============================
    # EVALUATION FUNCTION
    # ==============================

    def evaluate(self, player):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        score = 0

        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]

                if cell.player == player:
                    weight = 1

                    # Corner bonus
                    if (i in (0, self.rows - 1)) and (j in (0, self.cols - 1)):
                        weight = 4
                    # Edge bonus
                    elif i in (0, self.rows - 1) or j in (0, self.cols - 1):
                        weight = 2

                    score += cell.count * weight

                    # Near explosion bonus
                    if cell.count == self.cellThreshold(i, j) - 1:
                        score += 3

                elif cell.player == opponent:
                    weight = 1

                    if (i in (0, self.rows - 1)) and (j in (0, self.cols - 1)):
                        weight = 4
                    elif i in (0, self.rows - 1) or j in (0, self.cols - 1):
                        weight = 2

                    score -= cell.count * weight

                    if cell.count == self.cellThreshold(i, j) - 1:
                        score -= 3

        return score

    # ==============================
    # LEGAL MOVES
    # ==============================

    def getLegalMoves(self, player):
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player in (Player.NONE, player):
                    moves.append((i, j))

        # Move ordering: prioritize corners first
        moves.sort(key=lambda m: (
            0 if (m[0] in (0, self.rows - 1) and m[1] in (0, self.cols - 1)) else 1
        ))

        return moves


# ==============================
# MINIMAX WITH TIME CONTROL
# ==============================

def minimax(board, depth, alpha, beta, maximizing, player, start_time, time_limit):
    if time.time() - start_time > time_limit:
        return board.evaluate(player), None

    opponent = Player.RED if player == Player.BLUE else Player.BLUE

    if depth == 0 or board.isTerminal():
        return board.evaluate(player), None

    best_move = None

    if maximizing:
        max_eval = float('-inf')
        for move in board.getLegalMoves(player):
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)

            if new_board.isTerminal():
                return 100000, move

            eval_score, _ = minimax(
                new_board, depth - 1, alpha, beta, False,
                player, start_time, time_limit
            )

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break

        return max_eval, best_move

    else:
        min_eval = float('inf')
        for move in board.getLegalMoves(opponent):
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)

            eval_score, _ = minimax(
                new_board, depth - 1, alpha, beta, True,
                player, start_time, time_limit
            )

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move

            beta = min(beta, eval_score)
            if beta <= alpha:
                break

        return min_eval, best_move


# ==============================
# ITERATIVE DEEPENING
# ==============================

def getBestMove(board):
    player = Player.RED if board.me == 1 else Player.BLUE

    start_time = time.time()
    time_limit = min(0.9, board.my_time * 0.1)

    depth = 1
    best_move = None

    while True:
        if time.time() - start_time > time_limit:
            break

        score, move = minimax(
            board, depth,
            float('-inf'), float('inf'),
            True, player,
            start_time, time_limit
        )

        if move:
            best_move = move

        depth += 1

    if best_move is None:
        legal = board.getLegalMoves(player)
        if legal:
            best_move = legal[0]

    return best_move


def play_move(row, col):
    print(f"{row} {col}", flush=True)


# ==============================
# MAIN LOOP
# ==============================

while True:
    try:
        line = input()
    except EOFError:
        break

    board = Board(line)
    best_move = getBestMove(board)

    if best_move:
        play_move(best_move[0], best_move[1])