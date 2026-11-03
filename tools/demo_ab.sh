#!/bin/bash
# 对照演示：同一段 534-token 提示词，先官方 Q4_0、再自产 Q4_0，各跑一次。
# 每个阶段写时间戳到 /tmp/cie_phases.log，供后期按真实时间剪辑。
cd "$HOME/cie" || exit 1
export TERM=xterm-256color

PH=/tmp/cie_phases.log   # 由 record_ab.sh 清空，本脚本只追加
mark() { echo "$1 $(date +%s%3N)" >> "$PH"; }

clear
printf "\n"
printf "  \033[1;36m对照实验\033[0m   同一段 534 token 提示词，同一运行时，只换量化文件\n"
printf "               K1 · Bianbu 2.3.5 / riscv64 / 4 核 1.6 GHz\n"
printf "\n  ──────────────────────────────────────────────────────────────\n\n"
printf "  A：Qwen3.5-2B-Q4_0.gguf        官方 GGUF（名 Q4_0，实混 55 个非白名单张量）\n"
printf "  B：Qwen3.5-2B-Q4_0-self.gguf   自产 GGUF（纯 Q4_0，非白名单仅 1 个）\n"
printf "\n  提示词：从 /tmp/prompt512.txt 读入，-n 8 只生成 8 token，重点看预填充速度\n\n"
sleep 3
mark BANNER_END

# ---------------- A：官方 ----------------
printf "  \033[1m── A · 官方 Q4_0 ────────────────────────────────────────────\033[0m\n\n"
mark A_START
llama-cli -m models/Qwen3.5-2B-Q4_0.gguf \
  -f /tmp/prompt512.txt -n 8 -t 4 -fa 1 --no-mmap -st < /dev/null \
  2> >(grep -v --line-buffered "CPU_RISCV64_SPACEMIT" >&2)
mark A_DONE
printf "\n"
sleep 3

# ---------------- B：自产 ----------------
printf "  \033[1m── B · 自产 Q4_0 ────────────────────────────────────────────\033[0m\n\n"
mark B_START
llama-cli -m models/Qwen3.5-2B-Q4_0-self.gguf \
  -f /tmp/prompt512.txt -n 8 -t 4 -fa 1 --no-mmap -st < /dev/null \
  2> >(grep -v --line-buffered "CPU_RISCV64_SPACEMIT" >&2)
mark B_DONE

printf "\n  —— 以上为本机实录；视频中的计时等待段为 4 倍快进 ——\n"
sleep 8
mark END
