#!/bin/bash
# 录对照演示：开终端跑 demo_ab.sh，grim 连拍，按真实帧率编码。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export QT_QPA_PLATFORM=wayland

OUT=${1:-/tmp/k1_ab.mp4}
FRAMES=/tmp/cie_frames
rm -rf "$FRAMES"; mkdir -p "$FRAMES"; rm -f /tmp/cie_stop
pkill -x qterminal 2>/dev/null; sleep 1

(
  i=0
  while [ ! -f /tmp/cie_stop ]; do
    i=$((i + 1))
    grim -t ppm "$FRAMES/f_$(printf '%05d' "$i").ppm" 2>/dev/null || break
  done
  echo "$i" > /tmp/cie_frame_count
) &
CAP_PID=$!

sleep 1
: > /tmp/cie_phases.log
START=$(date +%s%3N)
echo "CAP_START $START" >> /tmp/cie_phases.log

setsid qterminal -p cie-demo -e "bash /home/a/cie/tools/demo_ab.sh" >/tmp/cie_qt.log 2>&1 &
sleep 2
wlrctl toplevel maximize >/dev/null 2>&1 || true

for _ in $(seq 1 300); do
  pgrep -x qterminal >/dev/null || break
  sleep 1
done
sleep 2

END=$(date +%s%3N)
touch /tmp/cie_stop
wait $CAP_PID 2>/dev/null

N=$(cat /tmp/cie_frame_count 2>/dev/null || echo 0)
MS=$(( END - START ))
[ "$N" -lt 10 ] && { echo "帧数不足：$N"; exit 1; }

FPS=$(awk -v n="$N" -v ms="$MS" 'BEGIN{printf "%.3f", n/(ms/1000)}')
echo "帧数=$N  时长=${MS}ms  实测帧率=$FPS"
cp /tmp/cie_phases.log /tmp/cie_phases.saved.log

ffmpeg -y -loglevel error -framerate "$FPS" -i "$FRAMES/f_%05d.ppm" \
  -vf "scale=1280:-2" -c:v libx264 -preset ultrafast -crf 24 -pix_fmt yuv420p \
  -movflags +faststart "$OUT" || exit 1
ls -l "$OUT" | awk '{print "输出 " $9 "  " $5 " 字节"}'
rm -rf "$FRAMES"
