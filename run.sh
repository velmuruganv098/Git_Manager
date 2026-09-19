#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo ""
echo "Starting Local GitHub Manager..."
echo "Open http://127.0.0.1:5757 in your browser."
echo "Press CTRL+C to stop it."
echo ""

python app.py
