#!/usr/bin/env bash
# ============================================================
# 04_build_quantizer.sh — 构建 v0.2.3 的量化器（llama-quantize）
#
# 【为什么需要这一步】
#   03_quantize.sh 必须用 v0.2.3 的 quantize，原因是 0.1.1 遇到 16 列的小张量
#   直接失败：
#     warning: blk.0.ssm_alpha.weight - ncols 16 not divisible by 32
#     llama_model_quantize: failed to quantize: no tensor type fallback is defined
#   v0.2.3 具备「装不下的张量回退为 F16」的逻辑，这正是本方案能产出 Q4_0 的前提。
#
# 【为什么本脚本关掉 GGML_SPACEMIT】
#   量化是纯 CPU 的数学运算（读 f16、按块量化、写 GGUF），不经过 IME/TCM。
#   关掉 SpacemiT 后端可完全绕开 SPERT 运行时依赖，构建更简单；
#   产出的 GGUF 与后端无关（GGUF 为小端格式，量化数学与 CPU 架构无关）。
#   注意：这个二进制【只用于量化】，不要拿它跑推理基准（没有 IME，会慢很多）。
#
# 【运行环境】Linux / WSL（需要 g++ 与 cmake）
#   native（默认）：在 x86 上构建，最快，产出本机可执行
#   riscv        ：交叉编译为 riscv64，可在 K1 上直接运行（需 RISCV_ROOT_PATH）
#
# 【用法】
#   bash 04_build_quantizer.sh              # 本机构建（推荐）
#   bash 04_build_quantizer.sh riscv        # 交叉编译 riscv64（需先 export RISCV_ROOT_PATH）
#   bash 04_build_quantizer.sh check        # 只检查现状，不构建
#
# 产物: $CIE_HOME/src/llama023/bin/llama-quantize
# ============================================================

set -u
CIE="${CIE_HOME:-$PWD}"
MODE="${1:-native}"
SRC="${SRC_DIR:-$CIE/llama.cpp}"
DEST="$CIE/src/llama023"
BIN="$DEST/bin/llama-quantize"
TAG="v0.2.3"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

say() { echo "  $*"; }
die() { echo; echo "[失败] $*"; exit 1; }

echo "=========================================================="
echo " 构建量化器 llama-quantize ($TAG)"
echo " 源码: $SRC"
echo " 产物: $BIN"
echo "=========================================================="

# ---------- check ----------
if [ "$MODE" = "check" ]; then
  [ -x "$BIN" ] && say "已存在可执行: $BIN" || say "尚不存在: $BIN"
  [ -f "$SRC/CMakeLists.txt" ] && say "源码在位: $(cat "$SRC/VERSION_NUMBER" 2>/dev/null | tr -d '[:space:]')" \
                               || say "源码缺失: $SRC"
  command -v cmake >/dev/null && say "cmake: $(cmake --version | head -1)" || say "cmake 未安装"
  command -v g++ >/dev/null && say "g++: $(g++ -dumpversion)" || say "g++ 未安装"
  exit 0
fi

# ---------- 已存在则跳过 ----------
if [ -x "$BIN" ]; then
  say "量化器已存在，跳过构建。"
  "$BIN" --help 2>&1 | head -2 | sed 's/^/    /'
  echo
  echo "如需重建: rm -f $BIN 后重跑本脚本"
  exit 0
fi

# ---------- 源码 ----------
if [ ! -f "$SRC/CMakeLists.txt" ]; then
  echo "源码缺失，尝试获取 $TAG ..."
  mkdir -p "$(dirname "$SRC")"
  URL="https://codeload.github.com/spacemit-com/llama.cpp/zip/refs/tags/$TAG"
  tmpzip="/tmp/llama-$TAG.zip"
  if command -v curl >/dev/null; then
    curl -L --max-time 600 -o "$tmpzip" "$URL" -s -w "    下载状态: %{http_code}  %{size_download} 字节\n"
  elif command -v wget >/dev/null; then
    wget -q -O "$tmpzip" "$URL" && echo "    下载完成"
  else
    die "需要 curl 或 wget 下载源码"
  fi
  [ -s "$tmpzip" ] || die "源码下载失败。手动获取后重试：
    curl -L -o /tmp/l.zip https://codeload.github.com/spacemit-com/llama.cpp/zip/refs/tags/$TAG
    unzip -q /tmp/l.zip -d /tmp && mv /tmp/llama.cpp-0.2.3 '$SRC'"
  command -v unzip >/dev/null || die "需要 unzip"
  rm -rf /tmp/_llama_extract && mkdir -p /tmp/_llama_extract
  unzip -q "$tmpzip" -d /tmp/_llama_extract
  inner=$(find /tmp/_llama_extract -maxdepth 1 -mindepth 1 -type d | head -1)
  [ -n "$inner" ] || die "解压后未找到目录"
  mkdir -p "$(dirname "$SRC")"
  mv "$inner" "$SRC"
  rm -rf /tmp/_llama_extract "$tmpzip"
  say "源码就绪: $SRC"
