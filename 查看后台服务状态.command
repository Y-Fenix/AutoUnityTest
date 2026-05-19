#!/bin/zsh
cd "$(dirname "$0")"
python3 wordgroup_config_detection.py service-status
read -r "?按回车关闭..."
