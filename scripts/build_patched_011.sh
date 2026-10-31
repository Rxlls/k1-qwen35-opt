#!/usr/bin/env bash
# ============================================================
# build_patched_011.sh — 在 WSL 内交叉编译「带 TCM 路径修复」的 llama.cpp 0.1.1
#
# 在 WSL (Ubuntu-24.04) 终端执行，不要在 K1 上跑：
#   bash "/mnt/c/Users/RX/Desktop/作业以及课程设计论文&GSR/CIE/scripts/build_patched_011.sh"
#
# 流程：检查工具链 → 取源码 → 改一行 → cmake 配置 → 编译 → 打包 → 复制到桌面
# ============================================================

set -u

WORK="${WORK:-$HOME/k1build}"
SRC="$WORK/llama011"
INSTALL="$WORK/install011"
TOOLCHAIN="$WORK/spacemit-toolchain-linux-glibc-x86_64-v1.2.4"
TAG="spacemit-llama.cpp.riscv64.0.1.1"
OUT_TGZ="$WORK/llama011-patched.tar.gz"

echo "=========================================================="
echo " 编译带 TCM patch 的 llama.cpp 0.1.1"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 工作目录: $WORK"
echo "=========================================================="

# ---------- 1. 工具链 ----------
echo
echo "== 1/7 工具链检查 =="
if [ ! -d "$TOOLCHAIN" ]; then
  echo "未找到工具链: $TOOLCHAIN"
  echo "尝试下载（约几分钟）..."
  mkdir -p "$WORK" && cd "$WORK" || exit 1
  wget -q --show-progress https://archive.spacemit.com/toolchain/spacemit-toolchain-linux-glibc-x86_64-v1.2.4.tar.xz || exit 1
  tar xf spacemit-toolchain-linux-glibc-x86_64-v1.2.4.tar.xz || exit 1
fi
export RISCV_ROOT_PATH="$TOOLCHAIN"
"$TOOLCHAIN/bin/riscv64-unknown-linux-gnu-gcc" --version | head -1 || {
  echo "工具链不可用"; exit 1;
}
echo "RISCV_ROOT_PATH=$RISCV_ROOT_PATH"

# ---------- 2. 源码 ----------
echo
echo "== 2/7 获取源码 (tag: $TAG) =="
mkdir -p "$WORK"
if [ ! -d "$SRC" ]; then
  cd "$WORK" || exit 1
  if ! git clone --depth 1 --branch "$TAG" https://github.com/spacemit-com/llama.cpp llama011; then
    # 本机 github.com:443 常被墙，但 codeload.github.com 可达：改用 tag 源码包
    echo "  git clone 失败，改用 codeload 源码包..."
    rm -rf llama011 llama011.tar.gz _llamaext
    curl -L --retry 3 --retry-delay 2 -o llama011.tar.gz \
      "https://codeload.github.com/spacemit-com/llama.cpp/tar.gz/refs/tags/$TAG" || {
      echo "源码包下载失败。可手动下载该 tar.gz 放入 $WORK 后重跑本脚本。"; exit 1;
    }
    mkdir -p _llamaext && tar xzf llama011.tar.gz -C _llamaext || exit 1
    INNER="$(find _llamaext -maxdepth 1 -mindepth 1 -type d | head -1)"
    [ -n "$INNER" ] || { echo "源码包结构异常"; exit 1; }
    mv "$INNER" llama011 && rm -rf _llamaext llama011.tar.gz
  fi
fi
cd "$SRC" || exit 1
echo "  VERSION_NUMBER : $(cat VERSION_NUMBER 2>/dev/null)"
echo "  commit         : $(git rev-parse --short HEAD 2>/dev/null)"
git submodule update --init --recursive --depth 1 >/dev/null 2>&1 || true

# ---------- 3. 应用 patch ----------
echo
echo "== 3/7 应用 TCM 路径 patch =="
F="ggml/src/ggml-cpu/spacemit/spine_mem_pool.cpp"
[ -f "$F" ] || { echo "找不到 $F，源码结构异常"; exit 1; }
echo "  改前: $(sed -n '30p' "$F")"
sed -i 's|"/dev/tcm_sync_mem"|"/dev/tcm"|' "$F"
echo "  改后: $(sed -n '30p' "$F")"
sed -n '30p' "$F" | grep -q '"/dev/tcm"' || { echo "patch 未生效"; exit 1; }