fi

ver=$(cat "$SRC/VERSION_NUMBER" 2>/dev/null | tr -d '[:space:]')
say "源码版本: ${ver:-未知}"
if [ -n "$ver" ] && [ "$ver" != "0.2.3" ]; then
  say "[注意] 版本为 $ver，本方案验证过的是 0.2.3；"
  say "       其他版本的小张量回退逻辑可能不同，产物请在 03 之后用 gguf_types.py 校验。"
fi

# ---------- 构建 ----------
BUILD="$SRC/build-quant"
rm -rf "$BUILD"

CMAKE_ARGS=(
  -S "$SRC" -B "$BUILD"
  -DCMAKE_BUILD_TYPE=Release
  -DGGML_SPACEMIT=OFF          # 量化不需要 IME，关掉即免去 SPERT 依赖
  -DBUILD_SHARED_LIBS=OFF      # 静态链接，产物自包含，无 rpath 问题
  -DLLAMA_OPENSSL=OFF
  -DLLAMA_BUILD_SERVER=OFF
  -DLLAMA_BUILD_UI=OFF         # 源码包不含前端产物，开着会因 xxd 失败
  -DLLAMA_BUILD_HTML=OFF
  -DLLAMA_BUILD_TESTS=OFF
  -DLLAMA_BUILD_EXAMPLES=OFF
  -DLLAMA_BUILD_APP=OFF
  -DLLAMA_BUILD_TOOLS=ON       # quantize 属于 tools，必须保留
)

if [ "$MODE" = "riscv" ]; then
  TC="$SRC/cmake/riscv64-spacemit-linux-gnu-gcc.cmake"
  [ -f "$TC" ] || die "找不到工具链文件: $TC"
  if [ -z "${RISCV_ROOT_PATH:-}" ]; then
    die "交叉编译需要先设置工具链路径：
    export RISCV_ROOT_PATH=/path/to/spacemit-toolchain-linux-glibc-x86_64-v1.2.4"
  fi
  say "交叉编译模式，工具链: $RISCV_ROOT_PATH"
  CMAKE_ARGS+=(-DCMAKE_TOOLCHAIN_FILE="$TC")
  # riscv 交叉场景下避免 GGML_NATIVE 误判为宿主 CPU
  CMAKE_ARGS+=(-DGGML_NATIVE=OFF)
else
  say "本机构建模式（x86），产物仅用于量化"
fi

echo
echo "== 配置 =="
cmake "${CMAKE_ARGS[@]}" > /tmp/quant_cfg.log 2>&1 || {
  echo "配置失败，末尾 20 行："; tail -20 /tmp/quant_cfg.log; die "cmake 配置失败";
}
grep -E "GGML_SYSTEM_ARCH|CMAKE_SYSTEM_PROCESSOR" /tmp/quant_cfg.log | head -2 | sed 's/^/    /'
say "配置完成"

echo
echo "== 编译（仅 llama-quantize 一个目标，比全量构建快得多）=="
if ! cmake --build "$BUILD" --target llama-quantize --parallel "$JOBS" > /tmp/quant_build.log 2>&1; then
  echo "编译失败，首个 error："
  grep -m5 -E "error:|Error " /tmp/quant_build.log | sed 's/^/    /' || tail -20 /tmp/quant_build.log
  die "编译失败（完整日志: /tmp/quant_build.log）"
fi
say "编译完成"

# ---------- 安装 ----------
FOUND=$(find "$BUILD" -name 'llama-quantize' -type f -perm -u+x | head -1)
[ -n "$FOUND" ] || die "未找到 llama-quantize 产物（检查 LLAMA_BUILD_TOOLS 是否被关掉）"
mkdir -p "$DEST/bin"
cp "$FOUND" "$BIN"
chmod +x "$BIN"

echo
echo "== 验证 =="
file "$BIN" | sed 's/^/    /'
"$BIN" --help 2>&1 | head -2 | sed 's/^/    /' || die "产物无法执行"

echo
echo "=========================================================="
echo " 完成。下一步："
echo "   bash scripts/03_quantize.sh <f16-nomtp.gguf> Q4_0"
echo
echo " 校验产物（必须是全 Q4_0、block_count=24/32、nextn=0）："
echo "   python3 tools/gguf_types.py <产物.gguf>"
echo "=========================================================="
