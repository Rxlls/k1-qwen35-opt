#!/bin/bash
# 视频用对照演示：llama-bench 输出干净表格，pp512 / tg64 逐行出现
cd "$HOME/cie" || exit 1
SIZE="${1:-2b}"
case "$SIZE" in
  2b) M=2B; A=models/Qwen3.5-2B-Q4_0.gguf; B=models/Qwen3.5-2B-Q4_0-self.gguf; N="55 个"; L="18 层" ;;
  4b) M=4B; A=models/Qwen3.5-4B-Q4_0.gguf; B=models/Qwen3.5-4B-Q4_0-self.gguf; N="73 个"; L="24 层" ;;
esac
PH=/tmp/cie_phases.log
mark() { echo "$1 $(date +%s%3N)" >> "$PH"; }
run() { llama-bench -m "$1" -p 512 -n 64 -t 4 -fa 1 -mmp 0 -r 1 2>&1 | grep -aE "^\| qwen|^build"; }

clear
printf "\n"
printf " \033[1;36mQwen3.5-%s · 官方 vs 自产\033[0m\n" "$M"
printf " K1 / Bianbu 2.3.5 / 4 核 1.6 GHz / 同一运行时\n"
printf "\n \033[2m────────────────────────────────────────────\033[0m\n\n"
printf " A  官方 GGUF   名 Q4_0，实混 %s 张量（%s GDN）\n" "$N" "$L"
printf " B  自产 GGUF   纯 Q4_0，非白名单仅 1 个\n"
printf "\n 同一段 534 token 提示词，各测一次\n\n"
sleep 6
mark BANNER_END

printf " \033[1m── A · 官方 ──────────────────────────────\033[0m\n"
mark A_START
run "$A"
mark A_DONE
printf "\n"
sleep 10

printf " \033[1m── B · 自产 ──────────────────────────────\033[0m\n"
mark B_START
run "$B"
mark B_DONE
sleep 12
mark END
