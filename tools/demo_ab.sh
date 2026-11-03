#!/bin/bash
# 对照演示：同一段 534-token 提示词，先官方 Q4_0、再自产 Q4_0，各跑一次。
# 用法：bash demo_ab.sh [2b|4b]      默认 2b
# 每个阶段写时间戳到 /tmp/cie_phases.log，供后期按真实时间剪辑。
cd "$HOME/cie" || exit 1
export TERM=xterm-256color

SIZE="${1:-2b}"
case "$SIZE" in
  2b) M=2B; A=models/Qwen3.5-2B-Q4_0.gguf; B=models/Qwen3.5-2B-Q4_0-self.gguf; MIX="55 个"; LAYERS="18 个 GDN 层" ;;
  4b) M=4B; A=models/Qwen3.5-4B-Q4_0.gguf; B=models/Qwen3.5-4B-Q4_0-self.gguf; MIX="73 个"; LAYERS="24 个 GDN 层" ;;
  *) echo "用法：bash $0 [2b|4b]"; exit 2 ;;
esac

PH=/tmp/cie_phases.log   # 由 record_ab.sh 清空，本脚本只追加
mark() { echo "$1 $(date +%s%3N)" >> "$PH"; }

clear
printf "\n"
printf "  \033[1;36m对照实验 · Qwen3.5-%s\033[0m   同一段 534 token 提示词，同一运行时，只换量化文件\n" "$M"
printf "               K1 · Bianbu 2.3.5 / riscv64 / 4 核 1.6 GHz\n"
printf "\n  ──────────────────────────────────────────────────────────────\n\n"
printf "  A：Qwen3.5-%s-Q4_0.gguf        官方 GGUF（名 Q4_0，实混 %s 非白名单张量，%s）\n" "$M" "$MIX" "$LAYERS"
printf "  B：Qwen3.5-%s-Q4_0-self.gguf   自产 GGUF（纯 Q4_0，非白名单仅 1 个）\n" "$M" "$M"
printf "\n  提示词：从 /tmp/prompt512.txt 读入（534 token），-n 8 只生成 8 token\n"
printf "  上下文 -c 2048（够放提示词即可，避免按模型默认长上下文分配 KV）\n\n"
sleep 4
mark BANNER_END

# ---------------- A：官方 ----------------
printf "  \033[1m── A · 官方 Q4_0 ────────────────────────────────────────────\033[0m\n\n"
mark A_START
llama-cli -m "$A" \
  -f /tmp/prompt512.txt -n 8 -t 4 -fa 1 --no-mmap -st -c 2048 < /dev/null \
  2> >(grep -v --line-buffered "CPU_RISCV64_SPACEMIT" >&2)
mark A_DONE
printf "\n"
sleep 3

# ---------------- B：自产 ----------------
printf "  \033[1m── B · 自产 Q4_0 ────────────────────────────────────────────\033[0m\n\n"
mark B_START
llama-cli -m "$B" \
  -f /tmp/prompt512.txt -n 8 -t 4 -fa 1 --no-mmap -st -c 2048 < /dev/null \
  2> >(grep -v --line-buffered "CPU_RISCV64_SPACEMIT" >&2)
mark B_DONE

printf "\n  —— 以上为本机实录；视频中的计时等待段为 4 倍快进 ——\n"
sleep 8
mark END
