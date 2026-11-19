#!/usr/bin/env bash
# One-time setup: install every service's dependencies and create .env.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

for dir in youtube x bot/telegram bot/discord meta_service/facebook meta_service/instagram gateway; do
  echo "→ installing $dir"
  (cd "$dir" && uv sync --quiet)
done

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env  # it will hold secrets
  echo "→ created .env from .env.example"
else
  echo "→ .env already exists; left unchanged"
fi

cat <<'MSG'

Setup done. Next:
  1. Fill in the credentials for the platforms you use in .env
     (each section of .env says where to get them).
  2. ./run.sh
MSG
