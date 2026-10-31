#!/usr/bin/env bash
# run_tomorrow.sh — K1 Qwen3.5 推理优化 · 批量执行清单
#
# 用法：
#   bash ~/cie/tools/run_tomorrow.sh            # 默认 all = prep + 4b + kv + server
#   bash ~/cie/tools/run_tomorrow.sh prep       # 用 v0.2.3 量化器生成 4B 自产 Q4_0
#   bash ~/cie/tools/run_tomorrow.sh 4b         # 4B 五版本 bench
#   bash ~/cie/tools/run_tomorrow.sh kv         # KV cache q8_0 对比（2B）
#   bash ~/cie/tools/run_tomorrow.sh server     # TTFT / 多轮（llama-server）
#   bash ~/cie/tools/run_tomorrow.sh quality    # 质量测试集（20 条固定 prompt）
#   bash ~/cie/tools/run_tomorrow.sh ctx        # 长上下文补点（16K / 32K）
#
# 口径约定（与既有基线一致，勿改）：
#   - 运行时：llama.cpp 0.1.1（apt，legacy IME1 后端）
#   - 线程：-t 4   （8 线程会令 decode 崩塌 70%，已实测）
#   - -fa 1 -mmp 0
#   - 4B 全部用 -r 2（含官方 Q4_0 同口径重测），保证表内可比
#
# 设计原则：
#   - 每步前后打印时间与耗时，失败记录 FAIL 但继续（除 prep）
#   - 所有输出进 $RESULTS，文件名带统一时间戳
#   - 涉及删除/覆盖的操作一律不做，已存在即跳过

set -u

CIE="${CIE_HOME:-$HOME/cie}"
MODELS="$CIE/models"
RESULTS="$CIE/results"
BENCH="llama-bench"                              # apt 0.1.1
QNT_NEW="$CIE/src/llama023/bin/llama-quantize"   # 自编译 v0.2.3（有小张量 F16 回退）
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$RESULTS/run_${STAMP}.log"
FAILED=()

mkdir -p "$RESULTS"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
hr()  { printf '%s\n' "------------------------------------------------------------" | tee -a "$LOG"; }

need() {
  if [ ! -f "$1" ]; then
    log "FAIL 缺少文件: $1"
    FAILED+=("missing:$1")
    return 1
  fi
  return 0
}

# bench <label> <model> [额外参数...]
bench() {
  local label="$1" model="$2"; shift 2
  local out="$RESULTS/bench_${label}_${STAMP}.txt"
  need "$model" || return 1
  log "bench ${label}  (model=$(basename "$model"))"
  local t0=$(date +%s)
  "$BENCH" -m "$model" -t 4 -p 64,512 -n 128 -fa 1 -mmp 0 -r 2 "$@" > "$out" 2>&1
  local rc=$?
  local dt=$(( $(date +%s) - t0 ))
  if [ $rc -ne 0 ]; then
    log "  FAIL rc=$rc 耗时${dt}s -> $out"
    FAILED+=("bench:$label")
  else
    grep -E 'pp64|pp512|tg128' "$out" | sed 's/^/  /' | tee -a "$LOG"
    log "  完成 耗时${dt}s"
  fi
  return $rc
}

# ============================================================
stage_prep() {
  hr; log "STAGE prep — 生成 4B 自产 Q4_0（收尾转换量化闭环）"
  local src="$MODELS/Qwen3.5-4B-f16-nomtp.gguf"
  local dst="$MODELS/Qwen3.5-4B-Q4_0-self.gguf"

  need "$src" || return 1
  need "$QNT_NEW" || return 1

  if [ -f "$dst" ]; then
    log "  已存在，跳过量化: $(basename "$dst")"
  else
    local t0=$(date +%s)
    "$QNT_NEW" --token-embedding-type q8_0 "$src" "$dst" Q4_0 \
      > "$RESULTS/quant_4b_q4self_${STAMP}.log" 2>&1
    local rc=$?
    log "  量化耗时 $(( $(date +%s) - t0 ))s rc=$rc"
    if [ $rc -ne 0 ]; then
      log "  FAIL 量化失败，末尾日志："
      tail -8 "$RESULTS/quant_4b_q4self_${STAMP}.log" | sed 's/^/    /' | tee -a "$LOG"
      FAILED+=("quant:4b_q4_0_self")
      return 1
    fi
  fi

  log "  体积: $(ls -lh "$dst" | awk '{print $5}')"
  log "  冒烟（8 token）"
  llama-cli -m "$dst" -p "你好" -n 8 -st --no-mmap 2>&1 \
    | grep -vE '^\s*$' | tail -3 | sed 's/^/    /' | tee -a "$LOG"
}