# ---------- 4. 配置 ----------
echo
echo "== 4/7 cmake 配置（约 1~2 分钟）=="
echo "  注意：0.1.1 用 -DGGML_CPU_RISCV64_SPACEMIT=ON，且不需要 SPERT"
# 上游 0.1.1 的 bug：ime.cpp 硬性要求 __riscv_zba，ggml-cpu/CMakeLists.txt 只在
# GGML_RV_ZBA 为真时才往 -march 里加 _zba，但 ggml/CMakeLists.txt 根本没定义
# GGML_RV_ZBA 这个 option，于是被当成 OFF，-march 丢掉 zba 直接编译报错。
# 这里显式打开 -DGGML_RV_ZBA=ON（该 option 未声明，cmake 会当作普通变量使用）。
# -DLLAMA_BUILD_WEBUI=OFF 关闭 WebUI 内嵌：0.1.1 的 tag 里不含前端产物
# (tools/server/public 下没有 bundle.js/index.html)，从 codeload 源码包构建时
# 该步骤必然失败，与 TCM patch 无关。
cmake -B build -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CPU_RISCV64_SPACEMIT=ON \
  -DGGML_RV_ZBA=ON \
  -DLLAMA_BUILD_WEBUI=OFF \
  -DCMAKE_TOOLCHAIN_FILE="$SRC/cmake/riscv64-spacemit-linux-gnu-gcc.cmake" \
  -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
  -DCMAKE_INSTALL_PREFIX="$INSTALL" 2>&1 | tail -30

if [ ! -f build/CMakeCache.txt ]; then
  echo
  echo "配置失败，请把上面的报错发出来"
  exit 1
fi

# 关键判据
echo
echo "  --- 关键配置结果 ---"
grep -E "RISCV64_SPACEMIT_IME_SPEC|SPACEMIT_RISCV_COMPILER_SUPPORT_IME|CMAKE_C_COMPILER:|GGML_RV_ZBA" build/CMakeCache.txt 2>/dev/null | head -6
grep -E "Adding CPU backend variant" build/CMakeCache.txt 2>/dev/null || true

# ---------- 5. 编译 ----------
echo
echo "== 5/7 编译（约 10~30 分钟，x86 上较快）=="
JOBS="${JOBS:-$(nproc)}"
echo "  并行度: $JOBS (内存不足可改为 JOBS=2 重跑)"
# 全量日志落盘：脚本里的 tail 会把真正的报错截掉，出错时便于排查
BUILD_LOG="$WORK/build011-full.log"
cmake --build build --parallel "$JOBS" >"$BUILD_LOG" 2>&1
BUILD_RC=$?
tail -25 "$BUILD_LOG"

if [ $BUILD_RC -ne 0 ]; then
  echo
  echo "编译报错，完整日志: $BUILD_LOG"
  echo "--- 首个 error ---"
  grep -n "error:" "$BUILD_LOG" | head -10
  exit 1
fi

if [ ! -x build/bin/llama-bench ]; then
  echo
  echo "编译未产出 llama-bench，完整日志: $BUILD_LOG"
  exit 1
fi

# ---------- 6. 打包 ----------
echo
echo "== 6/7 安装与打包 =="
cmake --install build >/dev/null 2>&1

# 验证 patch 真的进了产物：常量字符串应出现在 ggml-cpu 库里
LIB="$(find build -name 'libggml-cpu.so*' -type f | head -1)"
if [ -n "$LIB" ]; then
  echo "  检查 TCM 路径是否编入库 $LIB ..."
  if strings "$LIB" | grep -qx "/dev/tcm"; then
    echo "  OK: 产物中包含 \"/dev/tcm\""
  else
    echo "  警告: 未在产物中找到 \"/dev/tcm\"，请复查 patch"
  fi
  if strings "$LIB" | grep -qx "/dev/tcm_sync_mem"; then
    echo "  警告: 仍存在 \"/dev/tcm_sync_mem\"（patch 可能未完全生效）"
  else
    echo "  OK: 产物中已无 \"/dev/tcm_sync_mem\""
  fi
fi

tar czf "$OUT_TGZ" -C "$INSTALL" .
ls -lh "$OUT_TGZ"
echo "  sha256: $(sha256sum "$OUT_TGZ" | cut -d' ' -f1)"

# ---------- 7. 复制到 Windows ----------
echo
echo "== 7/7 复制到 Windows 桌面 =="
DEST="/mnt/c/Users/RX/Desktop"
if cp "$OUT_TGZ" "$DEST/" 2>/dev/null; then
  echo "  已复制到: C:\\Users\\RX\\Desktop\\llama011-patched.tar.gz"
else
  echo "  复制失败，请手动从 $OUT_TGZ 取出"
fi

echo
echo "=========================================================="
file "$INSTALL/bin/llama-bench" 2>/dev/null || true
echo "=========================================================="
echo " 完成。下一步："
echo "   1. 把 llama011-patched.tar.gz 用 Xftp 传到 K1 的 /home/a/cie/src/"
echo "   2. 在 K1 上执行："
echo "        cd ~/cie/src && mkdir -p llama011"
echo "        tar xzf llama011-patched.tar.gz -C llama011"
echo "        ~/cie/src/llama011/bin/llama-bench -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf \\"
echo "          -t 4 -p 64,512 -n 128 -fa 1 -r 3"
echo "   3. 看日志里 falling back to heap 是否消失"
echo "=========================================================="
