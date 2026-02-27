import board
from board import Board, Player
from draw import draw
from constants import *
import pygame
import time
import subprocess

pygame.init()
WIN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Bot Royale")
clock = pygame.time.Clock()

# ================= GAME CONFIG =================

class GameMode:
    HUMAN_VS_HUMAN = 0
    HUMAN_VS_BOT = 1
    BOT_VS_BOT = 2

MODE = GameMode.BOT_VS_BOT  # Change mode here

# Which side the bot plays in HUMAN_VS_BOT mode
# (the other side is human)
RED_IS_BOT = False
BLUE_IS_BOT = True

RED_BOT_PATH = "bot.py"
BLUE_BOT_PATH = "bot.py"

INITIAL_TIME = 60.0  # seconds per player

# ===============================================


def get_bot_move(bot_path, game_board, player, move_counter, my_time, opp_time):
    """Spawn bot subprocess, send board state as JSON, read back 'row col'."""
    state_json = game_board.serialize(player, move_counter, my_time, opp_time)

    start_time = time.time()

    process = subprocess.Popen(
        ["python3", bot_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        stdout, stderr = process.communicate(state_json + "\n", timeout=my_time)
    except subprocess.TimeoutExpired:
        process.kill()
        return None, 0  # timeout

    move_time = time.time() - start_time
    remaining_time = my_time - move_time

    if stderr:
        print(f"Bot stderr: {stderr.strip()}")

    if stdout:
        try:
            row, col = map(int, stdout.strip().split())
            return (row, col), remaining_time
        except Exception:
            print(f"Bot returned invalid output: {stdout.strip()}")
            return None, remaining_time

    return None, remaining_time


def is_bot_turn(player):
    """Determine if the current player is controlled by a bot."""
    if MODE == GameMode.HUMAN_VS_HUMAN:
        return False
    elif MODE == GameMode.BOT_VS_BOT:
        return True
    else:  # HUMAN_VS_BOT
        if player == Player.RED and RED_IS_BOT:
            return True
        if player == Player.BLUE and BLUE_IS_BOT:
            return True
        return False


def handle_bot_turn(game_board, player, move_counter, red_time, blue_time):
    """Execute a bot turn. Returns (success, winning_player, move_counter, red_time, blue_time)."""
    bot_path = RED_BOT_PATH if player == Player.RED else BLUE_BOT_PATH
    my_time = red_time if player == Player.RED else blue_time
    opp_time = blue_time if player == Player.RED else red_time

    move, remaining_time = get_bot_move(
        bot_path, game_board, player, move_counter, my_time, opp_time
    )

    # Update clock
    if player == Player.RED:
        red_time = remaining_time
    else:
        blue_time = remaining_time

    opponent = Player.BLUE if player == Player.RED else Player.RED

    # Timeout = forfeit
    if remaining_time <= 0:
        print(f"{player.name} ran out of time! Forfeit.")
        return False, opponent, move_counter, red_time, blue_time

    # No move = forfeit
    if move is None:
        print(f"{player.name} failed to return a move! Forfeit.")
        return False, opponent, move_counter, red_time, blue_time

    x, y = move

    # Invalid move = forfeit
    if not game_board.makeMove(x, y, player):
        print(f"{player.name} made invalid move ({x}, {y})! Forfeit.")
        return False, opponent, move_counter, red_time, blue_time

    # Check win
    if game_board.checkWin(move_counter, player):
        print(f"{player.name} wins!")
        return False, player, move_counter + 1, red_time, blue_time

    return True, Player.NONE, move_counter + 1, red_time, blue_time


def main():
    game_board = Board(ROWS, COLS, WIN)
    draw(Player.NONE, game_board)

    move_counter = 0
    run = True
    winning_player = Player.NONE

    red_time = INITIAL_TIME
    blue_time = INITIAL_TIME

    while run:
        player = Player.RED if move_counter % 2 == 0 else Player.BLUE

        pygame.display.set_caption(
            f"Bot Royale | RED: {red_time:.2f}s | BLUE: {blue_time:.2f}s"
        )

        # ================= BOT TURN =================
        if is_bot_turn(player):
            # Process pygame events so window stays responsive
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run = False
                    break

            if not run:
                break

            success, winner, move_counter, red_time, blue_time = handle_bot_turn(
                game_board, player, move_counter, red_time, blue_time
            )

            if not success:
                winning_player = winner
                run = False
                break

            time.sleep(0.2)  # small delay so you can see bot moves

        # ================= HUMAN TURN =================
        else:
            move_made = False
            while not move_made and run:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        run = False
                        move_made = True
                        break

                    if event.type == pygame.MOUSEBUTTONDOWN:
                        coord_x, coord_y = pygame.mouse.get_pos()
                        cell_width = WIDTH // (COLS + 2)
                        cell_height = HEIGHT // (ROWS + 2)
                        y = (coord_x - cell_width) // cell_width
                        x = (coord_y - cell_height) // cell_height

                        if 0 <= x < ROWS and 0 <= y < COLS:
                            if game_board.makeMove(x, y, player):
                                if game_board.checkWin(move_counter, player):
                                    print(f"{player.name} wins!")
                                    winning_player = player
                                    run = False
                                move_counter += 1
                                move_made = True
                                break

                draw(player, game_board)
                clock.tick(60)

        draw(player, game_board)
        clock.tick(60)

        # Draw condition
        if move_counter >= MAX_MOVES:
            print("Game ended in a draw!")
            break

    # Final display loop — keep showing the end state
    final_run = True
    while final_run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                final_run = False
        draw(winning_player, game_board)
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()