# ============================================================
stage_4b() {
  hr; log "STAGE 4b — 五个版本 bench（同口径 -r 2）"
  local M="$MODELS"
  bench 4b_off_q4_0  "$M/Qwen3.5-4B-Q4_0.gguf"        # 官方 unsloth 混合精度
  bench 4b_self_q4_0 "$M/Qwen3.5-4B-Q4_0-self.gguf"   # 自产统一 Q4_0
  bench 4b_self_q4km "$M/Qwen3.5-4B-Q4KM-q8emb.gguf"
  bench 4b_self_q5km "$M/Qwen3.5-4B-Q5KM-q8emb.gguf"
  bench 4b_self_q3km "$M/Qwen3.5-4B-Q3KM-q8emb.gguf"
}

# ============================================================
stage_kv() {
  hr; log "STAGE kv — KV cache q8_0 vs f16（2B 自产 Q4_0）"
  local m="$MODELS/Qwen3.5-2B-Q4_0-self.gguf"
  need "$m" || return 1

  # 对照：f16 KV（已有历史数据，这里同批重测保证环境一致）
  local out1="$RESULTS/kv_f16_${STAMP}.txt"
  log "  f16 KV @ d0,4096,8192"
  local t0=$(date +%s)
  "$BENCH" -m "$m" -t 4 -p 512 -n 64 -ctk f16 -ctv f16 -d 0,4096,8192 \
    -fa 1 -mmp 0 -r 1 > "$out1" 2>&1
  log "    耗时 $(( $(date +%s) - t0 ))s"
  grep -E 'pp512|tg64' "$out1" | sed 's/^/    /' | tee -a "$LOG"

  # 实验：q8_0 KV
  local out2="$RESULTS/kv_q8_0_${STAMP}.txt"
  log "  q8_0 KV @ d0,4096,8192"
  t0=$(date +%s)
  "$BENCH" -m "$m" -t 4 -p 512 -n 64 -ctk q8_0 -ctv q8_0 -d 0,4096,8192 \
    -fa 1 -mmp 0 -r 1 > "$out2" 2>&1
  local rc=$?
  log "    耗时 $(( $(date +%s) - t0 ))s rc=$rc"
  if [ $rc -ne 0 ]; then
    log "    FAIL（0.1.1 可能不支持 q8_0 KV），末尾："
    tail -5 "$out2" | sed 's/^/      /' | tee -a "$LOG"
    FAILED+=("kv:q8_0")
  else
    grep -E 'pp512|tg64' "$out2" | sed 's/^/    /' | tee -a "$LOG"
  fi
}

