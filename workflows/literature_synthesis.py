"""Run the synthesize research workflow."""

try:
    from workflows._runner import run
except ModuleNotFoundError:  # Direct execution from the workflows directory.
    from _runner import run


if __name__ == "__main__":
    raise SystemExit(run("synthesize"))
