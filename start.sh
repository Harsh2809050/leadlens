#!/usr/bin/env bash
# LeadLens launcher (macOS / Linux)
cd "$(dirname "$0")/backend"
python3 -m pip install -q -r requirements.txt
echo "Starting LeadLens at http://127.0.0.1:8787 ..."
python3 -m uvicorn main:app --host 127.0.0.1 --port 8787
