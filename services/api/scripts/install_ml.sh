#!/usr/bin/env sh
# Install the optional DDColor ML stack into a Python environment.
#
#   pnpm setup:ml                       # into services/api/.venv (local dev)
#   PYTHON=python sh scripts/install_ml.sh   # into the current interpreter (Railway)
#
# Two steps, because DDColor cannot be installed with its own dependencies (see
# requirements-ml.txt): first the pinned closure, then DDColor --no-deps.
# On Linux the CPU-only torch wheels are used unless TORCH_INDEX_URL says
# otherwise (set it to a CUDA index, e.g. https://download.pytorch.org/whl/cu124,
# on a GPU host). macOS wheels already include Apple MPS support.
set -eu

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
DDCOLOR_REF="2adb63f2656ac41cbdf7b894cddd94121a3faf13"

if [ "$(uname -s)" = "Linux" ]; then
  TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"
fi

if [ -n "${TORCH_INDEX_URL:-}" ]; then
  "$PYTHON" -m pip install --no-cache-dir --extra-index-url "$TORCH_INDEX_URL" -r requirements-ml.txt
else
  "$PYTHON" -m pip install --no-cache-dir -r requirements-ml.txt
fi

"$PYTHON" -m pip install --no-cache-dir --no-deps --no-build-isolation \
  "basicsr @ git+https://github.com/piddnad/DDColor.git@${DDCOLOR_REF}"

"$PYTHON" -c "import ddcolor, torch; print('DDColor ready; torch', torch.__version__)"
