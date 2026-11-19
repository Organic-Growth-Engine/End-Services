#!/usr/bin/env bash
# Start every configured service and the gateway. Usage: ./run.sh [service ...]
cd "$(dirname "$0")" && exec python3 scripts/run_all.py "$@"
