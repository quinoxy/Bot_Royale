import math
import copy
import time
from enum import Enum


class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2


class Bot:
    def __init__(self, player):
        self.player = player
        self.start = None
        self.TIME_LIMIT = 1.9

    def get_move(self, board):
        self.start = time.time()

        # Opening: center control (dominant in Chain Reaction)
        if board.move_number == 0:
            return (board.rows // 2, board.cols // 2)

        best_move = None
        depth = 1

        while time.time() - self.start < self.TIME_LIMIT:
            move, _ = self.minimax(board, depth, -math.inf, math.inf, True)
            if move:
                best_move = move
            depth += 1

        return best_move

    def minimax(self, board, depth, alpha, beta, maximize):
        if time.time() - self.start > self.TIME_LIMIT:
            return None, board.evaluate(self.player)

        if depth == 0 or board.isTerminal():
            return None, board.evaluate(self.player)

        current = self.player if maximize else board.getOpponent(self.player)
        moves = board.getLegalMoves(current)

        # 🔥 ADAPTIVE MOVE ORDERING
        moves.sort(
            key=lambda m: (
                board.cellExploding(m[0], m[1]),
                board.adaptivePressure(m[0], m[1], current),
                -board.calculatedRisk(m[0], m[1], current)
            ),
            reverse=True
        )

        best_move = None

        if maximize:
            best = -math.inf
            for m in moves:
                nb = copy.deepcopy(board)
                nb.makeMove(m[0], m[1], current)

                # Forced win
                if nb.hasWon(self.player):
                    return m, 1_000_000

                _, val = self.minimax(nb, depth - 1, alpha, beta, False)

                if val > best:
                    best = val
                    best_move = m

                alpha = max(alpha, val)
                if beta <= alpha:
                    break

            return best_move, best
        else:
            best = math.inf
            for m in moves:
                nb = copy.deepcopy(board)
                nb.makeMove(m[0], m[1], current)

                _, val = self.minimax(nb, depth - 1, alpha, beta, True)

                if val < best:
                    best = val
                    best_move = m

                beta = min(beta, val)
                if beta <= alpha:
                    break

            return best_move, best


# ===================== ADAPTIVE BOARD INTELLIGENCE ===================== #

class Board:
    def evaluate(self, player):
        opponent = self.getOpponent(player)
        score = 0

        my_cells = 0
        opp_cells = 0

        for i in range(self.rows):
            for j in range(self.cols):
                c = self.board[i][j]
                if c.player == player:
                    my_cells += 1
                    score += c.count * 7
                    if self.cellExploding(i, j):
                        score += 20
                elif c.player == opponent:
                    opp_cells += 1
                    score -= c.count * 8
                    if self.cellExploding(i, j):
                        score -= 25

        # 🔥 ADAPTIVE PHASE SHIFT
        if my_cells > opp_cells:
            score += 50   # go for kill
        else:
            score -= 10   # survive & bait

        return score

    def adaptivePressure(self, x, y, player):
        """
        Pressure depends on game phase.
        Early = spread
        Mid/Late = kill clusters
        """
        opp = self.getOpponent(player)
        pressure = 0

        for nx, ny in self.getNeighbors(x, y):
            cell = self.board[nx][ny]
            if cell.player == opp:
                pressure += 6
                if self.cellExploding(nx, ny):
                    pressure += 10
            elif cell.player == player:
                pressure += 2

        return pressure

    def calculatedRisk(self, x, y, player):
        """
        Early game: avoid gifting explosions
        Late game: allow sacrifices
        """
        opp = self.getOpponent(player)
        risk = 0

        for nx, ny in self.getNeighbors(x, y):
            cell = self.board[nx][ny]
            if cell.player == opp and self.cellExploding(nx, ny):
                risk += 6

        # Late-game aggression switch
        if self.move_number > (self.rows * self.cols) // 2:
            risk *= 0.4  # allow risk

        return risk

    def getOpponent(self, player):
        return Player.RED if player == Player.BLUE else Player.BLUE

    def getLegalMoves(self, player):
        explode = []
        normal = []

        for i in range(self.rows):
            for j in range(self.cols):
                c = self.board[i][j]
                if c.player == Player.NONE or c.player == player:
                    if self.cellExploding(i, j):
                        explode.append((i, j))
                    else:
                        normal.append((i, j))

        return explode + normal