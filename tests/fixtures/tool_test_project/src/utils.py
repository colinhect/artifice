"""Utility functions for the sample project."""


def format_output(data: dict, indent: int = 2) -> str:
    """Format dictionary as a readable string."""
    lines = []
    for key, value in data.items():
        lines.append(f"{' ' * indent}{key}: {value}")
    return "\n".join(lines)


def validate_input(data: dict, required_keys: list[str]) -> bool:
    """Validate that data contains all required keys."""
    return all(key in data for key in required_keys)


def merge_configs(*configs: dict) -> dict:
    """Merge multiple configuration dictionaries."""
    result = {}
    for config in configs:
        result.update(config)
    return result
