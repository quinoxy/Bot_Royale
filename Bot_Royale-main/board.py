
import pygame
from constants import *
from draw import draw_intermediaries




class BoardCell:
    def __init__(self):
        self.player = Player.NONE
        self.count = 0

class Position:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class VisualUpdate:
    def __init__(self, from_pos, to_pos, player, num_pieces_in_cell):
        self.from_pos = from_pos
        self.to_pos = to_pos
        self.player = player
        self.num_pieces_in_cell = num_pieces_in_cell

class Board:
    def __init__(self, rows, cols, win):
        self.rows = rows
        self.cols = cols
        self.board = [[BoardCell() for _ in range(cols)] for _ in range(rows)]
        self.win = win

    def display(self):
        for i in range(self.rows):
            row_display = []
            for j in range(self.cols):
                cell = self.board[i][j]
                if cell.player == Player.NONE:
                    row_display.append('. ')
                elif cell.player == Player.RED:
                    row_display.append(f'R{cell.count}')
                elif cell.player == Player.BLUE:
                    row_display.append(f'B{cell.count}')
            print('|'.join(row_display))

    def makeMove(self, x, y, player):
        
        # Validate the move before making it
        if (player == Player.NONE):
            print("Invalid player. Player cannot be NONE.")
            return False
        
        if (not self.checkValidCell(x, y)):
            print("Invalid move. Cell coordinates are out of bounds.")
            return False
        
        if (self.board[x][y].player != Player.NONE and self.board[x][y].player != player):
            print("Invalid move. Cell is occupied by the opponent.")
            return False

        
        # queue fro processing cell updates, starting with initial move
        update_queue = [[Position(x, y), Position(x, y)]] # pair to store from where to where does the piece go

        # each iteration of this loop will process all updates that are still pending
        
        while update_queue:

            num_updates_in_this_turn = len(update_queue)
            visual_updates_this_turn = [] 
            next_update_queue = []
            
            # process all the updates in the current queue
            for i in range(num_updates_in_this_turn):

                update = update_queue[i]
                from_pos = update[0]
                to_pos = update[1]

                cell = self.board[to_pos.x][to_pos.y]

                cell.count += 1
                cell.player = player

                # add the visual update for this move to the list of updates
                
                # if the cell is exploding, reset it and add its neighbors to the next update queue
                if self.cellExploding(to_pos.x, to_pos.y):
                    cell.count = 0
                    cell.player = Player.NONE

                    dir = [[-1, 0], [1, 0], [0, -1], [0, 1]]
                    # add adjacent cells to the next update queue
                    for d in dir:
                        new_x = to_pos.x + d[0]
                        new_y = to_pos.y + d[1]
                        if self.checkValidCell(new_x, new_y):
                            next_update_queue.append([Position(to_pos.x, to_pos.y), Position(new_x, new_y)])
                            visual_updates_this_turn.append(VisualUpdate(to_pos, Position(new_x, new_y), player, self.board[new_x][new_y].count + 1)) # +1 because the piece will be added to the new cell in the next update
            # move to the next set of updates for the next iteration
            update_queue = next_update_queue

            #once all updates for this turn are processed, add the visual updates to the main list of visual updates to be shown by the display module
            draw_intermediaries(player, self, visual_updates_this_turn)

        return True

    def checkWin(self, move_counter, player):

        if move_counter < 2:
            return False

        # if any cell is occupied by the opponent, return False
        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j].player != player and self.board[i][j].player != Player.NONE:
                    return False

        return True

    
    def checkValidCell(self, x, y):
        return 0 <= x < self.rows and 0 <= y < self.cols
    

    def cellExploding (self, x, y):
        if (not self.checkValidCell(x, y)):
            return False

        threshold = 4

        # incase we want the cell to explode regardless of it being on the edge at 4 pieces, comment out the next 4 lines
        if (x == 0 or x == self.rows - 1):
            threshold -= 1
        if (y == 0 or y == self.cols - 1):
            threshold -= 1

        return self.board[x][y].count >= threshold        