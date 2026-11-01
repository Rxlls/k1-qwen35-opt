#!/usr/bin/env bash
# ============================================================
# deploy.sh — 进迭时空 K1 (RISC-V) Qwen3.5 本地推理一键部署
#
# 用法:
#   bash deploy.sh            # = all：环境检查 → 模型校验 → 冒烟 → 使用说明
#   bash deploy.sh full       # 真·一键：安装依赖 → 环境检查 → 模型校验 → 冒烟
#   bash deploy.sh check      # 仅环境检查（只读）
#   bash deploy.sh deps       # 仅安装依赖（需 sudo）
#   bash deploy.sh models     # 仅校验模型文件
#   bash deploy.sh smoke      # 仅冒烟测试
#
# 前置条件:
#   1. 系统为 Bianbu 2.3.x (K1 镜像)，内核含 SpacemiT 补丁
#   2. 模型 GGUF 置于 $CIE_HOME/models/ (默认 ~/cie/models)
#      - 若文件名与默认不同，可用 MODEL_2B / MODEL_4B 环境变量指定
#      - 未指定时会自动匹配 Qwen3.5-2B-*.gguf / Qwen3.5-4B-*.gguf
#   3. full / deps 需要 sudo 权限
#
# 模型从哪来（本脚本不下载 13GB 权重）:
#   - 自己转换：scripts/00_fetch_models.sh → 01 → 02 → 04 → 03（见 docs/DEPLOY.md）
#   - 或从发布页取现成 GGUF 放入 models/
#
# 设计原则:
#   - 每一步失败即停并给出可执行的修复建议
#   - 不自动下载模型（体积大，且需用户确认来源）
#   - 除 apt 安装外不修改系统
# ============================================================

set -u

CIE="${CIE_HOME:-$HOME/cie}"
MODELS="$CIE/models"
RESULTS="$CIE/results"
PASS=0
FAIL=0

# 期望的模型（可用环境变量覆盖）
MODEL_2B="${MODEL_2B:-Qwen3.5-2B-Q4_0-self.gguf}"
MODEL_4B="${MODEL_4B:-Qwen3.5-4B-Q4_0-self.gguf}"
MIN_2B="${MIN_2B:-1100}"   # MB
MIN_4B="${MIN_4B:-2300}"   # MB

