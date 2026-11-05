#!/bin/bash
# 长上下文：展示 32K 的实测原始记录（实跑需 67 分钟，此处为记录回放）
cd "$HOME/cie" || exit 1
PH=/tmp/cie_phases.log
mark() { echo "$1 $(date +%s%3N)" >> "$PH"; }

clear
printf "\n"
printf " \033[1;36m长上下文 · 32K 实测\033[0m\n"
printf " 32K 实跑需 67 分钟（2B）/ 3.2 小时（4B），此处回放原始记录\n"
printf "\n \033[2m────────────────────────────────────────────\033[0m\n\n"
sleep 6
mark BANNER_END

printf " \033[2m$ grep '^| qwen' results/bench_2b_32k.txt results/bench_2b_32k_official.txt\033[0m\n"
grep -ahE "^\| qwen" results/bench_2b_32k_official.txt | sed 's/  */ /g; s/^/ /'
grep -ahE "^\| qwen" results/bench_2b_32k.txt | sed 's/  */ /g; s/^/ /'
printf "\n"
sleep 6

printf " \033[2m$ 五点衰减（2B 自产 pp512）\033[0m\n"
printf "   0      4096    8192    16384   32768\n"
printf "   20.24  14.65   11.76   8.26    5.03   t/s\n"
printf "   100%%    72.4%%   58.1%%   40.8%%   24.9%%   保持率\n"
printf "\n"
sleep 8

printf " \033[2m$ 4B 的 32K（results/bench_4b_32k.txt）\033[0m\n"
grep -ahE "^\| qwen" results/bench_4b_32k.txt | sed 's/  */ /g; s/^/ /'
printf "\n"
sleep 6

printf " 首字延迟：32K 输入 2B 约 67 分钟、4B 约 3.2 小时\n"
printf " 峰值内存：2B 2.25 GiB、4B 4.86 GiB（深 prefill，非加载值）\n"
printf " \033[2m结论：容量够、交互不可行 —— 长上下文应裁剪输入或换 2B\033[0m\n"
sleep 10
mark K_END
