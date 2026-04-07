#!/bin/bash
cd "$(dirname "$0")"
pip install -r requirements.txt 2>/dev/null || true
mkdir -p data
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
