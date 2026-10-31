#!/usr/bin/env bash
# quality_v2.sh — 质量测试（修正版）
#
# 与 v1 的差异：
#   v1: 裸 prompt 直接发 /completion -> 模型进入"续写模式"，输出英文思考过程占满 token
#   v2: 套 Qwen chat 模板 + 预填空 <think></think> 块 -> 强制跳过思考，直接给答案
#
# 用法: bash ~/cie/tools/quality_v2.sh [题目数]
#   默认全部 20 题；传 12 则只跑前 12 题（省时间）

set -u
CIE="${CIE_HOME:-$HOME/cie}"
MODELS="$CIE/models"
RESULTS="$CIE/results"
LIST="$CIE/tools/quality_prompts.txt"
STAMP=$(date +%Y%m%d_%H%M%S)
PORT=8082
LIMIT="${1:-20}"

[ -f "$LIST" ] || { echo "缺少 $LIST"; exit 1; }

for m in Qwen3.5-2B-Q4_0 Qwen3.5-2B-Q4_0-self; do
  MODEL="$MODELS/$m.gguf"
  [ -f "$MODEL" ] || { echo "跳过(缺失): $m"; continue; }
  OUT="$RESULTS/q2_${m}_${STAMP}.txt"

  echo "[$(date +%H:%M:%S)] 启动 server: $m (port $PORT)"
  llama-server -m "$MODEL" -t 4 -c 4096 -fa 1 --no-mmap \
    --host 127.0.0.1 --port $PORT \
    > "$RESULTS/server_q2_${m}_${STAMP}.log" 2>&1 &
  SPID=$!

  for i in $(seq 1 90); do
    curl -s --max-time 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -qi ok && break
    kill -0 $SPID 2>/dev/null || { echo "server 启动失败"; break; }
    sleep 1
  done
  echo "[$(date +%H:%M:%S)] 就绪，开始出题"

  : > "$OUT"
  n=0
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    case "$p" in \#*) continue ;; esac
    n=$((n+1))
    [ "$n" -gt "$LIMIT" ] && break

    printf '===== Q%02d =====\nQ: %s\nA: ' "$n" "$p" >> "$OUT"

    python3 - "$p" "$PORT" >> "$OUT" 2>/dev/null <<'PY'
import sys, json, urllib.request
p, port = sys.argv[1], sys.argv[2]
# 手动套 Qwen chat 模板，并预填空的 think 块 -> 模型直接从答案开始
prompt = ("<|im_start|>user\n" + p + "<|im_end|>\n"
          "<|im_start|>assistant\n<think>\n\n</think>\n\n")
body = json.dumps({
    "prompt": prompt,
    "n_predict": 224,
    "temperature": 0,
    "top_k": 1,
    "cache_prompt": False,
    "stop": ["<|im_end|>", "<|im_start|>"]
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:%s/completion" % port,
    data=body, headers={"Content-Type": "application/json"})
try:
    r = json.load(urllib.request.urlopen(req, timeout=420))
    txt = (r.get("content") or "").strip()
    print(txt if txt else "[EMPTY]")
except Exception as e:
    print("[ERROR] %s" % e)
PY

    printf '\n\n' >> "$OUT"
    echo "[$(date +%H:%M:%S)] Q$(printf %02d $n) 完成"
  done < "$LIST"

  kill $SPID 2>/dev/null; wait $SPID 2>/dev/null
  echo "[$(date +%H:%M:%S)] $m 全部完成 ($n 题) -> $OUT"
done

echo "DONE $(date +%H:%M:%S)"
