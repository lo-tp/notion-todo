#!/usr/bin/env bash
set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$SKILL_DIR/.venv/bin/python"

# Verify .venv
if [ ! -f "$VENV_PYTHON" ]; then
  echo "Error: Virtual environment missing at $VENV_PYTHON" >&2
  exit 1
fi

# Load .env
if [ -f "$(pwd)/.env" ]; then
  set -o allexport; source "$(pwd)/.env"; set +o allexport
elif [ -f "$HOME/.env" ]; then
  set -o allexport; source "$HOME/.env"; set +o allexport
fi

# Extract target script name from first argument
SCRIPT_NAME="$1"
shift 1  # Remove script name from arguments list so remaining flags ($@) pass to Python

TARGET_SCRIPT="$SKILL_DIR/scripts/$SCRIPT_NAME.py"

if [ ! -f "$TARGET_SCRIPT" ]; then
  echo "Error: Helper script '$SCRIPT_NAME.py' not found in $SKILL_DIR/scripts/" >&2
  exit 1
fi

# Execute target script with remaining arguments
exec "$VENV_PYTHON" "$TARGET_SCRIPT" "$@"
