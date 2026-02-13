from input import get_input
from board import Board, Player

ROWS = 7
COLS = 7
MAX_MOVES = 1000

def main():
    # Initialize board and other necessary components
    board = Board(ROWS, COLS)
    board.display()
    move_counter = 0

    while True:

        player = Player.NONE
        if move_counter % 2 == 0:
            player = Player.RED
            print("Red's turn")
        else:
            player = Player.BLUE
            print("Blue's turn")
        
        # Get input from user
        x, y = get_input()

        # Try to make move and check if it's valid
        if not board.makeMove(x, y, player):
            print("Invalid move, try again.")
            continue
        
        board.display()

        # Check for win condition after the move
        if board.checkWin(move_counter, player):
            color = "Red" if player == Player.RED else "Blue"
            print(f"{color} wins!")
            break
        
        move_counter += 1

        # Check for draw condition
        if (move_counter >= MAX_MOVES):
            print("Game ended in a draw!")
            break

if __name__ == "__main__":
    main()