ok()   { echo "  [OK]   $*"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $*"; }
sec()  { echo; echo "== $* =="; }

# 解析实际使用的模型路径：先按名字；否则在同类文件中挑，排除转换中间产物（f16 / nomtp），
# 并优先选择 Q4_0 成品（K1 上唯一推荐格式）。
resolve_model() {
  local want="$1" pattern="$2" cand pref
  if [ -f "$MODELS/$want" ]; then echo "$MODELS/$want"; return 0; fi

  cand=$(ls -S "$MODELS"/$pattern 2>/dev/null | grep -vE -- '-(f16|nomtp)|\.part$|\.tmp$')
  [ -n "$cand" ] || { echo ""; return 1; }

  pref=$(printf '%s\n' "$cand" | grep -i 'q4_0' | head -1)
  if [ -n "$pref" ]; then echo "$pref"; return 0; fi

  printf '%s\n' "$cand" | head -1
  return 0
}

# ------------------------------------------------------------
check_env() {
  sec "环境检查"

  local arch; arch=$(uname -m)
  [ "$arch" = "riscv64" ] && ok "架构 riscv64" || bad "架构为 $arch，本脚本要求 riscv64"

  local isa; isa=$(grep -m1 '^isa' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | tr -d ' ')
  if echo "$isa" | grep -q 'v'; then ok "RVV 向量扩展在位"; else bad "缺少 RVV (v) 扩展，无法启用向量加速"; fi
  if echo "$isa" | grep -q 'ime'; then ok "IME AI 扩展在位（K1 独有）"; else warn "未检测到 ime 扩展，IME 加速路径不可用"; fi

  local mem_mb; mem_mb=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
  if [ "$mem_mb" -ge 7000 ]; then ok "内存 ${mem_mb} MB"; else warn "内存仅 ${mem_mb} MB，4B 模型可能紧张"; fi

  local free_gb; free_gb=$(df -BG "${HOME}" | awk 'NR==2{gsub("G","",$4); print $4}')
  if [ "$free_gb" -ge 10 ]; then ok "可用磁盘 ${free_gb} GB"; else bad "可用磁盘仅 ${free_gb} GB，建议 ≥10GB"; fi

  local ver; ver=$(grep '^PRETTY_NAME' /etc/os-release 2>/dev/null | cut -d'"' -f2)
  echo "$ver" | grep -q Bianbu && ok "系统: $ver" || warn "系统为 $ver（非 Bianbu，厂商优化可能缺失）"

  ok "内核: $(uname -r)"

  for p in llama.cpp-tools-spacemit spacemit-tcm; do
    if dpkg -l "$p" 2>/dev/null | grep -q '^ii'; then
      ok "已安装 $p ($(dpkg -l "$p" | awk '/^ii/{print $3}'))"
    else
      warn "未安装 $p"
    fi
  done

  if [ -e /dev/tcm ]; then
    ok "TCM 设备节点存在 (/dev/tcm) $(ls -l /dev/tcm | awk '{print $1}')"
    if [ -r /dev/tcm ] && [ -w /dev/tcm ]; then
      warn "/dev/tcm 已对外开放。apt 原版 0.1.1 在此状态下 prefill 会下降约 38%（半可用状态）"
      warn "建议恢复出厂权限：sudo chmod 600 /dev/tcm  （详见 docs/DEPLOY.md §5.3）"
    else
      ok "/dev/tcm 为默认 600 —— 原版 0.1.1 将回退纯堆内存，这是预期且最快的行为，请勿 chmod"
    fi
    if fuser /dev/tcm >/dev/null 2>&1; then
      warn "/dev/tcm 正被其它进程占用（TCM 为独占资源），会拖慢当前测量：fuser -v /dev/tcm"
    fi
  else
    warn "无 /dev/tcm，TCM 加速不可用"
  fi
}

# ------------------------------------------------------------
install_deps() {
  sec "安装依赖"
  echo "  将执行: sudo apt update && sudo apt install -y llama.cpp-tools-spacemit spacemit-tcm"
  if sudo apt update -qq && sudo apt install -y llama.cpp-tools-spacemit spacemit-tcm; then
    ok "依赖安装完成"
  else
    bad "依赖安装失败——若源中无此包，说明系统非 Bianbu 或固件过旧"
    echo
    echo "  可行路径："
    echo "    a) 确认系统为 Bianbu 2.3.x K1 镜像（docs/DEPLOY.md §1）"
    echo "    b) 从源码交叉编译带 TCM patch 的版本（docs/PATCH_TCM.md）"
    return 1
  fi
}

# ------------------------------------------------------------
check_models() {
  sec "模型文件校验"
  [ -d "$MODELS" ] || { bad "模型目录不存在: $MODELS"; return 1; }

  echo "  目录: $MODELS"
  local missing=0
  local pair name min size
  for pair in "2B:$MODEL_2B:$MIN_2B" "4B:$MODEL_4B:$MIN_4B"; do
    size="${pair%%:*}"; rest="${pair#*:}"
    name="${rest%%:*}"; min="${rest##*:}"

    local path; path=$(resolve_model "$name" "Qwen3.5-$size-*.gguf")
    if [ -z "$path" ]; then
      bad "缺失 $name（也未匹配到 Qwen3.5-$size-*.gguf）"
      missing=$((missing+1)); continue
    fi
    [ "$(basename "$path")" != "$name" ] && warn "未找到 $name，改用 $(basename "$path")"

    local mb; mb=$(du -m "$path" | cut -f1)
    if [ "$mb" -lt "$min" ]; then
      bad "$(basename "$path") 体积异常 (${mb}MB < ${min}MB)，可能未传完"
    else
      ok "$(basename "$path")  ${mb} MB"
    fi
  done

  if [ $missing -gt 0 ]; then
    echo
    echo "  模型获取方式（二选一）："
    echo "    a) 自建管线（可复现，推荐）："
    echo "         bash scripts/00_fetch_models.sh 2b"
    echo "         bash scripts/01_convert.sh 2b"
    echo "         bash scripts/02_strip_mtp.sh"
    echo "         bash scripts/04_build_quantizer.sh"
    echo "         bash scripts/03_quantize.sh <f16-nomtp.gguf> Q4_0"
    echo "       详见 docs/DEPLOY.md"
    echo "    b) 使用现成 GGUF，放入 $MODELS/ 后用 MODEL_2B=<文件名> 指定"
    return 1
  fi

  if [ -f "$CIE/docs/hashes.txt" ]; then
    echo "  发现哈希清单，校验中（较慢，约 1 分钟）..."
    (cd "$MODELS" && sha256sum -c "$CIE/docs/hashes.txt" 2>&1 | tail -3) \
      && ok "sha256 校验通过" || warn "sha256 校验有差异，请核对"
  fi
}

# ------------------------------------------------------------
# 选 llama-cli：LLAMA_CLI 显式指定优先；否则优先 apt 原版（项目基线）；
# 最后才退回 PATH 里的（可能是自建的 patched 版本）。
pick_cli() {
  local c
  for c in "${LLAMA_CLI:-}" /usr/bin/llama-cli "$(command -v llama-cli 2>/dev/null)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

# 退出码翻译：timeout 透传子进程状态，128+N 即收到信号 N
rc_desc() {
  case "$1" in
    0)   echo "正常" ;;
    124) echo "超时（180s 内未出字）" ;;
    132) echo "SIGILL 非法指令" ;;
    134) echo "SIGABRT 断言失败（线程数超 perfer_core_ids 最常见）" ;;
    135) echo "SIGBUS 总线错误（mmap／大页异常）" ;;
    139) echo "SIGSEGV 段错误（多为动态库版本混用）" ;;
    *)   echo "退出码 $1" ;;
  esac
}

