#include "globals.hpp"
#include "input.hpp"
// Arbitrary large number to prevent infinite games

int main(){

    // Initializations
    Board board(ROWS, COLS);
    board.display();
    int moveCounter = 0;

    // Main game loop
    while (true){

        Player player;

        // Choosing player based on move counter
        if (moveCounter%2 == 0){
            player = Player::RED;
            std::cout << "Red's turn. Enter your move (x y): ";
        }
        else {
            player = Player::BLUE;
            std::cout << "Blue's turn. Enter your move (x y): ";
        }

        // Get user input for move
        Position pos = get_input();
        int x = pos.x;
        int y = pos.y;

        // Attempt to make the move, if it's invalid, ask for input again
        if (!board.makeMove(x, y, player)){
            std::cout << "Invalid move. Try again." << std::endl;
            continue;
        }

        board.display();

        // Check for win condition after the move
        if (board.checkWin(moveCounter, player)){
            std::cout << (player == Player::RED ? "Red" : "Blue") << " wins!" << std::endl;
            break;
        }

        moveCounter++;

        // If move counter exceeds threshold, declare a draw and end the game
        if (moveCounter >= TOTAL_MOVES_THRESHOLD){
            std::cout << "Game ended in a draw!" << std::endl;
            break;
        }
    }
}