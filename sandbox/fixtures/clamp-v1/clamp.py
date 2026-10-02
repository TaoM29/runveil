def clamp(value: int, lower: int, upper: int) -> int:
    """Return value bounded by inclusive lower/upper limits."""
    return min(value, upper)