# 跑一次冒烟；成功返回 0，同时把输出与退出码留在 SMOKE_OUT / SMOKE_RC
run_smoke() {
  local bin="$1" model="$2" extra="$3"
  echo "  运行: $(basename "$bin") -m $(basename "$model") -p 你好 -n 8 ${extra}"
  SMOKE_OUT=$(timeout 180 "$bin" -m "$model" -p "你好" -n 8 ${extra} 2>&1); SMOKE_RC=$?
  if echo "$SMOKE_OUT" | grep -qiE 'Generation:|Exiting'; then
    ok "推理正常出字（$(basename "$bin") ${extra}）"
    echo "$SMOKE_OUT" | grep -E 'Prompt:|Generation:' | tail -2 | sed 's/^/         /'
    return 0
  fi
  echo "  [FAIL] $(rc_desc "$SMOKE_RC")"
  echo "$SMOKE_OUT" | tail -6 | sed 's/^/         /'
  return 1
}

smoke_test() {
  sec "冒烟测试（生成 8 token）"
  local m; m=$(resolve_model "$MODEL_2B" "Qwen3.5-2B-*.gguf")
  [ -n "$m" ] || { bad "找不到可用的 2B 模型"; return 1; }

  # -t 4 是硬性要求：0.1.1 的 spacemit 后端在 ime.cpp:1704 断言
  #   thread_n N exceeds perfer_core_ids size 4
  # 默认线程数=8 会直接 abort（core dump），不是变慢。详见 docs/DEPLOY.md §5。
  local cli; cli=$(pick_cli) || { bad "找不到 llama-cli（PATH 与 /usr/bin 均无）"; return 1; }
  echo "  二进制: $cli"

  # 自建产物没设 rpath 时会静默加载系统旧库：把真正生效的库打出来
  local libs
  libs=$(ldd "$cli" 2>/dev/null | awk '/libllama|libggml/{print $3}' \
         | xargs -r -n1 basename 2>/dev/null | paste -sd' ' -)
  [ -n "$libs" ] && echo "  动态库: $libs"
  if [ -d "$CIE/src/llama011/lib" ]; then
    echo "  注意: 存在自建产物 $CIE/src/llama011/lib；用它须先 export LD_LIBRARY_PATH"
    echo "        否则跑的仍是系统库（日志会继续报 /dev/tcm_sync_mem）"
  fi

  local ok_try=0
  run_smoke "$cli" "$m" "-c 2048 -t 4 -st --no-mmap" && ok_try=1

  if [ $ok_try -eq 0 ]; then
    warn "第一次失败（$(rc_desc "$SMOKE_RC")），改 mmap 模式重试"
    run_smoke "$cli" "$m" "-c 2048 -t 4 -st" && ok_try=1
  fi

  if [ $ok_try -eq 0 ] && [ "$cli" != "/usr/bin/llama-cli" ] && [ -x /usr/bin/llama-cli ]; then
    warn "仍失败，换 apt 原版 /usr/bin/llama-cli 重试（项目基线版本）"
    run_smoke /usr/bin/llama-cli "$m" "-c 2048 -t 4 -st --no-mmap" && ok_try=1
  fi

  if [ $ok_try -eq 0 ]; then
    bad "冒烟失败（3 种组合均未出字）"
    echo "         定位命令：dmesg | tail -5   ／   free -m   ／   ldd $cli | grep -E 'llama|ggml'"
    echo "         判读要点：apt 原版报 open(/dev/tcm_sync_mem) errno=2 后回退堆内存，"
    echo "                   属预期且最快，不作为失败依据；errno=13 只会出现在打了 TCM patch 的版本上"
    return 1
  fi
  return 0
}

