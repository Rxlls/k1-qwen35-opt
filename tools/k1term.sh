#!/usr/bin/env bash
# k1term.sh — 与 K1 桌面上那个全屏 qterminal 里的 tmux 会话交互
# 用法:
#   k1term.sh start            新建 tmux 会话并拉起全屏 qterminal 接上它
#   k1term.sh stop             只关掉本脚本启动的那一个 qterminal + 会话
#   k1term.sh runfile <file> [delay]   把文件里每条命令逐条敲进会话
#   k1term.sh clear            清屏
#   k1term.sh shot <out.png>   整屏截图
set -u

export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
S=${S:-demo}
QWIN="qterminal --workdir /home/a/cie"

case "${1:-}" in
  start)
    if [ -f /tmp/k1term.pids ]; then
      xargs -r kill < /tmp/k1term.pids 2>/dev/null
      rm -f /tmp/k1term.pids
      sleep 2
    fi
    tmux kill-session -t "$S" 2>/dev/null
    tmux new-session -d -s "$S" -x 224 -y 56
    setsid env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 \
      XDG_SESSION_TYPE=wayland QT_QPA_PLATFORM=wayland HOME=/home/a PATH=/usr/bin:/bin \
      USER=a SHELL=/bin/bash LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 TERM=screen-256color \
      qterminal --workdir /home/a/cie -e "tmux attach -t $S" >/dev/null 2>&1 </dev/null &
    sleep 9
    pgrep -f "$QWIN" > /tmp/k1term.pids
    tmux list-windows -t "$S"
    wlrctl toplevel list
    ;;
  stop)
    if [ -f /tmp/k1term.pids ]; then
      xargs -r kill < /tmp/k1term.pids 2>/dev/null
      rm -f /tmp/k1term.pids
    fi
    tmux kill-session -t "$S" 2>/dev/null
    ;;
  clear)
    tmux send-keys -t "$S" "clear" Enter
    sleep 1
    ;;
  runfile)
    f=$2
    d=${3:-2}
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      tmux send-keys -t "$S" "$line" Enter
      sleep "$d"
    done < "$f"
    ;;
  shot)
    grim "$2"
    ;;
  *)
    echo "usage: $0 {start|stop|clear|runfile|shot}" >&2
    exit 2
    ;;
esac