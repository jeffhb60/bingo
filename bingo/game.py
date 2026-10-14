from dataclasses import dataclass
import random

@dataclass(frozen=True)
class Call:
    column: int
    letter: str
    value: str

    def __str__(self) -> str:
        divider = "-" if self.value.isdecimal() else ": "
        return f"{self.letter}{divider}{self.value}"

# Return a normalized game definition or raise ValueError.
def validate_game(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Game JSON must be an object.")

    name = data.get("name")
    word = data.get("word")
    columns = data.get("columns")
    free_center = data.get("free_center", True)

    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' must be a nonempty string.")
    if not isinstance(word, str) or len(word) != 5 or not word.isascii() or not word.isalpha():
        raise ValueError("'word' must contain exactly five letters A-Z.")
    if not isinstance(free_center, bool):
        raise ValueError("'free_center' must be true or false.")
    if not isinstance(columns, list) or len(columns) != 5:
        raise ValueError("'columns' must contain exactly five column objects.")

    normalized = []
    word = word.upper()
    for i, column in enumerate(columns):
        if not isinstance(column, dict):
            raise ValueError(f"Column {i + 1} must be an object.")
        letter = column.get("letter")
        if not isinstance(letter, str) or letter.upper() != word[i]:
            raise ValueError(f"Column {i + 1} letter must be '{word[i]}'.")
        items = column.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"Column {i + 1} must have at least one item.")
        values = []
        seen = set()
        for item in items:
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                raise ValueError(f"Column {i + 1}: items must be strings or integers.")
            value = str(item).strip()
            if not value:
                raise ValueError(f"Column {i + 1}: an item cannot be blank.")
            if value.casefold() in seen:
                raise ValueError(f"Column {i + 1}: duplicate item '{value}'.")
            seen.add(value.casefold())
            values.append(value)
        normalized.append({"letter": word[i], "items": values})

    return {
        "name": name.strip(),
        "word": word,
        "free_center": free_center,
        "columns": normalized,
    }

# A play session: one shuffled deck plus an advancing cursor.
class GameSession:

    def __init__(self, game: dict, *, rng: random.Random | None = None):
        self.game = validate_game(game)
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        self.deck = [
            Call(column=i, letter=column["letter"], value=value)
            for i, column in enumerate(self.game["columns"])
            for value in column["items"]
        ]
        self.rng.shuffle(self.deck)
        self.cursor = 0

    @property
    def remaining(self) -> int:
        return len(self.deck) - self.cursor

    @property
    def history(self) -> list[Call]:
        return self.deck[: self.cursor]

    @property
    def previous(self) -> Call | None:
        return self.deck[self.cursor - 1] if self.cursor else None

    def next_call(self) -> Call | None:
        if self.remaining == 0:
            return None
        call = self.deck[self.cursor]
        self.cursor += 1
        return call
