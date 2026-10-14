import random

BINGO_RANGES = {
    "B": range(1, 16),
    "I": range(16, 31),
    "N": range(31, 46),
    "G": range(46, 61),
    "O": range(61, 76)
}

# Create and shuffle all 75 BINGO calls.
def create_game():
    calls = []

    for letter, numbers in BINGO_RANGES.items():
        for number in numbers:
            calls.append({
                "letter": letter,
                "number": number
            })

    random.shuffle(calls)
    return calls

# Draw the next BINGO call.
# Returns a dictionary or None if no calls remain.
def next_call(remaining_calls):
    if not remaining_calls:
        return None

    return remaining_calls.pop()

# Convert a BINGO call into readable text.
def format_call(call):
    if call is None:
        return "No calls remaining"

    return f"{call['letter']}-{call['number']}"

# Return all previously called numbers.
def get_history(called_numbers):
    return called_numbers.copy()

# Return the number of calls remaining.
def get_remaining_count(remaining_calls):
    return len(remaining_calls)

def run_console():

    while True:
        remaining = create_game()
        history = []

        print("\n===== NEW BINGO GAME =====")
        print("ENTER = Next call")
        print("H = Call history")
        print("R = Restart")
        print("Q = Quit")

        while True:
            command = input("\nCommand: ").strip().lower()

            if command == "":
                call = next_call(remaining)

                if call is None:
                    print("All 75 numbers have been called!")
                    continue

                history.append(call)

                print(f"\n>>> {format_call(call)} <<<")
                print(f"Remaining: {get_remaining_count(remaining)}")

            elif command == "h":
                print("\nCall History:")

                for call in get_history(history):
                    print(format_call(call), end="  ")

                print()

            elif command == "r":
                print("Starting a new game...")
                break

            elif command == "q":
                print("Goodbye!")
                return

            else:
                print("Invalid command.")

if __name__ == "__main__":
    run_console()