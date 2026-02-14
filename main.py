import board
from input import get_input
from board import Board, Player
from draw import draw
from constants import *
import pygame
import time

WIN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Bot Royale")
clock = pygame.time.Clock()




def main():
    # Initialize board and other necessary components
    board = Board(ROWS, COLS, WIN)
    draw(Player.NONE, board)
    move_counter = 0
    run = True
    winning_player = Player.NONE

    while run:
        player = Player.NONE
        if move_counter % 2 == 0:
            player = Player.RED
        else:
            player = Player.BLUE

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False

            if event.type == pygame.MOUSEBUTTONDOWN:
                coord_x, coord_y = pygame.mouse.get_pos()
                cell_width = WIDTH//(COLS + 2) # +2 for padding on either side
                cell_height = HEIGHT//(ROWS + 2) # +2 for padding on either side
                y = (coord_x - cell_width) // cell_width
                x = (coord_y - cell_height) // cell_height


                if 0 <= x < COLS and 0 <= y < ROWS:
                    # Try to make move and check if it's valid
                    if not board.makeMove(x, y, player):
                        continue
                    
                    # Check for win condition after the move
                    if board.checkWin(move_counter, player):
                        color = "Red" if player == Player.RED else "Blue"
                        print(f"{color} wins!")
                        run = False
                        winning_player = player
                    
                    move_counter += 1
        if not run:
            break
        # Check for draw condition
        if (move_counter >= MAX_MOVES):
            print("Game ended in a draw!")
            run = False

        if move_counter % 2 == 0:
            player = Player.RED
        else:
            player = Player.BLUE
        draw(player, board)
        clock.tick(60)

    run = True
    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
        draw(winning_player, board)
        clock.tick(60)
    
    pygame.quit()
        
        

if __name__ == "__main__":
    main()