import time
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
            for j, cell_data in enumerate(row):
                self.board[i][j].count = cell_data[0]
                self.board[i][j].player = Player(cell_data[1])

    def copy(self):
        """Create a deep copy of the board"""
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

    def getCriticalMass(self, x, y):
        """Returns how many orbs needed to explode at (x, y)"""
        mass = 4
        if x == 0 or x == self.rows - 1:
            mass -= 1
        if y == 0 or y == self.cols - 1:
            mass -= 1
        return mass

    def getNeighbors(self, x, y):
        """Returns valid neighboring cell coordinates"""
        neighbors = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if self.checkValidCell(nx, ny):
                neighbors.append((nx, ny))
        return neighbors

    def cellExploding(self, x, y):
        if not self.checkValidCell(x, y):
            return False
        return self.board[x][y].count >= self.getCriticalMass(x, y)

    def makeMove(self, x, y, player):
        """Simulate a move and return True if successful"""
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

                    directions = [[-1, 0], [1, 0], [0, -1], [0, 1]]
                    for d in directions:
                        new_x = to_pos.x + d[0]
                        new_y = to_pos.y + d[1]
                        if self.checkValidCell(new_x, new_y):
                            next_update_queue.append([Position(to_pos.x, to_pos.y), Position(new_x, new_y)])

            update_queue = next_update_queue

        return True

    def isTerminal(self, move_counter):
        """Check if the game is in a terminal state"""
        if move_counter < 2:
            return False

        red_count = 0
        blue_count = 0

        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player == Player.RED:
                    red_count += 1
                elif self.board[i][j].player == Player.BLUE:
                    blue_count += 1

        return red_count == 0 or blue_count == 0

    def evaluate(self, player):
        """
        Evaluate the board state for the given player.
        Positive = good for player, Negative = bad for player.
        """
        my_color = player
        opp_color = Player.BLUE if player == Player.RED else Player.RED

        my_orbs = 0
        opp_orbs = 0
        my_critical = 0
        opp_critical = 0
        my_vulnerable = 0

        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                critical_mass = self.getCriticalMass(i, j)

                if cell.player == my_color:
                    my_orbs += cell.count
                    if cell.count == critical_mass - 1:
                        my_critical += 1
                        # Check if opponent has an adjacent cell (vulnerable)
                        for ni, nj in self.getNeighbors(i, j):
                            if self.board[ni][nj].player == opp_color:
                                my_vulnerable += 1
                                break

                elif cell.player == opp_color:
                    opp_orbs += cell.count
                    if cell.count == critical_mass - 1:
                        opp_critical += 1

        # Terminal bonuses
        if opp_orbs == 0:
            return 10000   # I WIN
        if my_orbs == 0:
            return -10000  # I LOSE

        # Heuristic score
        score = (my_orbs - opp_orbs) * 10
        score += my_critical * 15       # My cells ready to explode = great
        score -= opp_critical * 15      # Opponent ready to explode = danger
        score -= my_vulnerable * 20     # My near-critical cells next to opponent = risky

        return score

    def getLegalMoves(self, player):
        """Get all legal moves for the given player"""
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE or cell.player == player:
                    moves.append((i, j))
        return moves


# ─────────────────────────────────────────────────────────────
# MINIMAX WITH ALPHA-BETA PRUNING
# ─────────────────────────────────────────────────────────────

def minimax(board, depth, alpha, beta, maximizing_player, player, move_counter):
    """
    Minimax algorithm with alpha-beta pruning.
    Searches up to 4 layers deep to find the best move.

    Returns: (best_score, best_move)
    """
    opponent = Player.BLUE if player == Player.RED else Player.RED

    # Base case
    if depth == 0 or board.isTerminal(move_counter):
        return board.evaluate(player), None

    best_move = None

    if maximizing_player:
        max_eval = float('-inf')
        legal_moves = board.getLegalMoves(player)

        if not legal_moves:
            return board.evaluate(player), None

        for move in legal_moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)

            eval_score, _ = minimax(new_board, depth - 1, alpha, beta, False, player, move_counter + 1)

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break  # Alpha-Beta Prune ✂️

        return max_eval, best_move

    else:
        min_eval = float('inf')
        legal_moves = board.getLegalMoves(opponent)

        if not legal_moves:
            return board.evaluate(player), None

        for move in legal_moves:
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)

            eval_score, _ = minimax(new_board, depth - 1, alpha, beta, True, player, move_counter + 1)

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move

            beta = min(beta, eval_score)
            if beta <= alpha:
                break  # Alpha-Beta Prune ✂️

        return min_eval, best_move


# ─────────────────────────────────────────────────────────────
# GET BEST MOVE (Entry Point)
# ─────────────────────────────────────────────────────────────

def getBestMove(board, depth=4):
    """
    Returns the best move for the current player using iterative deepening minimax.
    Stays within time limit.
    """
    player = Player.RED if board.me == 1 else Player.BLUE

    best_move = None
    start = time.time()
    time_limit = min(board.my_time * 0.9, 55)  # Use 90% of remaining time, max 55s

    for d in range(1, depth + 1):
        if time.time() - start > time_limit:
            break

        score, move = minimax(board, d, float('-inf'), float('inf'), True, player, board.move_number)

        if move:
            best_move = move

        print(f"[Depth {d}] Best Move: {move} | Score: {score}", file=__import__('sys').stderr, flush=True)

    # Fallback: pick first legal move if minimax fails
    if best_move is None:
        legal_moves = board.getLegalMoves(player)
        if legal_moves:
            best_move = legal_moves[0]

    return best_move


# ─────────────────────────────────────────────────────────────
# PLAY MOVE OUTPUT
# ─────────────────────────────────────────────────────────────

def play_move(row, col):
    print(f"{row} {col}", flush=True)


# ─────────────────────────────────────────────────────────────
# MAIN — Read once, respond once, exit
# (main.py spawns a fresh subprocess every move)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        line = input()
        board = Board(line)

        best_move = getBestMove(board, depth=4)

        if best_move:
            play_move(best_move[0], best_move[1])
        else:
            # Emergency fallback — should never happen
            print("0 0", flush=True)

    except Exception as e:
        print(f"Bot error: {e}", file=__import__('sys').stderr, flush=True)
        print("0 0", flush=True)  # Send a move anyway so game doesn't freeze
