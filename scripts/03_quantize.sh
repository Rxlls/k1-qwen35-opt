#!/usr/bin/env bash
# ============================================================
# 03_quantize.sh — f16(nomtp) → 量化 GGUF
#
# 关键前提：必须使用 **v0.2.3 编译出的 llama-quantize**
#   0.1.1（apt 版）遇到 16 列的小张量会直接失败：
#     warning: blk.0.ssm_alpha.weight - ncols 16 not divisible by 32
#     llama_model_quantize: failed to quantize: no tensor type fallback is defined
#   v0.2.3 具备小张量 F16 回退，正是本方案能产出 Q4_0 的原因。
#
# 运行环境：K1（量化是纯 CPU 任务，不需要 IME；也在 x86 上跑）
#
# 用法:
#   bash 03_quantize.sh <输入-f16-nomtp.gguf> [Q4_0|Q4_K_M|Q5_K_M|Q3_K_M] [输出.gguf]
#   bash 03_quantize.sh <输入.gguf> all      # 依次产出 Q4_0 与 Q4_K_M
#
# 提示: 只有 Q4_0 / Q4_K_M / Q4_1 / Q2_K / Q3_K 命中 K1 的 IME 加速白名单；
#       Q5_K_M、Q3_K_M 实测会掉出加速路径（满载温度仅 31~32°C），不建议使用。
# ============================================================

set -u
CIE="${CIE_HOME:-$PWD}"
QNT="${QNT_BIN:-$CIE/src/llama023/bin/llama-quantize}"

IN="${1:-}"
TYPE="${2:-Q4_0}"
OUT="${3:-}"

if [ -z "$IN" ]; then
  echo "用法: bash $0 <输入-f16-nomtp.gguf> [量化类型] [输出.gguf]"; exit 2
fi
[ -f "$IN" ] || { echo "输入不存在: $IN"; exit 1; }

if [ ! -x "$QNT" ]; then
  echo "找不到可执行的 llama-quantize: $QNT"
  echo "请确认已交叉编译 v0.2.3 并解压到 \$CIE/src/llama023，"
  echo "或用 QNT_BIN 环境变量指定路径。"
  echo
  echo "（不要用 apt 的 /usr/bin/llama-quantize：0.1.1 无法处理 16 列小张量）"
  exit 1
fi

echo "量化器: $QNT"
"$QNT" --help 2>&1 | head -2 | sed 's/^/  /'

run_one() {
  local type="$1" out="$2"
  [ -f "$out" ] && { echo "  已存在，跳过: $(basename "$out")"; return 0; }
  echo
  echo "== 量化 $type =="
  local t0=$(date +%s)
  "$QNT" --token-embedding-type q8_0 "$IN" "$out" "$type" 2>&1 | \
    grep -E 'quantizing|model size|unused tensor|error|failed' | tail -8
  local rc=${PIPESTATUS[0]}
  echo "  耗时 $(( $(date +%s) - t0 ))s  rc=$rc"
  [ -f "$out" ] && ls -lh "$out" | awk '{print "  体积: "$5}'
  return $rc
}

base="${IN%.gguf}"
base="${base%-f16-nomtp}"

case "$TYPE" in
  all)
    run_one Q4_0   "${OUT:-$base-Q4_0.gguf}"
    run_one Q4_K_M "${OUT:-$base-Q4KM-q8emb.gguf}"
    ;;
  *)
    target="${OUT:-$base-$TYPE.gguf}"
    run_one "$TYPE" "$target"
    ;;
esac

echo
echo "== 产物校验（必须是全 Q4_0 / 正确的 block_count）=="
for f in ${OUT:-$base-Q4_0.gguf} ${OUT:-$base-Q4KM-q8emb.gguf}; do
  [ -f "$f" ] || continue
  python3 "$CIE/tools/gguf_types.py" "$f" 2>/dev/null | head -6 | sed 's/^/  /' || \
    echo "  （gguf_types.py 不可用，跳过）"
done

echo
echo "== 下一步 =="
echo "  拷贝到 K1 的 \$CIE/models/，然后:"
echo "    bash tools/bench_quick.sh \$(basename 产物.gguf) <tag>"
echo "    sha256sum 产物.gguf   # 记入 docs/技术文档.md §5.3"
