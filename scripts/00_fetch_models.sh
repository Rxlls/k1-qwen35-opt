#!/usr/bin/env bash
# ============================================================
# 00_fetch_models.sh — 下载 Qwen3.5 官方原始权重
#
# 运行环境：x86_64 主机（K1 内存不足以容纳 4B 的 8.4GB 权重转换过程）
# 依赖：pip install modelscope
#
# 用法:
#   bash 00_fetch_models.sh              # 下载 2B 与 4B
#   bash 00_fetch_models.sh 2b           # 仅 2B（约 4.6GB）
#   bash 00_fetch_models.sh 4b           # 仅 4B（约 8.4GB）
#
# 输出: $CIE_HOME/models/qwen3.5-2b|4b/  （HF 格式权重）
# ============================================================

set -u
CIE="${CIE_HOME:-$PWD}"
DEST="$CIE/models"
WHICH="${1:-all}"

command -v modelscope >/dev/null || {
  echo "缺少 modelscope，请先: pip install modelscope"; exit 1;
}

mkdir -p "$DEST"

fetch() {
  local repo="$1" dir="$2" note="$3"
  echo
  echo "== 下载 $repo -> $DEST/$dir （$note）=="
  modelscope download --model "$repo" --local_dir "$DEST/$dir" || return 1
  echo "-- 完成，清单："
  ls -lh "$DEST/$dir" | head -12
}

case "$WHICH" in
  2b)  fetch Qwen/Qwen3.5-2B qwen3.5-2b "约 4.6GB" ;;
  4b)  fetch Qwen/Qwen3.5-4B qwen3.5-4b "约 8.4GB" ;;
  all) fetch Qwen/Qwen3.5-2B qwen3.5-2b "约 4.6GB"
       fetch Qwen/Qwen3.5-4B qwen3.5-4b "约 8.4GB" ;;
  *)   echo "用法: bash $0 [2b|4b|all]"; exit 2 ;;
esac

echo
echo "== 下一步 =="
echo "  记录原始权重 sha256（可复现性证据）:"
echo "    sha256sum $DEST/qwen3.5-2b/*.safetensors > $CIE/docs/hash_2b_raw.txt"
echo "  然后执行: bash 01_convert.sh"
echo
echo "注意: 官方仓库名为 Qwen/Qwen3.5-2B 与 Qwen/Qwen3.5-4B，"
echo "      不存在 -Instruct 后缀（赛题所称 Instruct 指后训练权重本身）。"
