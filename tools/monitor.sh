#!/usr/bin/env bash
# 推理过程资源监测（所有性能测试必须与它同时段运行）
# 用法: bash ~/cie/tools/monitor.sh [CSV路径] [被监测进程PID]
#   例: bash ~/cie/tools/monitor.sh                        # 只记系统级
#       bash ~/cie/tools/monitor.sh "" 1234                # 记RSS
# 默认输出: $CIE/results/monitor_<时间>.csv
# 每秒一行: 时间,cpu0/4频率MHz,最高温度C,可用内存MB,swap占用MB,进程RSS MB
# Ctrl+C 结束。可用 CIE_HOME 改根目录，默认 ~/cie
set -u
CIE=${CIE_HOME:-$HOME/cie}
RESULTS="$CIE/results"
mkdir -p "$RESULTS"
OUT=${1:-$RESULTS/monitor_$(date +%F_%H%M%S).csv}
PID=${2:-}
mkdir -p "$(dirname "$OUT")"
echo "ts,cpu0_mhz,cpu4_mhz,temp_c,mem_avail_mb,swap_mb,rss_mb" > "$OUT"
echo "采样中 -> $OUT  (Ctrl+C结束)"

while true; do
  ts=$(date +%s)
  f0=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || echo 0)
  f4=$(cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq 2>/dev/null || echo 0)
  temp=0
  for t in /sys/class/thermal/thermal_zone*/temp; do
    [ -f "$t" ] || continue
    v=$(cat "$t" 2>/dev/null) || v=0
    [ "$v" -gt "$temp" ] 2>/dev/null && temp=$v
  done
  temp_c=$(awk -v m="$temp" 'BEGIN{printf "%.1f", m/1000}')
  mem_avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  swap_used=$(awk '/SwapTotal/{t=$2}/SwapFree/{f=$2}END{print int((t-f)/1024)}' /proc/meminfo)
  rss=0
  if [ -n "$PID" ]; then
    rss=$(ps -p "$PID" -o rss= 2>/dev/null | tr -d ' ')
    rss=${rss:-0}
  fi
  echo "$ts,$((f0/1000)),$((f4/1000)),$temp_c,$mem_avail,$swap_used,$rss" >> "$OUT"
  sleep 1
done
