#!/bin/bash
# Benchmark Suite Orchestrator

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SUITE="${1:-framework}"
if [[ $# -gt 0 ]]; then
  shift
fi

SUITE_DIR="$SCRIPT_DIR/suites/$SUITE"
SUITE_RUN="$SUITE_DIR/run.sh"

if [[ ! -d "$SUITE_DIR" ]]; then
  echo "Error: unknown benchmark suite '$SUITE'"
  echo ""
  echo "Available suites:"
  ls -1 "$SCRIPT_DIR/suites" | sed 's/^/  - /'
  echo ""
  echo "Usage:"
  echo "  ./run.sh [suite] [suite-options]"
  echo ""
  echo "Examples:"
  echo "  ./run.sh"
  echo "  ./run.sh framework --size-only"
  exit 1
fi

if [[ ! -x "$SUITE_RUN" ]]; then
  echo "Error: suite runner not found or not executable: $SUITE_RUN"
  exit 1
fi

exec "$SUITE_RUN" "$@"
