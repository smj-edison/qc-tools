#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SOCKET_PATH="$XDG_RUNTIME_DIR/jupyter.sock"
# Clean up any stale socket from previous runs.
rm -f "$SOCKET_PATH"

REMOTE_USER="$(whoami)"
REMOTE_HOST="$(hostname -f 2>/dev/null || hostname)"

cat <<EOF
========================================================================
 Jupyter Socket Server Starting
========================================================================
 Socket path : $SOCKET_PATH

 Run this command on your LOCAL machine in a separate terminal:

   ssh -N -L 8000:${SOCKET_PATH} ${REMOTE_USER}@${REMOTE_HOST}

 Then open your browser to:

   http://localhost:8000

 (Use the token printed below to authenticate)
========================================================================

EOF

source "$SCRIPT_DIR/.venv/bin/activate"

OPENSSL_CONF=/dev/null jupyter notebook --no-browser --sock="$SOCKET_PATH" --sock-mode=0600