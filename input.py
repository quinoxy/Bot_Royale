def get_input():
    while True:
        try:
            move = input("Enter your move (x y): ")
            x, y = map(int, move.split())
            return x, y
        except ValueError:
            print("Invalid input. Please enter two integers separated by a space.")