# ------------------------------------------------------------
usage_help() {
  sec "使用说明"
  cat <<'EOF'
  单轮对话:
    llama-cli -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -c 4096 -st --no-mmap

  交互对话（关闭思考模式）:
    llama-cli -m ~/cie/models/Qwen3.5-4B-Q4_0-self.gguf -t 4 -c 4096 -cnv \
      --chat-template-kwargs '{"enable_thinking":false}'

  API 服务:
    llama-server -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -c 8192 \
      --host 127.0.0.1 --port 8080

  基准测试:
    bash ~/cie/tools/bench_quick.sh Qwen3.5-2B-Q4_0-self.gguf my_tag

  重要约束:
    - 线程数必须为 4（8 线程会使 decode 下降 70%）
    - 仅使用 Q4_0 格式（Q5_K/Q3_K/q8_0-KV 不在 IME 白名单，慢 3~7 倍）
    - 长 prompt 首 token 延迟约 62 秒/1200 token，属硬件带宽限制
EOF
}

# ------------------------------------------------------------
main() {
  local stage="${1:-all}"
  echo "=========================================================="
  echo " K1 Qwen3.5 推理优化 · 部署验证"
  echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')   主机: $(hostname)"
  echo "=========================================================="

  case "$stage" in
    check)  check_env ;;
    deps)   install_deps ;;
    models) check_models ;;
    smoke)  smoke_test ;;
    full)
      # 真·一键：装依赖 → 检查 → 模型 → 冒烟
      install_deps || { echo; echo "依赖安装失败，终止。"; exit 1; }
      check_env
      if [ $FAIL -gt 0 ]; then
        echo; echo "环境检查有 $FAIL 项失败，请先修复再继续。"; exit 1
      fi
      check_models
      if [ $FAIL -gt 0 ]; then
        echo; echo "模型文件缺失，跳过冒烟测试。"; exit 1
      fi
      smoke_test
      usage_help
      ;;
    all)
      check_env
      if [ $FAIL -gt 0 ]; then
        echo
        echo "环境检查有 $FAIL 项失败，请先修复再继续。"
        echo "若缺的是依赖包：bash $0 deps   或   bash $0 full"
        exit 1
      fi
      check_models
      if [ $FAIL -gt 0 ]; then
        echo
        echo "模型文件缺失，跳过冒烟测试。"
        usage_help
        exit 1
      fi
      smoke_test
      usage_help
      ;;
    *) echo "未知阶段: $stage"; echo "用法: bash $0 [all|full|check|deps|models|smoke]"; exit 2 ;;
  esac

  echo
  echo "=========================================================="
  echo " 结果: 通过 $PASS 项，失败 $FAIL 项"
  echo "=========================================================="
  [ $FAIL -eq 0 ] || exit 1
}

main "$@"
