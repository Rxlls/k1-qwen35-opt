#!/usr/bin/env bash
# 4B @ 32K 深度：只测 decode（tg64），绕过 pp512 那一遍 3 小时的上下文填充
cd "$HOME/cie" || exit 1
OUT=results/bench_4b_32k_tg.txt
: > "$OUT"
echo "===== 4B 32K decode 单测：-p 0 -n 64 -d 32768 -r 1 =====" >> "$OUT"
date "+start %F %T" >> "$OUT"
timeout 28800 llama-bench -m models/Qwen3.5-4B-Q4_0-self.gguf \
  -t 4 -p 0 -n 64 -d 32768 -fa 1 -mmp 0 -r 1 >> "$OUT" 2>&1
rc=$?
echo "rc=$rc" >> "$OUT"
date "+end %F %T" >> "$OUT"
touch /tmp/tg32k.done
