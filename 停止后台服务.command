#!/bin/zsh
cd "$(dirname "$0")"
python3 wordgroup_config_detection.py service-stop
read -r "?按回车关闭..."
