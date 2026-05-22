#!/bin/zsh
cd "$(dirname "$0")"

PORT=9990
URL="http://127.0.0.1:${PORT}/"
PID_FILE=".autounitytest_server.pid"
STDOUT_LOG="wordgroup_ui_service.stdout.log"
STDERR_LOG="wordgroup_ui_service.stderr.log"

echo "正在启动 AutoUnityTest 本地服务器..."

python3 wordgroup_config_detection.py service-stop >/dev/null 2>&1

existing_pid="$(lsof -tiTCP:${PORT} -sTCP:LISTEN | head -n 1)"
if [ -n "$existing_pid" ]; then
  echo "$existing_pid" > "$PID_FILE"
  echo "服务器已在运行，PID：$existing_pid"
  /usr/bin/open "$URL"
  echo ""
  read -r "?按回车关闭..."
  exit 0
fi

/usr/bin/nohup python3 wordgroup_config_detection.py ui --no-open --port "$PORT" --host 127.0.0.1 --ui-users-file= </dev/null >> "$STDOUT_LOG" 2>> "$STDERR_LOG" &!
server_pid=$!
echo "$server_pid" > "$PID_FILE"

ready=0
for i in {1..40}; do
  if lsof -tiTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.25
done

echo ""
if [ "$ready" -eq 1 ]; then
  echo "服务器已启动："
  echo "$URL"
  /usr/bin/open "$URL"
else
  echo "服务器启动失败。"
  echo "如需排查，请查看：$STDERR_LOG"
fi

echo ""
read -r "?按回车关闭..."
