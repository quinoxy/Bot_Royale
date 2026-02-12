#include <vector>

enum struct Player{
    NONE,
    RED,
    BLUE
};

struct Position{
    int x;
    int y;
};

struct visualUpdate{
    Position from;
    Position to;
    Player player;
    int numPiecesInReceivingCell;
};

struct BoardCell{
    int numPieces;
    Player owner; 
};

class Board{

public:
    Board(int rows, int cols);
    void display();
    bool makeMove(int x, int y, Player player);
    bool cellExploding(int x, int y);
    bool checkValidCell(int x, int y);
    

    
private:
    std::vector<std::vector<BoardCell>> grid;
    int rows;
    int cols;
};