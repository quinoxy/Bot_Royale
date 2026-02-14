from enum import Enum

# Window settings
WIDTH, HEIGHT = 1000, 1000

# Colors
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)

# Game settings
ROWS = 7
COLS = 7
MAX_MOVES = 1000

class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2