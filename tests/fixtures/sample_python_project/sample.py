"""Sample module for testing LSP capabilities."""


class Calculator:
    """A simple arithmetic calculator."""

    def __init__(self, initial_value: int = 0) -> None:
        self.value: int = initial_value

    def add(self, amount: int) -> int:
        """Add amount to the internal value and return result."""
        self.value += amount
        return self.value

    def subtract(self, amount: int) -> int:
        """Subtract amount from internal value."""
        self.value -= amount
        return self.value


def compute_total(a: int, b: int) -> int:
    """Compute sum using Calculator class."""
    calc = Calculator(a)
    return calc.add(b)


def main_entry() -> None:
    res = compute_total(10, 20)
    print(f"Result: {res}")


if __name__ == "__main__":
    main_entry()
