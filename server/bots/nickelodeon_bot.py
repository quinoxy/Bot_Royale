import json
import time

NONE = 0
RED = 1
BLUE = 2

class Board:
    _precomputed = False
    _neighbors = tuple()
    _capacities = tuple()

    def __init__(self, line=None):
        if line is None:
            return
            
        state = json.loads(line)
        self.rows = state['rows']
        self.cols = state['cols']
        self.N = self.rows * self.cols
        self.my_time = state['my_time']
        self.opp_time = state['opp_time']
        self.me = state["player"]
        self.move_number = state.get('move_number', 0)
        
        self.counts = [0] * self.N
        self.players = [0] * self.N
        self.red_orbs = 0
        self.blue_orbs = 0
        
        for r, row in enumerate(state['board']):
            for c, cell_data in enumerate(row):
                count = cell_data[0]
                player_val = cell_data[1]
                idx = r * self.cols + c
                
                self.counts[idx] = count
                self.players[idx] = player_val
                
                if player_val == RED:
                    self.red_orbs += count
                elif player_val == BLUE:
                    self.blue_orbs += count
                    
        if not Board._precomputed:
            self._precompute_grid()

    def _precompute_grid(self):
        neighbors = []
        capacities = []
        for r in range(self.rows):
            for c in range(self.cols):
                adj = []
                if r > 0: adj.append((r - 1) * self.cols + c)
                if r < self.rows - 1: adj.append((r + 1) * self.cols + c)
                if c > 0: adj.append(r * self.cols + c - 1)
                if c < self.cols - 1: adj.append(r * self.cols + c + 1)
                
                neighbors.append(tuple(adj))
                capacities.append(len(adj))
                
        Board._neighbors = tuple(neighbors)
        Board._capacities = tuple(capacities)
        Board._precomputed = True

    def makeMove(self, idx, player, move_counter):
        if self.players[idx] not in (NONE, player):
            return None
            
        history = {'_orbs': (self.red_orbs, self.blue_orbs)}
        
        counts = self.counts
        players = self.players
        neighbors = Board._neighbors
        capacities = Board._capacities
        
        # Using a flat array with a head pointer is faster than popping from a queue
        queue = [idx]
        head = 0
        
        while head < len(queue):
            curr = queue[head]
            head += 1
            
            if curr not in history:
                history[curr] = (players[curr], counts[curr])
                
            c_player = players[curr]
            
            # If an enemy cell is caught in the blast, capture it first
            if c_player != NONE and c_player != player:
                enemy_count = counts[curr]
                if c_player == RED:
                    self.red_orbs -= enemy_count
                else:
                    self.blue_orbs -= enemy_count
                    
                if player == RED:
                    self.red_orbs += enemy_count
                else:
                    self.blue_orbs += enemy_count
            
            counts[curr] += 1
            players[curr] = player
            
            if player == RED:
                self.red_orbs += 1
            else:
                self.blue_orbs += 1
            
            # Check explosion
            if counts[curr] == capacities[curr]:
                exploded_count = counts[curr]
                counts[curr] = 0
                players[curr] = NONE
                
                if player == RED:
                    self.red_orbs -= exploded_count
                else:
                    self.blue_orbs -= exploded_count
                    
                queue.extend(neighbors[curr])
                
            # THE CRITICAL FIX: Stop the physics simulation if a player is wiped out
            if move_counter >= 2 and (self.red_orbs == 0 or self.blue_orbs == 0):
                break
                
        return history

    def undoMove(self, history):
        if not history: return
        self.red_orbs, self.blue_orbs = history.pop('_orbs')
        for idx, (old_player, old_count) in history.items():
            self.players[idx] = old_player
            self.counts[idx] = old_count

    def isTerminal(self, move_counter):
        if move_counter < 2: return False
        return self.red_orbs == 0 or self.blue_orbs == 0

    def evaluate(self, player, move_counter):
        my_orbs = self.red_orbs if player == RED else self.blue_orbs
        opp_orbs = self.blue_orbs if player == RED else self.red_orbs
        
        if move_counter >= 2:
            if opp_orbs == 0 and my_orbs > 0: return 100000
            if my_orbs == 0 and opp_orbs > 0: return -100000
        
        score = 0
        players = self.players
        counts = self.counts
        caps = Board._capacities
        
        for i in range(self.N):
            p = players[i]
            if p == NONE: continue
            
            c = counts[i]
            cap = caps[i]
            multiplier = 1 if p == player else -1
            
            score += (c * 2) * multiplier
            if c == cap - 1:
                score += 3 * multiplier
            if cap == 2: 
                score += 2 * multiplier
            elif cap == 3: 
                score += 1 * multiplier
                
        score += (my_orbs - opp_orbs) * 5
        return score

    def getLegalMoves(self, player):
        return [i for i, p in enumerate(self.players) if p == NONE or p == player]


