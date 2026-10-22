#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv-overlay/bin/python ]]; then
  python3 -m venv .venv-overlay
  .venv-overlay/bin/python -m pip install -r overlay/requirements.txt
fi
if ! .venv-overlay/bin/python -c 'import PySide6, cv2, numpy' >/dev/null 2>&1; then
  .venv-overlay/bin/python -m pip install -r overlay/requirements.txt
fi
exec .venv-overlay/bin/python -m overlay.app "$@"
