#!/bin/zsh
cd "$(dirname "$0")"
python3 wordgroup_config_detection.py service-open --port 9990 --ui-users-file "" --open-browser
