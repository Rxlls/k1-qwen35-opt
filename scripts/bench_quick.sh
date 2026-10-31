#!/usr/bin/env bash
# 快速基准（非正式基线，用于量级判断与链路验证）
# 用法: bash ~/cie/tools/bench_quick.sh <模型.gguf|模型名> [标签]
#   模型只给文件名时自动到 $CIE/models/ 下找
# 固定口径: -t 4(IME约束) -fa 1 -mmp 0(mmap关) -r 3(3次重复)
# 结果存: $CIE/results/bench_<标签>_<时间>.txt
# 可用 CIE_HOME 改根目录，默认 ~/cie
set -u
CIE=${CIE_HOME:-$HOME/cie}
MODELS="$CIE/models"
RESULTS="$CIE/results"
mkdir -p "$RESULTS"

[ $# -ge 1 ] || { echo "用法: bash ~/cie/tools/bench_quick.sh <模型.gguf|模型名> [标签]"; exit 1; }
MODEL=$1
if [ ! -f "$MODEL" ] && [ -f "$MODELS/$(basename "$MODEL")" ]; then
  MODEL="$MODELS/$(basename "$MODEL")"
fi
[ -f "$MODEL" ] || { echo "找不到模型: $1  (已尝试 $MODELS/)"; exit 1; }
TAG=${2:-$(basename "$MODEL" .gguf)}
OUT="$RESULTS/bench_${TAG}_$(date +%F_%H%M%S).txt"

echo "=== bench_quick: $MODEL (tag=$TAG) @ $(date '+%F %T') ==="
echo "口径: -t 4 -fa 1 -mmp 0 -r 3 | pp=64,512 | tg=128"
llama-bench -m "$MODEL" -t 4 -p 64,512 -n 128 -fa 1 -mmp 0 -r 3 2>&1 | tee "$OUT"
echo
echo "已保存: $OUT"
