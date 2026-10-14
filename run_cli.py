# Launch the console interface: python run_cli.py
from bingo.cli import main

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")