# ============================================================
stage_server() {
  hr; log "STAGE server — TTFT / 多轮（llama-server :8080）"
  local m="$MODELS/Qwen3.5-2B-Q4_0-self.gguf"
  need "$m" || return 1
  command -v curl >/dev/null || { log "  无 curl，跳过"; FAILED+=("server:curl"); return 1; }

  log "  启动 llama-server"
  llama-server -m "$m" -t 4 -c 8192 -fa 1 --no-mmap \
    --host 127.0.0.1 --port 8080 \
    > "$RESULTS/server_${STAMP}.log" 2>&1 &
  local SPID=$!

  # 等待就绪（最多 90s）
  local i=0
  while [ $i -lt 90 ]; do
    if curl -s --max-time 2 http://127.0.0.1:8080/health 2>/dev/null | grep -qi ok; then break; fi
    kill -0 $SPID 2>/dev/null || { log "  server 进程已退出"; break; }
    sleep 1; i=$((i+1))
  done
  if [ $i -ge 90 ]; then
    log "  FAIL 启动超时，末尾日志："
    tail -10 "$RESULTS/server_${STAMP}.log" | sed 's/^/    /' | tee -a "$LOG"
    kill $SPID 2>/dev/null; FAILED+=("server:start"); return 1
  fi
  log "  就绪（${i}s）"

  local out="$RESULTS/ttft_${STAMP}.txt"
  : > "$out"

  # 单轮：短 prompt
  log "  [1] 单轮短 prompt"
  curl -s --max-time 300 -X POST http://127.0.0.1:8080/completion \
    -H 'Content-Type: application/json' \
    -d '{"prompt":"用一句话解释什么是 RISC-V。","n_predict":64,"temperature":0,"cache_prompt":false}' \
    | python3 -c 'import sys,json
d=json.load(sys.stdin); t=d.get("timings",{})
print("    单轮 prompt_n=%s prompt_tps=%.2f gen_n=%s gen_tps=%.2f" % (t.get("prompt_n",0),t.get("prompt_per_second",0),t.get("predicted_n",0),t.get("predicted_per_second",0)))' \
    2>/dev/null | tee -a "$out" | tee -a "$LOG"

  # 单轮：长 prompt（约 1.5K token 上下文，看 TTFT 随长度变化）
  log "  [2] 单轮长 prompt（约 1.5K）"
  local longp
  longp=$(python3 -c 'print("边缘设备上部署大语言模型需要考虑内存带宽、量化精度和算子实现三个方面的权衡。"*60)')
  curl -s --max-time 600 -X POST http://127.0.0.1:8080/completion \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"prompt":sys.argv[1],"n_predict":32,"temperature":0,"cache_prompt":False}))' "$longp")" \
    | python3 -c 'import sys,json
d=json.load(sys.stdin); t=d.get("timings",{})
print("    长prompt prompt_n=%s prompt_tps=%.2f gen_n=%s gen_tps=%.2f" % (t.get("prompt_n",0),t.get("prompt_per_second",0),t.get("predicted_n",0),t.get("predicted_per_second",0)))' \
    2>/dev/null | tee -a "$out" | tee -a "$LOG"

  # 多轮：第二轮带历史，看 KV 复用是否生效（cache_prompt=true）
  log "  [3] 多轮（第2轮命中 cache，观察 prompt_n 是否只剩增量）"
  curl -s --max-time 600 -X POST http://127.0.0.1:8080/completion \
    -H 'Content-Type: application/json' \
    -d '{"prompt":"<|im_start|>user\nRISC-V 是什么？<|im_end|>\n<|im_start|>assistant\nRISC-V 是一个开放指令集架构。<|im_end|>\n<|im_start|>user\n它和 ARM 最大的区别是什么？<|im_end|>\n<|im_start|>assistant\n","n_predict":64,"temperature":0,"cache_prompt":true}' \
    | python3 -c 'import sys,json
d=json.load(sys.stdin); t=d.get("timings",{})
print("    多轮2 prompt_n=%s prompt_tps=%.2f gen_n=%s gen_tps=%.2f" % (t.get("prompt_n",0),t.get("prompt_per_second",0),t.get("predicted_n",0),t.get("predicted_per_second",0)))' \
    2>/dev/null | tee -a "$out" | tee -a "$LOG"

  kill $SPID 2>/dev/null
  wait $SPID 2>/dev/null
  log "  server 已停止，结果 -> $out"
}