class TimeManager:
    def __init__(self, time_limit):
        self.start = time.time()
        self.limit = time_limit
        self.nodes = 0

    def is_out_of_time(self):
        self.nodes += 1
        if self.nodes & 1023 == 0:
            return (time.time() - self.start) > self.limit
        return False


def minimax(board, depth, alpha, beta, maximizing_player, player, move_counter, tm):
    if tm.is_out_of_time():
        raise TimeoutError()

    if depth == 0 or board.isTerminal(move_counter):
        return board.evaluate(player, move_counter), None
    
    best_move = None
    current_player = player if maximizing_player else (RED if player == BLUE else BLUE)
    legal_moves = board.getLegalMoves(current_player)
    
    if not legal_moves:
        return board.evaluate(player, move_counter), None
    
    if maximizing_player:
        max_eval = float('-inf')
        for move_idx in legal_moves:
            history = board.makeMove(move_idx, current_player, move_counter)
            if history is None: continue
            
            eval_score, _ = minimax(board, depth - 1, alpha, beta, False, player, move_counter + 1, tm)
            board.undoMove(history)
            
            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move_idx
            alpha = max(alpha, eval_score)
            if beta <= alpha: break
        return max_eval, best_move
    else:
        min_eval = float('inf')
        for move_idx in legal_moves:
            history = board.makeMove(move_idx, current_player, move_counter)
            if history is None: continue
            
            eval_score, _ = minimax(board, depth - 1, alpha, beta, True, player, move_counter + 1, tm)
            board.undoMove(history)
            
            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move_idx
            beta = min(beta, eval_score)
            if beta <= alpha: break
        return min_eval, best_move


def getBestMove(board, depth = 4):
    player = RED if board.me == 1 else BLUE
    
    time_left = board.my_time
    if time_left > 100: 
        time_left /= 1000.0 
        
    time_limit = min(1.5, max(0.5, time_left * 0.10))
    if time_left < 2.0: 
        time_limit = max(0.1, time_left * 0.5)
        
    tm = TimeManager(time_limit)
    best_move_idx = None
    depth = 1
    
    legal_moves = board.getLegalMoves(player)
    if not legal_moves: return None
    
    root_moves = []
    caps = Board._capacities
    for idx in legal_moves:
        prio = 0
        if caps[idx] == 2: prio += 3
        if board.players[idx] == player and board.counts[idx] == caps[idx] - 1: prio += 5
        root_moves.append((prio, idx))
    root_moves.sort(key=lambda x: x[0], reverse=True)
    ordered_legal_moves = [m[1] for m in root_moves]
    
    while True:
        try:
            max_eval = float('-inf')
            current_best_move = None
            alpha = float('-inf')
            beta = float('inf')
            
            for move_idx in ordered_legal_moves:
                history = board.makeMove(move_idx, player, board.move_number)
                if history is None: continue
                
                eval_score, _ = minimax(board, depth - 1, alpha, beta, False, player, board.move_number + 1, tm)
                board.undoMove(history)
                
                if eval_score > max_eval:
                    max_eval = eval_score
                    current_best_move = move_idx
                alpha = max(alpha, eval_score)
                
            if current_best_move is not None:
                best_move_idx = current_best_move
                
            depth += 1
            if depth > 12: break 
            
        except TimeoutError:
            break 
            
    if best_move_idx is None:
        best_move_idx = ordered_legal_moves[0]

    row = best_move_idx // board.cols
    col = best_move_idx % board.cols
    return row, col

def play_move(row, col):
    print(f"{row} {col}", flush=True)

if __name__ == "__main__":
    while True:
        try:
            line = input()
            if not line: break
            board = Board(line)
            move = getBestMove(board)
            if move: play_move(move[0], move[1])
        except EOFError:
            break