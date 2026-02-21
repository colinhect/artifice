"""Sample Python module for testing tool operations."""


def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"


def calculate_sum(numbers: list[int]) -> int:
    """Calculate the sum of a list of numbers."""
    return sum(numbers)


def process_data(data: dict) -> dict:
    """Process input data and return transformed result."""
    result = {
        "original": data,
        "count": len(data),
        "keys": list(data.keys()),
    }
    return result


class DataProcessor:
    """A class for processing data."""

    def __init__(self, name: str):
        self.name = name
        self._cache: dict = {}

    def process(self, item: dict) -> dict:
        """Process a single item."""
        key = item.get("id", "unknown")
        if key not in self._cache:
            self._cache[key] = self._transform(item)
        return self._cache[key]

    def _transform(self, item: dict) -> dict:
        """Transform an item."""
        return {k: v for k, v in item.items() if v is not None}


async def fetch_remote_data(url: str) -> dict:
    """Fetch data from a remote URL."""
    # This is a placeholder for async operations
    return {"url": url, "status": "simulated"}


if __name__ == "__main__":
    print(greet("World"))
    print(calculate_sum([1, 2, 3, 4, 5]))
