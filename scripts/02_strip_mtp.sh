#!/usr/bin/env bash
# ============================================================
# 02_strip_mtp.sh — 剥离 MTP 层并修正元数据
#
# 为什么必须做这一步:
#   Qwen3.5 权重的第 N+1 层是 MTP（多 token 预测）模块，含 nextn.* 张量。
#   v0.2.3 转换器会把它保留为额外一层并计入 block_count，
#   而 0.1.1 运行时（apt 版）不认识 MTP，加载时报:
#     missing tensor 'blk.24.ssm_conv1d.weight'
#     done_getting_tensors: wrong number of tensors; expected 335, got 320
#   需同时修正三个元数据键:
#     block_count            25 -> 24   (4B: 33 -> 32)
#     nextn_predict_layers   1  -> 0
#     attention.recurrent_layers  去掉末尾那一个 False
#
# 运行环境：x86 或 K1 均可（只做张量拷贝，需 pip install gguf）
#
# 用法: bash 02_strip_mtp.sh <输入-f16.gguf> [输出-nomtp.gguf]
# ============================================================

set -u
CIE="${CIE_HOME:-$PWD}"
PY="${PYTHON:-python3}"

IN="${1:-}"
if [ -z "$IN" ]; then
  # 缺省按文件名推断
  if [ -f "$CIE/gguf/Qwen3.5-2B-f16.gguf" ] && [ ! -f "$CIE/gguf/Qwen3.5-2B-f16-nomtp.gguf" ]; then
    IN="$CIE/gguf/Qwen3.5-2B-f16.gguf"
  elif [ -f "$CIE/gguf/Qwen3.5-4B-f16.gguf" ] && [ ! -f "$CIE/gguf/Qwen3.5-4B-f16-nomtp.gguf" ]; then
    IN="$CIE/gguf/Qwen3.5-4B-f16.gguf"
  else
    echo "用法: bash $0 <输入-f16.gguf> [输出.gguf]"; exit 2
  fi
fi
OUT="${2:-${IN%.gguf}-nomtp.gguf}"

[ -f "$IN" ] || { echo "输入不存在: $IN"; exit 1; }
[ -f "$CIE/tools/strip_mtp.py" ] || { echo "缺少 $CIE/tools/strip_mtp.py"; exit 1; }

"$PY" -c "import gguf" 2>/dev/null || {
  echo "缺少 gguf 库，请执行:"
  echo "  python -m pip install gguf -i https://pypi.tuna.tsinghua.edu.cn/simple"
  echo "  （K1 上系统 Python 需加 --break-system-packages）"
  exit 1
}

echo "== 剥离 MTP =="
echo "  输入: $IN"
echo "  输出: $OUT"
"$PY" "$CIE/tools/strip_mtp.py" "$IN" "$OUT" 2>&1 | tail -14

echo
if [ ! -f "$OUT" ]; then
  echo "剥离失败，未生成输出"; exit 1
fi

echo "== 校验（必须 block_count 正确、nextn=0、无 MTP 残留）=="
"$PY" - "$OUT" <<'PY'
import sys, gguf
r = gguf.GGUFReader(sys.argv[1])
def g(k):
    f = r.get_field(k)
    return f.contents() if f else None
bc = g("qwen35.block_count")
nk = g("qwen35.nextn_predict_layers")
rl = g("qwen35.attention.recurrent_layers")
resid = [t.name for t in r.tensors if "nextn" in t.name or t.name.startswith("blk.%d." % (bc or 99))]
print("  block_count   :", bc)
print("  nextn         :", nk)
print("  recurrent_len :", len(rl) if rl is not None else "?")
print("  tensors       :", len(r.tensors))
print("  残留 MTP 张量 :", len(resid))
ok = (nk == 0) and (len(resid) == 0) and (rl is None or len(rl) == bc)
print("  结果          :", "OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
PY

echo
echo "== 下一步 =="
echo "  bash 03_quantize.sh $OUT Q4_0"
