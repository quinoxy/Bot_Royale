#include "board.hpp"

Board::Board(int rows, int cols) : rows(rows), cols(cols) {
    grid.resize(rows, std::vector<BoardCell>(cols, {0, Player::NONE}));
}

bool Board::makeMove(int x, int y, Player player){
    if (player == Player::NONE) {
        return false; // Invalid player
    }
    if (x < 0 || x >= rows || y < 0 || y >= cols) {
        return false; // Out of bounds
    }
    if (grid[x][y].owner != Player::NONE && grid[x][y].owner != player) {
        return false; // Cell already occupied
    }

    // This will hold all visual updates for this turn
    std::vector<std::vector<visualUpdate>> updates;

    // Queue for processing cell updates, starting with the initial move
    std::vector<std::pair<Position, Position>> updateQueue = {{{x, y}, {x, y}}}; // Pair to store from where to where does the piece go

    // Each iteration of the loop process all updates that are still in queue
    
    while (!updateQueue.empty()){

        int numUpdatesInThisTurn = updateQueue.size();
        std::vector<visualUpdate> currentTurnUpdates;
        std::vector<std::pair<Position, Position>> nextUpdateQueue;
        
        // Process all updates in the current queue
        for (int i = 0; i < numUpdatesInThisTurn; i++){
        
            Position fromPos = updateQueue[i].first;
            Position pos = updateQueue[i].second;
            int x = pos.x;
            int y = pos.y;

            grid[x][y].numPieces++;
            grid[x][y].owner = player;

            // Add visual update for this move
            currentTurnUpdates.push_back({fromPos, pos, player, grid[x][y].numPieces});

            // If the cell is exploding, reset it and add its neighbors to the next update queue
            if (cellExploding(x, y)){
                grid[x][y].numPieces = 0;
                grid[x][y].owner = Player::NONE;

                std::vector<Position> neighbors = {{x-1, y}, {x+1, y}, {x, y-1}, {x, y+1}};
                for (const auto& neighbor : neighbors){
                    if (checkValidCell(neighbor.x, neighbor.y)){
                        nextUpdateQueue.push_back({pos, neighbor});
                    }
                }
            }
        }

        // Move to the next set of updates for the next iteration
        updateQueue = nextUpdateQueue;
        
        // After processing all updates for this turn, add them to the visual updates list
        if (!currentTurnUpdates.empty()){
            updates.push_back(currentTurnUpdates);
        }
    }

    // Send visualization updates to screen
    // This looks something like:
    // screen->applyVisualUpdates(updates);


    return true;
}


bool Board::checkValidCell(int x, int y) {
    return x >= 0 && x < rows && y >= 0 && y < cols;
}
bool Board::cellExploding(int x, int y) {
    if (x < 0 || x >= rows || y < 0 || y >= cols) {
        return false; // Out of bounds
    }
    int threshold = 4; // Example threshold for explosion

    // If we want a cell to explode only if it has 4 atoms in it, comment out the next 2 lines
    if (x == 0 || x == rows - 1) threshold--; // Edge cells have a lower threshold
    if (y == 0 || y == cols - 1) threshold--; // Edge cells have a lower threshold

    return grid[x][y].numPieces >= threshold;
}

bool Board::checkWin(int plyNumber, Player player){
    if (plyNumber < 2) {
        return false; // Not enough moves have been made to determine a winner
    }

    Player opponent = (player == Player::RED) ? Player::BLUE : Player::RED;

    // Check if the opponent has any pieces left on the board
    for (const auto& row : grid) {
        for (const auto& cell : row) {
            if (cell.owner == opponent) {
                return false; // Opponent still has pieces, no winner yet
            }
        }
    }

    return true; // Opponent has no pieces left, current player wins

}

void Board::display(){
    for (int i = 0; i < rows; i++){
        for (int j = 0; j < cols; j++){
            char cellChar = '.';
            if (grid[i][j].owner == Player::RED) {
                cellChar = 'R';
            } else if (grid[i][j].owner == Player::BLUE) {
                cellChar = 'B';
            }
            if (grid[i][j].numPieces == 0) {
                std::cout << "... | ";
            } else {
                std::cout << cellChar << grid[i][j].numPieces << " | ";
            }
            
        }
        std::cout << std::endl;
    }
}