#!/usr/bin/env bash
# 快速基准（非正式基线，用于量级判断与链路验证）
# 用法: bash bench_quick.sh <模型.gguf> [标签]
# 固定口径: -t 4(IME约束) -fa 1 -mmp 0(mmap关) -r 3(3次重复取中位)
# 结果存 results/bench_<标签>_<时间>.txt
set -u
MODEL=${1:?用法: bash bench_quick.sh <模型.gguf> [标签]}
[ -f "$MODEL" ] || { echo "找不到模型: $MODEL"; exit 1; }
TAG=${2:-$(basename "$MODEL" .gguf)}
mkdir -p results
OUT="results/bench_${TAG}_$(date +%F_%H%M%S).txt"

echo "=== bench_quick: $MODEL (tag=$TAG) @ $(date '+%F %T') ==="
echo "口径: -t 4 -fa 1 -mmp 0 -r 3 | pp=64,512 | tg=128"
llama-bench -m "$MODEL" -t 4 -p 64,512 -n 128 -fa 1 -mmp 0 -r 3 2>&1 | tee "$OUT"
echo
echo "已保存: $OUT"
