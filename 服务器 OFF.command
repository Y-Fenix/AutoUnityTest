#!/bin/zsh
cd "$(dirname "$0")"

PORT=9990
PID_FILE=".autounitytest_server.pid"

echo "正在停止 AutoUnityTest 本地服务器..."
python3 wordgroup_config_detection.py service-stop >/dev/null 2>&1

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  if [ -n "$pid" ]; then
    kill "$pid" >/dev/null 2>&1
  fi
  rm -f "$PID_FILE"
fi

for pid in $(lsof -tiTCP:${PORT} -sTCP:LISTEN); do
  kill "$pid" >/dev/null 2>&1
done

echo ""
echo "服务器已停止。"

echo ""
read -r "?按回车关闭..."
