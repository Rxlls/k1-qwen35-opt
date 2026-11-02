#!/usr/bin/env bash
# k1test.sh — 测试 qterminal 渲染后端，并安全清理
# 所有进程按 PID 精确定位，绝不使用会在自身命令行中出现的模式串
set -u

export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0

QNAME="qterminal"          # 精确进程名，用于 pkill -x
QARGS="--workdir /home/a/cie"

kill_my_terminals() {
  # 只杀 qterminal 这个精确可执行名，不碰别的
  pkill -x "$QNAME" 2>/dev/null
  sleep 2
}

kill_my_terminals
echo "--- after cleanup ---"
pgrep -a -x qterminal || echo "none running"

run_case() {
  local tag="$1"; shift
  local envs="$*"
  mkdir -p "/tmp/kt-$tag"
  setsid env $envs \
    qterminal --workdir /home/a/cie \
    -e "bash -c 'echo \"RENDER-$tag\"; uname -srm; sleep 240'" \
    >/dev/null 2>&1 </dev/null &
  sleep 8
  wlrctl toplevel activate qterminal >/dev/null 2>&1
  sleep 2
  grim "/tmp/kt-$tag/shot.png"
  python3 - "$tag" <<'PY'
import sys
from PIL import Image
import numpy as np
tag = sys.argv[1]
a = np.array(Image.open(f"/tmp/kt-{tag}/shot.png").convert("L"))
print(f"[{tag}] mean={a.mean():.1f} max={a.max()} bright>150 frac={(a>150).mean():.4f}")
PY
}

BASE="XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_SESSION_TYPE=wayland HOME=/home/a PATH=/usr/bin:/bin USER=a LANG=zh_CN.UTF-8 TERM=xterm-256color"

echo "=== case A: wayland, default GL ==="
run_case gl "$BASE QT_QPA_PLATFORM=wayland"

kill_my_terminals
echo "=== case B: wayland, software rasterizer ==="
run_case sw "$BASE QT_QPA_PLATFORM=wayland QT_QUICK_BACKEND=software QT_OPENGL=software LIBGL_ALWAYS_SOFTWARE=1"

kill_my_terminals
echo "=== case C: xcb via Xwayland ==="
run_case xcb "$BASE QT_QPA_PLATFORM=xcb"

echo "=== done; leaving last window open ==="
pgrep -a -x qterminal