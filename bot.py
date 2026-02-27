import json
from enum import Enum
import copy


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
        """Simulate a move and return True if successful"""
        if player == Player.NONE:
            return False
        if not self.checkValidCell(x, y):
            return False
        if self.board[x][y].player != Player.NONE and self.board[x][y].player != player:
            return False
        
        # Queue for processing cell updates
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
        pass
    def getLegalMoves(self, player):
        """Get all legal moves for the given player"""
        moves = []
        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE or cell.player == player:
                    moves.append((i, j))
        return moves


def minimax(board, depth, alpha, beta, maximizing_player, player, move_counter):
    """
    Minimax algorithm with alpha-beta pruning
    
    Args:
        board: Current board state
        depth: Current depth in the search tree
        alpha: Best value for maximizer
        beta: Best value for minimizer
        maximizing_player: True if current player is maximizing
        player: The player we're optimizing for
        move_counter: Number of moves made so far
    
    Returns:
        Tuple of (best_score, best_move)
    """
    opponent = Player.RED if player == Player.BLUE else Player.BLUE
    
    # Base case: check terminal state or depth limit
    if depth == 0 or board.isTerminal(move_counter):
        return board.evaluate(player), None
    
    best_move = None
    
    if maximizing_player:
        max_eval = float('-inf')
        legal_moves = board.getLegalMoves(player)
        
        if not legal_moves:
            return board.evaluate(player), None
        
        for move in legal_moves:
            # Make a copy and simulate the move
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], player)
            
            eval_score, _ = minimax(new_board, depth - 1, alpha, beta, False, player, move_counter + 1)
            
            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move
            
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break  # Beta cutoff
        
        return max_eval, best_move
    
    else:
        min_eval = float('inf')
        legal_moves = board.getLegalMoves(opponent)
        
        if not legal_moves:
            return board.evaluate(player), None
        
        for move in legal_moves:
            # Make a copy and simulate the move
            new_board = board.copy()
            new_board.makeMove(move[0], move[1], opponent)
            
            eval_score, _ = minimax(new_board, depth - 1, alpha, beta, True, player, move_counter + 1)
            
            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move
            
            beta = min(beta, eval_score)
            if beta <= alpha:
                break  # Alpha cutoff
        
        return min_eval, best_move


def getBestMove(board, depth=4):
    """Get the best move using minimax with alpha-beta pruning"""
    player = Player.RED if board.me == 1 else Player.BLUE
    _, best_move = minimax(board, depth, float('-inf'), float('inf'), True, player, board.move_number)
    
    if best_move is None:
        # Fallback: choose first legal move
        legal_moves = board.getLegalMoves(player)
        if legal_moves:
            best_move = legal_moves[0]
    
    return best_move

        
def play_move(row, col):
    print(f"{row} {col}", flush=True)


# Main game loop
while True:
    line = input()
    board = Board(line)
    
    # Get the best move using minimax with alpha-beta pruning
    best_move = getBestMove(board, depth=4)
    
    if best_move:
        play_move(best_move[0], best_move[1])
