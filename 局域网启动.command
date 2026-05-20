#!/bin/zsh
cd "$(dirname "$0")"

read -r "PORT?共享端口（默认 8765）: "
PORT=${PORT:-8765}
PID_FILE=".autounitytest_lan_server.pid"
STDOUT_LOG="wordgroup_ui_service.stdout.log"
STDERR_LOG="wordgroup_ui_service.stderr.log"

echo "正在启动 AutoUnityTest 局域网服务器..."
python3 wordgroup_config_detection.py service-stop >/dev/null 2>&1

existing_pid="$(lsof -tiTCP:${PORT} -sTCP:LISTEN | head -n 1)"
if [ -n "$existing_pid" ]; then
  echo "$existing_pid" > "$PID_FILE"
  echo "局域网服务器已在运行，PID：$existing_pid"
else
  /usr/bin/nohup python3 wordgroup_config_detection.py ui --no-open --share --port "$PORT" >> "$STDOUT_LOG" 2>> "$STDERR_LOG" &
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

  if [ "$ready" -ne 1 ]; then
    echo ""
    echo "局域网服务器启动失败。"
    echo "如需排查，请查看：$STDERR_LOG"
    echo ""
    read -r "?按回车关闭..."
    exit 1
  fi
fi

echo ""
echo "局域网服务器已启动。"
echo "本机访问：http://127.0.0.1:${PORT}/"
echo "局域网访问地址："
python3 -c 'import socket,sys; port=sys.argv[1]; ips=[]; name=socket.gethostname(); 
for item in socket.getaddrinfo(name, None):
    ip=item[4][0]
    if "." in ip and not ip.startswith("127.") and ip not in ips:
        ips.append(ip)
for ip in ips:
    print(f"  http://{ip}:{port}/")
' "$PORT"

echo ""
echo "访问账号："
python3 -c 'import json, pathlib
path = pathlib.Path("wordgroup_ui_users.json")
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"users": []}
for item in data.get("users", []):
    print("  {} ({})".format(item.get("username", ""), item.get("role", "readonly")))
    print("    password: {}".format(item.get("password", "")))
'

/usr/bin/open "http://127.0.0.1:${PORT}/"

echo ""
read -r "?按回车关闭..."
