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

    //this will hold all visual updates for this turn
    std::vector<std::vector<visualUpdate>> updates;

    // Queue for processing cell updates, starting with the initial move
    std::vector<std::pair<Position, Position>> updateQueue = {{{x, y}, {x, y}}}; //pair to store from where to where does the piece go

    //Each iteration of the loop process all updates that are still in queue
    
    while (!updateQueue.empty()){
        int numUpdatesInThisTurn = updateQueue.size();
        std::vector<visualUpdate> currentTurnUpdates;
        std::vector<std::pair<Position, Position>> nextUpdateQueue;
        for (int i = 0; i < numUpdatesInThisTurn; i++){
            Position fromPos = updateQueue[i].first;
            Position pos = updateQueue[i].second;
            int x = pos.x;
            int y = pos.y;

            grid[x][y].numPieces++;
            grid[x][y].owner = player;

            currentTurnUpdates.push_back({fromPos, pos, player, grid[x][y].numPieces});

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
        updateQueue = nextUpdateQueue;
        if (!currentTurnUpdates.empty()){
            updates.push_back(currentTurnUpdates);
        }
    }

    // Send visualization updates to screen



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

    //if we want a cell to explode only if it has 4 atoms in it, comment out the next 2 lines
    if (x == 0 || x == rows - 1) threshold--; // Edge cells have a lower threshold
    if (y == 0 || y == cols - 1) threshold--; // Edge cells have a lower threshold

    return grid[x][y].numPieces >= threshold;
}