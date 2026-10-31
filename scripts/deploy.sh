#!/usr/bin/env bash
# ============================================================
# deploy.sh — 进迭时空 K1 (RISC-V) Qwen3.5 本地推理一键部署
#
# 用法:
#   bash deploy.sh            # 完整流程：环境检查 → 依赖 → 模型校验 → 冒烟
#   bash deploy.sh check      # 仅环境检查
#   bash deploy.sh deps       # 仅安装依赖
#   bash deploy.sh models     # 仅校验模型文件
#   bash deploy.sh smoke      # 仅冒烟测试
#
# 前置条件:
#   1. 系统为 Bianbu 2.3.x (K1 镜像)，内核含 SpacemiT 补丁
#   2. 模型 GGUF 文件置于 $CIE_HOME/models/ (默认 ~/cie/models)
#   3. 有 sudo 权限（安装 apt 包时）
#
# 设计原则:
#   - 每一步失败即停并给出可执行的修复建议
#   - 不自动下载模型（13GB 级，且需用户确认来源）
#   - 全程只读系统信息，除 apt 安装外不修改系统
# ============================================================

set -u

CIE="${CIE_HOME:-$HOME/cie}"
MODELS="$CIE/models"
RESULTS="$CIE/results"
PASS=0
FAIL=0

# 期望的模型文件（名称:最小体积MB）
declare -A EXPECT=(
  ["Qwen3.5-2B-Q4_0-self.gguf"]=1100
  ["Qwen3.5-4B-Q4_0-self.gguf"]=2300
)

ok()   { echo "  [OK]   $*"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $*"; }
sec()  { echo; echo "== $* =="; }

# ------------------------------------------------------------
check_env() {
  sec "环境检查"

  # 架构
  local arch; arch=$(uname -m)
  [ "$arch" = "riscv64" ] && ok "架构 riscv64" || bad "架构为 $arch，本脚本要求 riscv64"

  # RVV + IME 扩展
  local isa; isa=$(grep -m1 '^isa' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | tr -d ' ')
  if echo "$isa" | grep -q 'v'; then ok "RVV 向量扩展在位"; else bad "缺少 RVV (v) 扩展，无法启用向量加速"; fi
  if echo "$isa" | grep -q 'ime'; then ok "IME AI 扩展在位（K1 独有）"; else warn "未检测到 ime 扩展，IME 加速路径不可用"; fi

  # 内存
  local mem_mb; mem_mb=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
  if [ "$mem_mb" -ge 7000 ]; then ok "内存 ${mem_mb} MB"; else warn "内存仅 ${mem_mb} MB，4B 模型可能紧张"; fi

  # 磁盘
  local free_gb; free_gb=$(df -BG "${HOME}" | awk 'NR==2{gsub("G","",$4); print $4}')
  if [ "$free_gb" -ge 10 ]; then ok "可用磁盘 ${free_gb} GB"; else bad "可用磁盘仅 ${free_gb} GB，建议 ≥10GB"; fi

  # 系统版本
  local ver; ver=$(grep '^PRETTY_NAME' /etc/os-release 2>/dev/null | cut -d'"' -f2)
  echo "$ver" | grep -q Bianbu && ok "系统: $ver" || warn "系统为 $ver（非 Bianbu，厂商优化可能缺失）"

  # 内核
  ok "内核: $(uname -r)"

  # 关键包
  for p in llama.cpp-tools-spacemit spacemit-tcm; do
    if dpkg -l "$p" 2>/dev/null | grep -q '^ii'; then
      ok "已安装 $p ($(dpkg -l "$p" | awk '/^ii/{print $3}'))"
    else
      warn "未安装 $p"
    fi
  done

  # TCM 设备
  if [ -e /dev/tcm ]; then ok "TCM 设备节点存在 (/dev/tcm)"; else warn "无 /dev/tcm，TCM 加速不可用"; fi
}

# ------------------------------------------------------------
install_deps() {
  sec "安装依赖"
  echo "  将执行: sudo apt update && sudo apt install -y llama.cpp-tools-spacemit spacemit-tcm"
  if sudo apt update -qq && sudo apt install -y llama.cpp-tools-spacemit spacemit-tcm; then
    ok "依赖安装完成"
  else
    bad "依赖安装失败——若源中无此包，需从源码编译（见 docs/REPORT.md 附录A）"
    return 1
  fi
}

# ------------------------------------------------------------
check_models() {
  sec "模型文件校验"
  [ -d "$MODELS" ] || { bad "模型目录不存在: $MODELS"; return 1; }

  echo "  目录: $MODELS"
  local missing=0
  for f in "${!EXPECT[@]}"; do
    local path="$MODELS/$f"
    if [ ! -f "$path" ]; then
      bad "缺失 $f"
      missing=$((missing+1)); continue
    fi
    local mb; mb=$(du -m "$path" | cut -f1)
    if [ "$mb" -lt "${EXPECT[$f]}" ]; then
      bad "$f 体积异常 (${mb}MB < ${EXPECT[$f]}MB)，可能未传完"
    else
      ok "$f  ${mb} MB"
    fi
  done

  if [ $missing -gt 0 ]; then
    echo
    echo "  缺失文件需从转换流程产出，或拷贝现成 GGUF 到 $MODELS"
    echo "  转换流程见 docs/REPORT.md 附录A"
    return 1
  fi

  # sha256 可选校验（若存在清单）
  if [ -f "$CIE/docs/hashes.txt" ]; then
    echo "  发现哈希清单，校验中（较慢，约 1 分钟）..."
    (cd "$MODELS" && sha256sum -c "$CIE/docs/hashes.txt" 2>&1 | tail -3) \
      && ok "sha256 校验通过" || warn "sha256 校验有差异，请核对"
  fi
}

# ------------------------------------------------------------
smoke_test() {
  sec "冒烟测试（生成 8 token）"
  local m="$MODELS/Qwen3.5-2B-Q4_0-self.gguf"
  [ -f "$m" ] || { bad "模型不存在: $m"; return 1; }

  echo "  运行: llama-cli -m $(basename "$m") -p 你好 -n 8 -c 2048 -st --no-mmap"
  local out
  out=$(timeout 180 llama-cli -m "$m" -p "你好" -n 8 -c 2048 -st --no-mmap 2>&1)
  if echo "$out" | grep -qiE 't/s|Exiting'; then
    ok "推理正常出字"
    echo "$out" | grep -E 'Prompt:|Generation:' | tail -2 | sed 's/^/         /'
  else
    bad "推理失败，末尾输出："
    echo "$out" | tail -6 | sed 's/^/         /'
    return 1
  fi
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
    all)
      check_env
      if [ $FAIL -gt 0 ]; then
        echo
        echo "环境检查有 $FAIL 项失败，请先修复再继续。"
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
    *) echo "未知阶段: $stage"; echo "用法: bash $0 [check|deps|models|smoke|all]"; exit 2 ;;
  esac

  echo
  echo "=========================================================="
  echo " 结果: 通过 $PASS 项，失败 $FAIL 项"
  echo "=========================================================="
  [ $FAIL -eq 0 ] || exit 1
}

main "$@"
