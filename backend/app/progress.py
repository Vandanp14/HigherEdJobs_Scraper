from datetime import datetime


def report(source: str, message: str) -> None:
    """Print one progress line to the terminal running the server, e.g. `14:20:05 [AIR] Found 19 listings`."""
    print(f"{datetime.now():%H:%M:%S} [{source}] {message}", flush=True)


def elapsed(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds:02d}s"
