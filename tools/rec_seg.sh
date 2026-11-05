#!/bin/bash
# 录一段：grim 连续抓 JPEG，按实测帧率编码为 mp4
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export QT_QPA_PLATFORM=wayland

SCRIPT="$1"; OUT="$2"; INTERVAL="${3:-0.4}"; MAXWAIT="${4:-420}"
FRAMES=/tmp/frames_rec
rm -rf "$FRAMES"; mkdir -p "$FRAMES"
rm -f /tmp/rec_stop
pkill -x qterminal 2>/dev/null; sleep 1
: > /tmp/cie_phases.log

(
  i=0
  while [ ! -f /tmp/rec_stop ]; do
    i=$((i + 1))
    grim -t ppm "$FRAMES/f_$(printf %05d "$i").ppm" 2>/dev/null || break
    sleep "$INTERVAL"
  done
  echo "$i" > /tmp/rec_count
) &
CAP=$!

START=$(date +%s%3N)
echo "CAP_START $START" >> /tmp/cie_phases.log
setsid qterminal -p cie-demo -e "bash $SCRIPT" >/tmp/qt.log 2>&1 &

for _ in $(seq 1 "$MAXWAIT"); do
  pgrep -x qterminal >/dev/null || break
  sleep 1
done
sleep 1

END=$(date +%s%3N)
touch /tmp/rec_stop
wait $CAP 2>/dev/null

N=$(cat /tmp/rec_count 2>/dev/null || echo 0)
MS=$((END - START))
[ "$N" -lt 5 ] && { echo "帧数不足: $N"; exit 1; }
FPS=$(awk -v n="$N" -v ms="$MS" 'BEGIN{printf "%.4f", n/(ms/1000)}')
cp /tmp/cie_phases.log "/tmp/phases_$(basename "$OUT" .mp4).log"

ffmpeg -y -loglevel error -framerate "$FPS" -i "$FRAMES/f_%05d.ppm" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$OUT" || exit 1

rm -rf "$FRAMES"
echo "帧=$N 时长=$((MS / 1000))s 帧率=$FPS -> $OUT $(du -h "$OUT" | cut -f1)"
