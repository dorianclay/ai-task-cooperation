#!/bin/bash
cd "$(dirname "$0")"
echo "Models available in Ollama:"
ollama list 2>/dev/null || { echo "ollama not found on PATH. Is Ollama installed and running?"; read -p "Press Enter to close."; exit 1; }
echo
# Pick the first qwen model tag, else fall back to the first model listed
MODEL=$(ollama list | awk 'NR>1 && tolower($1) ~ /qwen/ {print $1; exit}')
[ -z "$MODEL" ] && MODEL=$(ollama list | awk 'NR>1 {print $1; exit}')
echo "Using model: $MODEL"
echo
python3 smoke_test.py --model "$MODEL" --episodes 20 2>&1 | tee smoke_log.txt
echo
read -p "Done. Press Enter to close."
