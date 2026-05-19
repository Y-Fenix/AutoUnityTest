#!/bin/zsh
cd "$(dirname "$0")"

read -r "PORT?共享端口（默认 8765）: "
PORT=${PORT:-8765}

python3 wordgroup_config_detection.py service-open --share --port "$PORT" --open-browser