# ============================================================
stage_quality() {
  hr; log "STAGE quality — 质量测试集（20 条，greedy，双版本对照）"
  command -v curl >/dev/null || { log "  无 curl，跳过"; return 1; }

  local list="$CIE/tools/quality_prompts.txt"
  if [ ! -f "$list" ]; then
    log "  缺少 $list，跳过"
    FAILED+=("quality:prompts"); return 1
  fi

  for m in "$MODELS/Qwen3.5-2B-Q4_0.gguf" "$MODELS/Qwen3.5-2B-Q4_0-self.gguf"; do
    need "$m" || continue
    local tag; tag=$(basename "$m" .gguf)
    local out="$RESULTS/quality_${tag}_${STAMP}.txt"

    log "  启动 server: $tag"
    llama-server -m "$m" -t 4 -c 4096 -fa 1 --no-mmap --host 127.0.0.1 --port 8081 \
      > "$RESULTS/server_q_${tag}_${STAMP}.log" 2>&1 &
    local SPID=$!
    local i=0
    while [ $i -lt 90 ]; do
      curl -s --max-time 2 http://127.0.0.1:8081/health 2>/dev/null | grep -qi ok && break
      kill -0 $SPID 2>/dev/null || break
      sleep 1; i=$((i+1))
    done

    : > "$out"
    local n=0
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      case "$p" in \#*) continue ;; esac
      n=$((n+1))
      printf '===== Q%02d =====\nQ: %s\nA: ' "$n" "$p" >> "$out"
      curl -s --max-time 300 -X POST http://127.0.0.1:8081/completion \
        -H 'Content-Type: application/json' \
        -d "$(python3 -c 'import json,sys;print(json.dumps({"prompt":sys.argv[1],"n_predict":192,"temperature":0,"cache_prompt":False}))' "$p")" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin).get("content","").strip())' \
        >> "$out" 2>/dev/null
      printf '\n\n' >> "$out"
    done < "$list"

    kill $SPID 2>/dev/null; wait $SPID 2>/dev/null
    log "    完成 $n 条 -> $out"
  done
}

# ============================================================
# 长上下文补点（16K / 32K）——单点，r=1，耗时长
stage_ctx() {
  hr; log "STAGE ctx — 长上下文补点"
  local d="${DEPTH:-16384}"
  local M="$MODELS"

  log "  官方 Q4_0 @ d${d}（补齐对照缺口）"
  local t0=$(date +%s)
  "$BENCH" -m "$M/Qwen3.5-2B-Q4_0.gguf" -t 4 -p 512 -n 64 -d "$d" \
    -fa 1 -mmp 0 -r 1 > "$RESULTS/ctx_off_d${d}_${STAMP}.txt" 2>&1
  log "    耗时 $(( $(date +%s) - t0 ))s"
  grep -E 'pp512|tg64' "$RESULTS/ctx_off_d${d}_${STAMP}.txt" | sed 's/^/    /' | tee -a "$LOG"

  log "  自产 Q4_0 @ d${d}"
  t0=$(date +%s)
  "$BENCH" -m "$M/Qwen3.5-2B-Q4_0-self.gguf" -t 4 -p 512 -n 64 -d "$d" \
    -fa 1 -mmp 0 -r 1 > "$RESULTS/ctx_self_d${d}_${STAMP}.txt" 2>&1
  log "    耗时 $(( $(date +%s) - t0 ))s"
  grep -E 'pp512|tg64' "$RESULTS/ctx_self_d${d}_${STAMP}.txt" | sed 's/^/    /' | tee -a "$LOG"
}

# ============================================================
summary() {
  hr; log "汇总"
  log "  日志: $LOG"
  log "  结果目录: $RESULTS"
  if [ ${#FAILED[@]} -eq 0 ]; then
    log "  状态: 全部成功"
  else
    log "  失败项 (${#FAILED[@]}): ${FAILED[*]}"
  fi
  log "  当前内存: $(free -h | awk '/Mem:/{print $3"/"$2}')  温度: $(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf "%.0fC", $1/1000}')"
}

# ============================================================
main() {
  local stage="${1:-all}"
  log "run_tomorrow 开始  stage=$stage  host=$(hostname)"
  log "内存 $(free -h | awk '/Mem:/{print $3"/"$2}')  磁盘 $(df -h "$HOME" | awk 'NR==2{print $4" 可用"}')"

  case "$stage" in
    prep)    stage_prep ;;
    4b)      stage_4b ;;
    kv)      stage_kv ;;
    server)  stage_server ;;
    quality) stage_quality ;;
    ctx)     stage_ctx ;;
    all)     stage_prep; stage_4b; stage_kv; stage_server ;;
    *)       log "未知阶段: $stage"; echo "用法: bash $0 [prep|4b|kv|server|quality|ctx|all]"; exit 2 ;;
  esac

  summary
}

main "$@"
