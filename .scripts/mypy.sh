#!/bin/bash
echo "Running type checks..."
mypy src/ app.py --config-file mypy.ini

echo "Running linting..."
pylint src/ app.py

echo "Checking imports..."
isort --check-only src/ app.py

echo "Checking formatting..."
black --check src/ app.py