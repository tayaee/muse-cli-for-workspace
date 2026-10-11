#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing muse-cli-w via uv tool ==="

# Check if uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo "Warning: 'uv' is not installed or not in PATH."
    echo "Attempting to install uv automatically..."
    if command -v curl >/dev/null 2>&1; then
        echo "+ curl -LsSf https://astral.sh/uv/install.sh | sh"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
    else
        echo "Error: curl is required to install uv automatically." >&2
        echo "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/" >&2
        exit 1
    fi
fi

# Ensure uv is now available
if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv was installed but is not found in PATH." >&2
    echo "Please reload your shell or add ~/.local/bin to your PATH, then rerun this script." >&2
    exit 1
fi

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

echo "Installing muse-cli-w tool from git..."
echo "+ uv tool install git+https://github.com/tayaee/muse-cli-for-workspace.git --force"
uv tool install git+https://github.com/tayaee/muse-cli-for-workspace.git --force

uv tool update-shell >/dev/null 2>&1 || true

if ! command -v muse-cli >/dev/null 2>&1; then
    echo ""
    echo "Note: 'muse-cli' was not detected in PATH."
    echo "      muse-cli-w requires muse-cli to communicate with Muse AI."
    echo "      Please ensure muse-cli is installed and configured (muse-cli status)."
fi

echo ""
echo "========================================"
echo "  muse-cli-w installation complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  muse-cli-w --help"
echo "  muse-cli-w ls muse:"
echo ""
