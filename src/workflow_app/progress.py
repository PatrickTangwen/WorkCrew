"""Stage-level progress output (plan section 33): plain lines on stderr."""

import sys


def emit(message):
    print(f"[workflow] {message}", file=sys.stderr)
