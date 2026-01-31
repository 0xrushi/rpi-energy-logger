#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="telemetry-logger.service"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${SRC_DIR}/${SERVICE_NAME}" ]]; then
  echo "error: ${SRC_DIR}/${SERVICE_NAME} not found" >&2
  exit 2
fi

echo "Installing systemd service to /etc/systemd/system/${SERVICE_NAME}"
sudo install -m 0644 "${SRC_DIR}/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"

echo "Reloading systemd + enabling service"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo "Done. Check status with:"
echo "  systemctl status ${SERVICE_NAME}"
