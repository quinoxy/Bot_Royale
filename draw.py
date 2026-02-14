import pygame
from constants import *



FRAMES_TO_UPDATE = 8  # number of frames to show the visual updates for each turn

def draw(player, board, update = True):
    WIN = board.win
    WIN.fill(BLACK)
    
    line_color = WHITE
    if (player == Player.RED):
        line_color = RED
    elif (player == Player.BLUE):
        line_color = BLUE

    # draw the grid first
    cell_width = WIDTH//(COLS + 2) # +2 for padding on both sides
    cell_height = HEIGHT//(ROWS + 2) # +2 for padding on both
    for i in range(ROWS + 1):
        pygame.draw.line(WIN, line_color, (cell_width, cell_height * (i + 1)), (WIDTH - cell_width, cell_height * (i + 1)), 2)
    for j in range(COLS + 1):
        pygame.draw.line(WIN, line_color, (cell_width * (j + 1), cell_height), (cell_width * (j + 1), HEIGHT - cell_height), 2)

    # draw board cells
    for i in range(board.rows):
        for j in range(board.cols):
            cell = board.board[i][j]
            if cell.player != Player.NONE:
                color = RED if cell.player == Player.RED else BLUE
                if cell.count == 1:
                    center_x = cell_width * (j + 1.5)
                    center_y = cell_height * (i + 1.5)
                    pygame.draw.circle(WIN, color, (int(center_x), int(center_y)), min(cell_width, cell_height) // 5)
                elif cell.count == 2:
                    center_x1 = cell_width * (j + 1.25)
                    center_y1 = cell_height * (i + 1.5)
                    center_x2 = cell_width * (j + 1.75)
                    center_y2 = cell_height * (i + 1.5)
                    pygame.draw.circle(WIN, color, (int(center_x1), int(center_y1)), min(cell_width, cell_height) // 5)
                    pygame.draw.circle(WIN, color, (int(center_x2), int(center_y2)), min(cell_width, cell_height) // 5)
                elif cell.count == 3:
                    center_x1 = cell_width * (j + 1.25)
                    center_y1 = cell_height * (i + 1.25)
                    center_x2 = cell_width * (j + 1.75)
                    center_y2 = cell_height * (i + 1.25)
                    center_x3 = cell_width * (j + 1.5)
                    center_y3 = cell_height * (i + 1.75)
                    pygame.draw.circle(WIN, color, (int(center_x1), int(center_y1)), min(cell_width, cell_height) // 5)
                    pygame.draw.circle(WIN, color, (int(center_x2), int(center_y2)), min(cell_width, cell_height) // 5)
                    pygame.draw.circle(WIN, color, (int(center_x3), int(center_y3)), min(cell_width, cell_height) // 5)
    if update:
        pygame.display.update()


def draw_intermediaries(player, board, visual_updates):
    
    
    visual_updates_to_be_processed = []
    for update in visual_updates:
        if (update.from_pos.x == update.to_pos.x and update.from_pos.y == update.to_pos.y):
            continue  # skip if the piece didn't actually move (i.e. it just exploded in place)
        visual_updates_to_be_processed.append(update)

    if len(visual_updates_to_be_processed) == 0:
        return
    

    for i in range(FRAMES_TO_UPDATE):
        draw(player, board, update = False)
        # code to draw the visual updates one by one with a small delay in between
        # something like
        for update in visual_updates_to_be_processed:
            if (update.from_pos.x == update.to_pos.x and update.from_pos.y == update.to_pos.y):
                continue  # skip if the piece didn't actually move (i.e. it just exploded in place)
            # draw the update on the board
            # for example, if the update is a piece moving from (x1, y1) to (x2, y2), you can draw a circle at (x2, y2) with the player's color
            cell_width = WIDTH//(COLS + 2) # +2 for padding on either side
            cell_height = HEIGHT//(ROWS + 2) # +2 for padding on either side
            color = RED if update.player == Player.RED else BLUE
            from_center_x = cell_width * (update.from_pos.y + 1.5)
            from_center_y = cell_height * (update.from_pos.x + 1.5)
            to_center_x = cell_width * (update.to_pos.y + 1.5)
            to_center_y = cell_height * (update.to_pos.x + 1.5)
            # interpolate between from and to positions
            center_x = from_center_x + (to_center_x - from_center_x) * i / FRAMES_TO_UPDATE
            center_y = from_center_y + (to_center_y - from_center_y) * i / FRAMES_TO_UPDATE
            pygame.draw.circle(board.win, color, (int(center_x), int(center_y)), min(cell_width, cell_height) // 5)
        pygame.display.update()
        pygame.time.delay(16)  # delay for 500 milliseconds between updates

