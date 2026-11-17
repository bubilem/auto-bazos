#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    echo "Vytvářím virtuální prostředí..."
    python3 -m venv .venv || exit 1
    .venv/bin/python -m pip install --quiet -r requirements.txt || exit 1
fi

exec .venv/bin/python server.py --open
