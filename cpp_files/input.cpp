#include "input.hpp"

Position get_input(){
    int x, y;
    std::cout << "Enter your move (x y): ";
    std::cin >> x >> y;
    return {x, y};
}