import json
from enum import Enum
from collections import deque
import sys
import math

# ================= PLAYER =================

class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2


# ================= CELL =================

class BoardCell:
    def __init__(self, player=Player.NONE, count=0):
        self.player = player
        self.count = count


# ================= BOARD =================

class Board:
    def __init__(self, line):
        state = json.loads(line)
        self.rows = state['rows']
        self.cols = state['cols']
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

    def getThreshold(self, x, y):
        threshold = 4
        if x == 0 or x == self.rows - 1:
            threshold -= 1
        if y == 0 or y == self.cols - 1:
            threshold -= 1
        return threshold

    def makeMove(self, x, y, player):
        if not self.checkValidCell(x, y):
            return False

        cell = self.board[x][y]
        if cell.player != Player.NONE and cell.player != player:
            return False

        cell.count += 1
        cell.player = player

        q = deque()
        if cell.count >= self.getThreshold(x, y):
            q.append((x, y))

        while q:
            cx, cy = q.popleft()
            threshold = self.getThreshold(cx, cy)

            if self.board[cx][cy].count < threshold:
                continue

            self.board[cx][cy].count -= threshold
            if self.board[cx][cy].count == 0:
                self.board[cx][cy].player = Player.NONE

            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = cx + dx, cy + dy
                if not self.checkValidCell(nx, ny):
                    continue
                self.board[nx][ny].count += 1
                self.board[nx][ny].player = player
                if self.board[nx][ny].count >= self.getThreshold(nx, ny):
                    q.append((nx, ny))

        return True

    def getLegalMoves(self, player):
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player in (Player.NONE, player):
                    moves.append((i, j))
        return moves

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

    def evaluate(self, player):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        my_score = 0
        opp_score = 0

        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == player:
                    my_score += cell.count + 3
                elif cell.player == opponent:
                    opp_score += cell.count + 3

        return my_score - opp_score


# ================= MINIMAX =================

def minimax(board, depth, alpha, beta, maximizing, player):

    opponent = Player.RED if player == Player.BLUE else Player.BLUE

    if depth == 0 or board.isTerminal():
        return board.evaluate(player), None

    if maximizing:
        max_eval = -math.inf
        best_move = None
        for move in board.getLegalMoves(player):
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)
            eval_score, _ = minimax(new_board, depth-1, alpha, beta, False, player)

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break

        return max_eval, best_move

    else:
        min_eval = math.inf
        best_move = None
        for move in board.getLegalMoves(opponent):
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)
            eval_score, _ = minimax(new_board, depth-1, alpha, beta, True, player)

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move

            beta = min(beta, eval_score)
            if beta <= alpha:
                break

        return min_eval, best_move


def getBestMove(board):

    player = Player.RED if board.me == 1 else Player.BLUE

    depth = 3  # fixed safe depth

    _, move = minimax(board, depth, -math.inf, math.inf, True, player)

    if move:
        return move

    legal = board.getLegalMoves(player)
    if legal:
        return legal[0]

    return None


# ================= MAIN =================

if __name__ == "__main__":

    line = sys.stdin.readline()
    if not line:
        sys.exit(0)

    board = Board(line.strip())

    move = getBestMove(board)

    if move:
        print(f"{move[0]} {move[1]}", flush=True)
    else:
        print("0 0", flush=True)

    sys.exit(0)