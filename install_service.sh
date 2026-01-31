#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="telemetry-logger.service"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVICE_USER="${SUDO_USER:-$(id -un)}"
SERVICE_GROUP="$(id -gn "${SERVICE_USER}")"

if [[ ! -f "${SRC_DIR}/${SERVICE_NAME}" ]]; then
  echo "error: ${SRC_DIR}/${SERVICE_NAME} not found" >&2
  exit 2
fi

TMP_SERVICE=$(mktemp)
trap 'rm -f "${TMP_SERVICE}"' EXIT

sed -e "s/@USER@/${SERVICE_USER}/" -e "s/@GROUP@/${SERVICE_GROUP}/" "${SRC_DIR}/${SERVICE_NAME}" >"${TMP_SERVICE}"

echo "Installing systemd service to /etc/systemd/system/${SERVICE_NAME} (user=${SERVICE_USER} group=${SERVICE_GROUP})"
sudo install -m 0644 "${TMP_SERVICE}" "/etc/systemd/system/${SERVICE_NAME}"

echo "Reloading systemd + enabling service"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo "Done. Check status with:"
echo "  systemctl status ${SERVICE_NAME}"
