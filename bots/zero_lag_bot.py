import json
from enum import Enum


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
            for j, cell in enumerate(row):
                self.board[i][j].count = cell[0]
                self.board[i][j].player = Player(cell[1])

    def copy(self):
        new = Board.__new__(Board)
        new.rows = self.rows
        new.cols = self.cols
        new.my_time = self.my_time
        new.opp_time = self.opp_time
        new.me = self.me
        new.move_number = self.move_number

        new.board = [[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(self.cols):
                new.board[i][j].player = self.board[i][j].player
                new.board[i][j].count = self.board[i][j].count

        return new

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
        if self.board[x][y].player not in [Player.NONE, player]:
            return False

        queue = [Position(x, y)]

        while queue:
            pos = queue.pop(0)
            cell = self.board[pos.x][pos.y]

            cell.count += 1
            cell.player = player

            if self.cellExploding(pos.x, pos.y):
                cell.count = 0
                cell.player = Player.NONE

                for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx, ny = pos.x + dx, pos.y + dy
                    if self.checkValidCell(nx, ny):
                        queue.append(Position(nx, ny))

        return True

    def getLegalMoves(self, player):
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player in (Player.NONE, player):
                    moves.append((i, j))
        return moves

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

    # ⭐ FINAL TOURNAMENT EVALUATION
    def evaluate(self, player):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        my_cells = opp_cells = 0
        my_dots = opp_dots = 0
        score = 0

        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE:
                    continue

                threshold = 4
                if i == 0 or i == self.rows - 1: threshold -= 1
                if j == 0 or j == self.cols - 1: threshold -= 1

                critical = (cell.count == threshold - 1)

                if cell.player == player:
                    my_cells += 1
                    my_dots += cell.count

                    proximity = cell.count / threshold
                    score += 10 + proximity * 20

                    if critical:
                        score += 18
                        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                            nx, ny = i + dx, j + dy
                            if self.checkValidCell(nx, ny):
                                if self.board[nx][ny].player == opponent:
                                    score -= 22

                    if (i in [0,self.rows-1]) and (j in [0,self.cols-1]):
                        score += 6
                    elif i in [0,self.rows-1] or j in [0,self.cols-1]:
                        score += 3

                else:
                    opp_cells += 1
                    opp_dots += cell.count

                    proximity = cell.count / threshold
                    score -= 10 + proximity * 20

                    if critical:
                        score -= 18
                        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                            nx, ny = i + dx, j + dy
                            if self.checkValidCell(nx, ny):
                                if self.board[nx][ny].player == player:
                                    score += 22

        if opp_cells == 0 and self.move_number >= 2:
            return 100000
        if my_cells == 0 and self.move_number >= 2:
            return -100000

        score += (my_cells - opp_cells) * 8
        score += (my_dots - opp_dots) * 5

        total = my_cells + opp_cells
        if total > 0:
            score += (my_cells / total - 0.5) * 50

        return score


# 🔥 MOVE ORDERING
def order_moves(board, moves):
    def priority(move):
        x, y = move
        cell = board.board[x][y]

        threshold = 4
        if x == 0 or x == board.rows - 1: threshold -= 1
        if y == 0 or y == board.cols - 1: threshold -= 1

        return cell.count == threshold - 1

    return sorted(moves, key=priority, reverse=True)


def minimax(board, depth, alpha, beta, maximizing, player, move_counter):
    opponent = Player.RED if player == Player.BLUE else Player.BLUE

    if depth == 0 or board.isTerminal(move_counter):
        return board.evaluate(player), None

    if maximizing:
        max_eval = float('-inf')
        best_move = None

        moves = order_moves(board, board.getLegalMoves(player))

        for move in moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)

            eval_score, _ = minimax(new_board, depth - 1, alpha, beta, False, player, move_counter + 1)

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break

        return max_eval, best_move

    else:
        min_eval = float('inf')
        best_move = None

        moves = order_moves(board, board.getLegalMoves(opponent))

        for move in moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)

            eval_score, _ = minimax(new_board, depth - 1, alpha, beta, True, player, move_counter + 1)

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move

            beta = min(beta, eval_score)
            if beta <= alpha:
                break

        return min_eval, best_move


def getInstantWin(board, player):
    for move in board.getLegalMoves(player):
        temp = board.copy()
        temp.makeMove(move[0], move[1], player)
        if temp.isTerminal(board.move_number + 1):
            return move
    return None


def choose_depth(board):
    if board.move_number < 6:
        return 3
    if board.my_time < 10:
        return 2
    if board.my_time < 25:
        return 3
    return 4


def getBestMove(board):
    player = Player.RED if board.me == 1 else Player.BLUE

    win_move = getInstantWin(board, player)
    if win_move:
        return win_move

    depth = choose_depth(board)

    _, move = minimax(board, depth, float('-inf'), float('inf'), True, player, board.move_number)

    if move is None:
        legal = board.getLegalMoves(player)
        return legal[0] if legal else (0, 0)

    return move


def play_move(r, c):
    print(f"{r} {c}", flush=True)


# 🏁 MAIN LOOP (CRASH SAFE)
while True:
    try:
        line = input()
        board = Board(line)
        move = getBestMove(board)
        play_move(move[0], move[1])
    except:
        print("0 0", flush=True)