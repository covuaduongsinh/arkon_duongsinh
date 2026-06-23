#!/usr/bin/env bash
# Runs ON the production server (logged in as the SSH_USER, e.g. root),
# streamed in by .github/workflows/deploy.yml. Keep it idempotent.
set -euo pipefail

APP_DIR=/home/arkon/arkon-main

echo "==> Pulling latest code"
cd "$APP_DIR"
sudo -u arkon git pull

echo "==> Rebuilding & restarting containers"
docker compose --env-file .env.docker up -d --build

echo "==> Pruning dangling images"
docker image prune -f

echo "==> Deploy complete"
