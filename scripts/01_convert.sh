#!/usr/bin/env bash
# ============================================================
# 01_convert.sh — HF 原始权重 → f16 GGUF
#
# 运行环境：x86_64 主机（4B 转换峰值内存约 10~12GB，K1 必然 OOM）
# 依赖：llama.cpp 源码 + venv 内的 torch/transformers/gguf/sentencepiece
#
# 用法:
#   bash 01_convert.sh 2b
#   bash 01_convert.sh 4b
#   bash 01_convert.sh <HF权重目录> <输出.gguf>
#
# 说明:
#   - 转换脚本取自 spacemit-com/llama.cpp v0.2.3（conversion/ 包结构）
#   - 该版本支持 qwen35 架构（Qwen3_5TextModel）
#   - 输出为 f16，后续需经 02_strip_mtp.sh 再进 03_quantize.sh
# ============================================================

set -u
CIE="${CIE_HOME:-$PWD}"
SRC="$CIE/llama.cpp"
MODELS="$CIE/models"
GGUF="$CIE/gguf"
PY="${PYTHON:-python}"

mkdir -p "$GGUF"

[ -f "$SRC/convert_hf_to_gguf.py" ] || {
  echo "找不到 $SRC/convert_hf_to_gguf.py"
  echo "请先获取源码: wget https://codeload.github.com/spacemit-com/llama.cpp/zip/refs/tags/v0.2.3"
  exit 1
}

case "${1:-}" in
  2b) IN="$MODELS/qwen3.5-2b"; OUT="$GGUF/Qwen3.5-2B-f16.gguf" ;;
  4b) IN="$MODELS/qwen3.5-4b"; OUT="$GGUF/Qwen3.5-4B-f16.gguf" ;;
  *)
     if [ $# -ge 2 ]; then IN="$1"; OUT="$2"; else
       echo "用法: bash $0 [2b|4b] 或 bash $0 <HF目录> <输出.gguf>"; exit 2
     fi ;;
esac

[ -d "$IN" ] || { echo "权重目录不存在: $IN"; exit 1; }

echo "== 转换 =="
echo "  输入: $IN"
echo "  输出: $OUT"
echo "  预计: 2B 约 15 秒 / 4B 约 60 秒（视磁盘而定）"

cd "$SRC" || exit 1
"$PY" convert_hf_to_gguf.py "$IN" --outfile "$OUT" --outtype f16 2>&1 | \
  grep -vE '^Writing:' | tail -20

if [ ! -f "$OUT" ]; then
  echo "转换失败，未生成输出文件"; exit 1
fi

echo
echo "== 产物 =="
ls -lh "$OUT"
echo
echo "== 自动校验（架构 / 层数 / 张量数）=="
"$PY" "$CIE/tools/gguf_types.py" "$OUT" 2>/dev/null | head -12 || \
  echo "  （gguf_types.py 不可用，跳过；可后续手动核对）"
echo
echo "== 下一步 =="
echo "  bash 02_strip_mtp.sh $OUT"
echo
echo "注意: 转换器会把 MTP 层计入 block_count（2B 写 25、4B 写 33），"
echo "      而运行时 0.1.1 不支持 MTP，必须进入下一步剥离。"
