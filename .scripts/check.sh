#!/bin/bash
# Run every static check the project uses. Exit code is non-zero if any fails.
set -u
status=0

echo "Formatting (ruff format --check)..."
uv run ruff format --check . || status=1

echo "Linting (ruff check)..."
uv run ruff check . || status=1

echo "Type checks (mypy)..."
uv run mypy src/ app.py boot.py || status=1

exit $status
