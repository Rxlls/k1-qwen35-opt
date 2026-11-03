#!/bin/bash
# 在 K1 桌面上录一段真机演示：开终端跑 demo.sh，同时用 grim 连续抓帧，最后编码成 mp4。
# 用法：bash record_demo.sh [输出名]
set -u

export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export QT_QPA_PLATFORM=wayland

OUT=${1:-/tmp/k1_demo.mp4}
FRAMES=/tmp/cie_frames
rm -rf "$FRAMES"; mkdir -p "$FRAMES"
rm -f /tmp/cie_stop

pkill -x qterminal 2>/dev/null
sleep 1

# ---- 抓帧循环（后台）----
(
  i=0
  while [ ! -f /tmp/cie_stop ]; do
    i=$((i + 1))
    grim -t ppm "$FRAMES/f_$(printf '%05d' "$i").ppm" 2>/dev/null || break
  done
  echo "$i" > /tmp/cie_frame_count
) &
CAP_PID=$!

sleep 1  # 先录一小段桌面
START=$(date +%s%N)

# ---- 开终端跑演示 ----
setsid qterminal -p cie-demo -e "bash /home/a/cie/demo.sh" >/tmp/cie_qt.log 2>&1 &
sleep 2
wlrctl toplevel maximize >/dev/null 2>&1 || true   # labwc 下把窗口铺满，避免桌面边框入镜

# demo.sh 约 60 s 结束（生成 + 尾部停留）
for _ in $(seq 1 90); do
  pgrep -x qterminal >/dev/null || break
  sleep 1
done
sleep 2

END=$(date +%s%N)
touch /tmp/cie_stop
wait $CAP_PID 2>/dev/null

N=$(cat /tmp/cie_frame_count 2>/dev/null || echo 0)
MS=$(( (END - START) / 1000000 ))
if [ "$N" -lt 10 ]; then echo "帧数不足：$N"; exit 1; fi

# 真实帧率 = 帧数 / 秒数（抓帧间隔近似恒定，用均值可避免速度失真）
FPS=$(awk -v n="$N" -v ms="$MS" 'BEGIN{printf "%.3f", n/(ms/1000)}')
echo "帧数=$N  时长=${MS}ms  实测帧率=$FPS"

ffmpeg -y -loglevel error -framerate "$FPS" -i "$FRAMES/f_%05d.ppm" \
  -vf "scale=1280:-2" -c:v libx264 -preset ultrafast -crf 24 -pix_fmt yuv420p \
  -movflags +faststart "$OUT" || exit 1

ls -l "$OUT" | awk '{print "输出 " $9 "  " $5 " 字节"}'
ffprobe -v error -show_entries format=duration -of default=nw=1 "$OUT"
rm -rf "$FRAMES"
