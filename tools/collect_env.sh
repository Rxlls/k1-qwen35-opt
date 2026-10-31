#!/usr/bin/env bash
# K1 环境快照采集
# 用法: bash ~/cie/tools/collect_env.sh     （任意目录执行都可以）
# 输出: $CIE/results/env_<时间>.txt
# 可用 CIE_HOME 环境变量改根目录，默认 ~/cie
set -u
CIE=${CIE_HOME:-$HOME/cie}
RESULTS="$CIE/results"
mkdir -p "$RESULTS"
OUT="$RESULTS/env_$(date +%F_%H%M%S).txt"

{
  echo "=== K1 环境快照 @ $(date '+%F %T') ==="
  echo; echo "--- 系统与内核 ---"
  head -5 /etc/os-release
  uname -a
  echo; echo "--- CPU / ISA ---"
  echo "核数: $(nproc)"
  grep -m1 isa /proc/cpuinfo
  for c in 0 4; do
    f=/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq
    [ -f "$f" ] && echo "cpu$c: $(cat "$f") kHz  governor=$(cat "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor" 2>/dev/null)"
  done
  echo; echo "--- 内存 / 存储 ---"
  free -h
  lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
  df -h / 2>/dev/null
  ls /dev/mmcblk* 2>/dev/null || echo "(无mmcblk设备, eMMC不可见)"
  echo; echo "--- TCM 设备节点 ---"
  ls -l /dev/tcm* 2>&1
  lsmod 2>/dev/null | grep -i -E 'tcm|spacemit' || echo "(lsmod 无 tcm/spacemit 模块)"
  echo; echo "--- 温度 ---"
  for tz in /sys/class/thermal/thermal_zone*; do
    [ -f "$tz/temp" ] && echo "$(cat "$tz/type" 2>/dev/null): $(awk '{printf "%.1f C", $1/1000}' "$tz/temp")"
  done
  echo; echo "--- 工具链 ---"
  gcc --version 2>/dev/null | head -1 || echo "gcc 未安装"
  cmake --version 2>/dev/null | head -1 || echo "cmake 未安装"
  python3 --version 2>/dev/null || echo "python3 未安装"
  git --version 2>/dev/null | head -1
  echo; echo "--- llama.cpp / TCM 包 ---"
  dpkg -l 2>/dev/null | grep -Ei 'llama|spacemit-tcm' || echo "(未安装)"
  command -v llama-cli llama-bench llama-server 2>/dev/null
  llama-bench --version 2>/dev/null | head -2
  echo; echo "--- TCM 状态 ---"
  spacemit-tcm-smi -i 2>/dev/null || echo "(spacemit-tcm-smi 不可用)"
} | tee "$OUT"

echo
echo "已保存: $OUT"
