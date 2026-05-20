#!/bin/zsh
cd "$(dirname "$0")"

echo "AutoUnityTest 服务器状态"
echo "----------------------------------------"

if lsof -tiTCP:9990 -sTCP:LISTEN >/dev/null 2>&1; then
  pid="$(lsof -tiTCP:9990 -sTCP:LISTEN | head -n 1)"
  echo "本地服务器：运行中"
  echo "本机访问：http://127.0.0.1:9990/"
  echo "PID：$pid"
else
  echo "本地服务器：未运行"
fi

if [ -f ".autounitytest_lan_server.pid" ]; then
  lan_pid="$(cat .autounitytest_lan_server.pid)"
  if ps -p "$lan_pid" >/dev/null 2>&1; then
    echo ""
    echo "局域网服务器：运行中"
    echo "PID：$lan_pid"
  fi
fi

echo ""
python3 wordgroup_config_detection.py service-status

echo ""
read -r "?按回车关闭..."
