#!/usr/bin/env python3
"""
Autonomous GitHub Copilot repository refinement loop.
Run from the root of your repository.

Usage:
    python copilot_auto_refiner.py

It repeatedly asks GitHub Copilot to:
  1. inspect the repository
  2. identify problems
  3. decide what changes are needed
  4. implement those changes
  5. run tests
  6. inspect the result again

No new prompt is required after starting.
"""

import subprocess
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

MAX_ROUNDS = 10
COPILOT_TIMEOUT = 300  # 5 minutes per invocation
STATE_FILE = ".copilot_refiner_state.json"
GITIGNORE_ADDITIONS = f"\n{STATE_FILE}\n"


def check_copilot_available() -> bool:
    """Verify that GitHub Copilot CLI is installed and accessible."""
    try:
        result = subprocess.run(
            ["copilot", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_copilot(instruction: str) -> bool:
    """Send an instruction to GitHub Copilot CLI with timeout and error handling."""
    command = [
        "copilot",
        "-p",
        instruction,
        "--allow-all-tools",
    ]

    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=COPILOT_TIMEOUT,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"\nCopilot error (exit code {result.returncode}):")
            print(result.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"ERROR: Copilot did not respond within {COPILOT_TIMEOUT} seconds.")
        return False
    except FileNotFoundError:
        print("ERROR: Copilot CLI not found. Install GitHub Copilot CLI first.")
        return False


def git_status() -> str:
    """Get short git status."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return "ERROR: git status timeout"
    except FileNotFoundError:
        return "ERROR: git not found"


def git_diff_stat() -> str:
    """Get git diff statistics."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        return result.stdout if result.stdout.strip() else "No changes"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(could not retrieve diff stat)"


def run_tests() -> Tuple[bool, str]:
    """Run the project's test suite. Returns (success, output)."""
    print("\n" + "=" * 70)
    print("RUNNING TESTS")
    print("=" * 70)

    try:
        result = subprocess.run(
            ["python", "-m", "unittest", "discover", "-q"],
            text=True,
            capture_output=True,
            timeout=120,
            cwd=".",
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        print(output if output else "All tests passed.")
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 120 seconds"
    except FileNotFoundError:
        return False, "Python or unittest not available"


def save_state(round_number: int, status: str) -> None:
    """Save refinement state to file."""
    state = {
        "round": round_number,
        "status": status,
        "timestamp": time.time(),
    }
    try:
        Path(STATE_FILE).write_text(
            json.dumps(state, indent=2),
            encoding="utf-8"
        )
    except IOError as e:
        print(f"Warning: Could not save state file: {e}")


def load_state() -> Optional[dict]:
    """Load refinement state from file."""
    if Path(STATE_FILE).exists():
        try:
            return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
        except (IOError, json.JSONDecodeError):
            return None
    return None


def add_to_gitignore(entry: str) -> None:
    """Add entry to .gitignore if not already present."""
    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if entry.strip() not in content:
            gitignore_path.write_text(
                content.rstrip() + GITIGNORE_ADDITIONS,
                encoding="utf-8"
            )
    else:
        gitignore_path.write_text(GITIGNORE_ADDITIONS.lstrip(), encoding="utf-8")


def main() -> None:
    """Main refinement loop."""
    if not Path(".git").exists():
        print("ERROR: Run this from the root of a Git repository.")
        sys.exit(1)

    if not check_copilot_available():
        print("ERROR: GitHub Copilot CLI is not installed or not in PATH.")
        print("Install it with: npm install -g @github/copilot-cli")
        sys.exit(1)

    print("=" * 70)
    print("        GITHUB COPILOT AUTONOMOUS REFINER")
    print("=" * 70)
    print()
    print(f"Max rounds: {MAX_ROUNDS}")
    print(f"Timeout per invocation: {COPILOT_TIMEOUT}s")
    print()

    add_to_gitignore(STATE_FILE)

    previous_status = load_state()
    if previous_status:
        print(f"Resuming from round {previous_status['round']}")
        print()

    for round_number in range(1, MAX_ROUNDS + 1):
        print("=" * 70)
        print(f"REFINEMENT ROUND {round_number}/{MAX_ROUNDS}")
        print("=" * 70)
        print()

        instruction = f"""
You are the autonomous senior engineer responsible for improving this repository.

This is refinement round {round_number}.

Do NOT ask the human what to change.

You must independently inspect the repository and decide what needs improvement.

WORKFLOW:

1. Inspect the entire repository structure and README.
2. Read the important source files.
3. Identify:
   - bugs
   - broken functionality
   - bad error handling
   - duplicated code
   - weak architecture
   - security problems
   - performance problems
   - poor documentation
   - missing tests
   - failing tests
   - incorrect assumptions
   - maintainability problems
4. Prioritize real problems over cosmetic changes.
5. Before changing anything, formulate an internal change plan.
6. Implement changes directly in the repository.
7. Add or improve tests for every meaningful change.
8. Run the project's existing tests.
9. If tests fail, investigate, fix, and re-run.
10. Reinspect modified code for regressions.
11. Do not rewrite working code unnecessarily.
12. Do not remove functionality to make tests pass.
13. Preserve existing public APIs unless changing them is necessary.
14. Preserve user-facing behaviour unless it is demonstrably incorrect.
15. Never invent dependencies when an existing dependency can be used.
16. Do not modify unrelated files.
17. Keep changes small, coherent, and production-quality.

IMPORTANT:

You are both the reviewer and implementer.
Do not stop after producing a review.
Actually make the required changes.
Do not wait for another human prompt.

When the repository is genuinely in good condition, do not manufacture changes.
Instead report:

REPOSITORY_STATUS: CLEAN

If there are still legitimate problems, continue fixing them.

At the end of this round, briefly report:
- problems found
- changes made
- tests executed
- remaining problems
- whether another round is required
"""

        success = run_copilot(instruction)

        if not success:
            print("\nCopilot returned an error. Stopping.")
            save_state(round_number, "copilot_error")
            break

        status = git_status()
        diff_stat = git_diff_stat()

        print("\n" + "=" * 70)
        print("GIT STATUS")
        print("=" * 70)
        print(status if status else "No uncommitted changes.")
        print("\nDIFF STAT:")
        print(diff_stat)
        print()

        if not status.strip():
            print("No changes detected. Checking repository status...")
            save_state(round_number, "no_changes")
        else:
            save_state(round_number, "changes_made")
            print("Running tests after changes...")
            test_success, test_output = run_tests()

            if not test_success:
                print("\nWARNING: Tests failed. Copilot may need to investigate.")

        # Final check: ask Copilot whether the repository is ready
        print("\n" + "=" * 70)
        print("FINAL REPOSITORY STATUS CHECK")
        print("=" * 70)
        print()

        final_check = run_copilot(
            """
Perform a final independent review of the repository.

Do not modify anything in this step.

Determine whether there are still meaningful bugs, failing tests, architectural problems,
security problems, or missing tests that should be addressed.

If the repository is genuinely ready and no further work is needed, output exactly:

REPOSITORY_STATUS: CLEAN

Otherwise output exactly:

REPOSITORY_STATUS: NEEDS_WORK
"""
        )

        if not final_check:
            print("\nFinal check failed. Stopping.")
            break

        print()
        print(f"Round {round_number} complete.")

    print()
    print("=" * 70)
    print("AUTONOMOUS REFINEMENT FINISHED")
    print("=" * 70)
    print()
    print("Review the Git diff before committing to main:")
    print()
    print(git_diff_stat())
    print()
    print("To stage and commit changes:")
    print("  git add -A")
    print("  git commit -m 'Autonomous refinement by Copilot'")
    print()


if __name__ == "__main__":
    main()
