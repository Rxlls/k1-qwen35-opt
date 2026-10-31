# VERSIONS.md — 环境版本固化清单

> 赛题：基于K1 AI CPU的Qwen3.5本地部署与性能优化（全国RISC-V高水平创新及应用大赛·第二届）
> 本文件记录全部版本与校验值，烧录/下载后立即更新。性能数据只在"本表锁定的环境"内可比。

## 系统镜像

| 项 | 值 |
|---|---|
| 镜像文件 | Bianbu-LXQt-K1-V2.3.5-20260602111447.zip |
| 镜像类型 | eMMC刷机包（文件名不带img，Titan Flasher/fastboot用） |
| 构建日期 | 2026-06-02 |
| 文件大小 | 2,248,361,338 bytes（≈2.09GB） |
| SHA256 | 5f07ead80a7503826e75fd8f6e26a5cbd0de7a5942a91c1c6644e70f8a5e839f |
| 包内清单 | rootfs.ext4(8GB) / bootfs.ext4(256MB) / env.bin / u-boot.itb / fw_dynamic.itb / factory/FSBL.bin / factory/bootinfo_emmc.bin 等16个文件 |
| 校验日期 | 2026-10-28 |

## 硬件平台（待刷机后用实测值补全）

| 项 | 值 |
|---|---|
| 机型 | 进迭时空K1笔记本（MUSE Book类），8GB LPDDR4x + 128GB NVMe存储 |
| 内存 | 总量7.7GiB，LXQt桌面空闲时占用约1.3GiB、可用6.4GiB（2026-10-28实测）；**无swap** |
| 存储 | 系统运行于**NVMe**：nvme0n1p6=/（119G ext4）、p5=/boot（256M）；lsblk未显示eMMC设备（仅SPI mtdblock0-5），待`ls /dev/mmcblk*`复核 |
| CPU | K1，8×X60；isa=rv64imafdcv_…_zvfh_zfh_…_ime——**v(RVV)、zvfh、ime(AI扩展)全部在位** ✅ |

## 软件版本（刷机后补全）

| 项 | 值 | 采集命令 |
|---|---|---|
| Bianbu版本 | 2.3.5（Noble Numbat，基于Ubuntu 24.04源码） | 2026-10-28实测 |
| 内核 | 6.6.63 | 2026-10-28实测 |
| 桌面环境 | LXQt（镜像即LXQt版；终端中XDG_CURRENT_DESKTOP未回显，属会话变量未继承，不影响判定） | 2026-10-28 |
| GCC | 待记录 | `gcc --version` |
| CMake | 待记录 | `cmake --version` |
| Python | 待记录 | `python3 --version` |
| llama.cpp-tools-spacemit | 待记录 | `dpkg -l \| grep llama` |
| spacemit-tcm | 待记录 | `dpkg -l \| grep spacemit-tcm` |

## 模型产物（GGUF，K1端 ~/models/）

| 文件 | 量化 | 体积 | sha256 |
|---|---|---|---|
| Qwen3.5-2B-Q4_0.gguf | Q4_0 | 1.2GB（1.12GiB，1.88B参数） | cd70221bebaee0503e0f6717e174250cd7825aa88438b3aabec9ad55731d9bb1 |
| Qwen3.5-4B-Q4_0.gguf | Q4_0 | 2.5GB（2.40GiB，4.21B参数） | 298fcb5fe7a77ccc79745ae24751560c5ac56874caff4bb39b1f2055bd72b8bb |

## 正式基线 B1：厂商开箱版（llama.cpp 0.1.1 + Q4_0，2026-10-29）

口径：`-t 4 -fa 1 -mmp 0 -r 3`，pp64/pp512/tg128，轮间冷却60s，全程`monitor.sh`采样。
2B 三轮取中位、4B 两轮取中位。

| 模型 | pp64 (t/s) | pp512 (t/s) | tg128 (t/s) | 有效带宽 | 峰值可用内存 |
|---|---|---|---|---|---|
| Qwen3.5-2B Q4_0 | **11.24** | **10.84** | **2.84** | 3.41 GB/s（峰值32%） | 5642 MB |
| Qwen3.5-4B Q4_0 | **3.92** | **3.80** | **1.31** | 3.38 GB/s（峰值32%） | 4276 MB |

**原始五轮数据**（`results/stab_*.txt`）：

| 轮次 | 2B pp64 | 2B pp512 | 2B tg128 | 4B pp64 | 4B pp512 | 4B tg128 |
|---|---|---|---|---|---|---|
| t1 | 11.24 | 10.82 | 2.84 | 3.92 | 3.80 | 1.31 |
| t2 | 11.25 | 10.84 | 2.84 | 3.92 | 3.80 | 1.31 |
| t3 | 11.19 | 10.84 | 2.84 | — | — | — |

**测量质量与稳定性结论（可直接用于报告）**：
- 轮间性能漂移 <0.5%（2B pp64：11.24→11.25→11.19），单轮标准差 ±0.00~0.03 → **测量系统可信，可作为正式基线**
- 全部5轮期间 **cpu0/cpu4 恒定 1600MHz，无一次降频**；温度均值 52.8~56.0°C、峰值 ≤60°C
- 结论：**散热不是瓶颈，无需额外散热装置**；性能瓶颈完全在软件路径（旧版后端 + TCM接口错配）
- 4B 可用内存余量 4276MB，为 32K 长上下文（KV约1GB）留出足够空间
- 用户体验参考：4B tg=1.31 t/s ⇒ 生成100 token 约需 76 秒；pp512 需 135 秒 ⇒ 4B 的 prompt 必须控制在短文本


## 根因定位（2026-10-29结案）

**版本错配：llama.cpp 0.1.1 与 spacemit-tcm 3.0.0 接口不兼容。**

| 实测项 | 值 | 来源 |
|---|---|---|
| llama.cpp 包 | `llama.cpp-tools-spacemit 0.1.1-bpo1+6` | `dpkg -s` |
| 包维护者 | liudecheng <decheng.liu@spacemit.com> | **合规证据：确系进迭时空构建** |
| apt 候选版本 | 0.1.1-bpo1+6（与已安装相同，**源中无0.2.x**） | `apt-cache policy` |
| apt 源 | `archive.spacemit.com/bianbu bianbu-v2.3-updates/main` | 同上 |
| TCM 包 | `spacemit-tcm 3.0.0-bpo1+2` | `dpkg -l` |
| 系统暴露的TCM节点 | `/dev/tcm`（字符设备，0600 root:root） | `ls -l /dev/tcm*` |
| llama.cpp 索取的节点 | `/dev/tcm_sync_mem`（**不存在**）→ errno=2 | 运行日志 |

新版 TCM 驱动暴露 `/dev/tcm`，而 0.1.1 的 llama.cpp 硬编码打开旧接口 `/dev/tcm_sync_mem` → 申请失败回退堆内存 → IME 第二通道（`use_ime2:0`）无法启用 → prefill 仅为预期值约1/4。

**处置**：自编译 `spacemit-com/llama.cpp` v0.2.3（含新 `ggml-spacemit` 后端与 GDN 算子优化），装入 `~/cie/src/llama-install`，与 apt 版并存。**apt 0.1.1 保留作为「厂商开箱基线 B1」**，用于报告中"更换后端"这一项的可量化归因。

## 自编译 llama.cpp 构建配方（v0.2.3，2026-10-29）

官方文档：`docs/build-riscv64-spacemit.md`（spacemit-com/llama.cpp）

**关键点：`-DGGML_CPU_RISCV64_SPACEMIT` 已废弃**，新版必须用 `-DGGML_SPACEMIT=ON` 并配合 `SPERT_DIR`
指向 spine-runtime 解压目录（含 include/ 与 lib/）。两者不能同时开。

```bash
wget https://github.com/spacemit-com/spine-runtime/releases/download/0.6.3/spine-runtime.riscv64.0.6.3.tar.gz
tar xzf spine-runtime.riscv64.0.6.3.tar.gz
export SPERT_DIR=$PWD/spine-runtime.riscv64.0.6.3

cmake -B build -DCMAKE_BUILD_TYPE=Release \
  -DGGML_SPACEMIT=ON -DSPERT_DIR=${SPERT_DIR} \
  -DGGML_CPU_REPACK=OFF -DLLAMA_OPENSSL=OFF -DLLAMA_CURL=OFF \
  -DGGML_RVV=ON -DGGML_RV_ZVFH=ON -DGGML_RV_ZFH=ON \
  -DGGML_RV_ZICBOP=ON -DGGML_RV_ZIHINTPAUSE=ON -DGGML_RV_ZBA=ON \
  -DCMAKE_TOOLCHAIN_FILE=${PWD}/cmake/riscv64-spacemit-linux-gnu-gcc.cmake \
  -DCMAKE_INSTALL_PREFIX=$HOME/cie/src/llama-install
cmake --build build --parallel 4 --config Release
cmake --install build
```

**IME 规格实测（本机 GCC 13.3，CMake 探测结果）**：

| 探测项 | 结果 | 含义 |
|---|---|---|
| IME1（vmadot v2） | ✅ Success | IME1 内核可用 |
| VMADOTN | ✅ Success | — |
| VMADOT_S4 / S8（i4 点积） | ❌ Failed | IME2 不支持 |
| VFWMADOT_FP16 | ❌ Failed | IME2 不支持 |
| VPACK / VNPACK | ❌ Failed | IME2 不支持 |

→ 本机构建只能得到 `RISCV64_SPACEMIT_IME1`。官方检测逻辑要求 i4 vmadot + vpack/vnspack 同时具备才定义 IME2，且 GCC≥15 才会追加 `-march=..._xsmtvdotii`。
**注意**：`use_ime2: 0` 的根因是编译器缺少 IME2 指令支持，**不是 TCM 故障**（此前判断需修正）。若要 IME2 需用 SpacemiT 官方交叉工具链（v1.2.4，含 GCC15）在 x86 上交叉编译；但 K1 的 core arch id 为 `a03c`、K3 为 `a064`，K1 是否具备 IME2 硬件支持尚待验证，优先级低于先把 IME1 基线跑正。

## 转换管线（2026-10-29 验证通过）

源码：`spacemit-com/llama.cpp` v0.2.3（tarball方式获取，因github.com经代理返回502，
改用 `codeload.github.com/.../zip/refs/tags/v0.2.3`，40MB/6.6s）
转换环境：Windows x86_64 + Python 3.12.10 venv（torch 2.15.0 / transformers 5.21.1 / gguf 0.19.0）

```powershell
$CIE = "C:\Users\RX\Desktop\作业以及课程设计论文&GSR\CIE"
cd "$CIE\llama.cpp"
python convert_hf_to_gguf.py "$CIE\models\qwen3.5-2b" --outfile "$CIE\gguf\Qwen3.5-2B-f16.gguf" --outtype f16
python convert_hf_to_gguf.py "$CIE\models\qwen3.5-4b" --outfile "$CIE\gguf\Qwen3.5-4B-f16.gguf" --outtype f16
```

**f16中间产物校验**（`gguf.GGUFReader`读取）：

| 文件 | 架构 | 张量数 | ctx_length | 张量类型分布 | 体积 | 耗时 |
|---|---|---|---|---|---|---|
| Qwen3.5-2B-f16.gguf | `qwen35` | 335 | 262144 | F16×195, F32×140 | 3.89GB | 14s |
| Qwen3.5-4B-f16.gguf | `qwen35` | 441 | 262144 | F16×257, F32×184 | 8.65GB | 43s |

- `arch=qwen35` 与llama.cpp期望一致；`ctx=262144`与官方声明一致 → 转换正确
- F32张量为norm/bias等一维参数，保持高精度符合预期
- **注意**：Windows预编译`llama-quantize.exe`无法获取（github.com/objects.githubusercontent.com均502），
  量化改在K1上用`llama-quantize`执行（量化不依赖IME加速，旧版0.1.1可用）

## 模型chat template差异（影响测试口径）

- **2B**：`enable_thinking` 未定义 → 默认**关闭**思考，输出直答
- **4B**：`enable_thinking is false` 才输出空think块，否则 `<think>` → 默认**开启**思考

⇒ 质量测试与多轮测试必须显式统一：`--chat-template-kwargs '{"enable_thinking":false}'`，
否则4B会先生成大段思考内容，导致token数、时延、上下文占用与2B不可比。
（`llama-bench`不受影响，它不经过chat template）

## 量化策略对比（自产 vs 官方，2B，2026-10-30）

口径：`-t 4 -fa 1 -mmp 0 -r 3`，llama.cpp 0.1.1。

| 版本 | 格式 | 体积 | pp64 | pp512 | tg128 |
|---|---|---|---|---|---|
| 官方unsoth（B1基线） | Q4_0 | 1.12 GiB | 11.24 | 10.84 | **2.84** |
| **自产** | **Q4_K_M** | 1.29 GiB | 10.88 | 10.56 | **2.56** |
| 差值 | — | **+15.2%** | −3.2% | −2.6% | **−9.9%** |

**关键结论（反直觉，需写进报告）**：
反算有效带宽：Q4_0 = 1.2026GB×2.84 = **3.42 GB/s**；Q4_K_M = 1.3851GB×2.56 = **3.55 GB/s**（**+3.8%**）。

⇒ Q4_K_M 的**带宽效率其实略高**，但权重体积大 15%，净效果是 decode 慢 9.9%。
⇒ **在 K1 这种带宽受限平台上，decode 速度由权重体积主导，而非反量化开销**。
（此前猜测"K-quants 解包更重导致变慢"，被数据否证，需修正。）

**工程含义**：Q4_0 是 K1 上的速度最优选择；Q4_K_M 的价值在质量而非速度。二者应作为"质量-速度"权衡的两端同时提交。

## 转换链路踩坑记录（4个，均已解决）

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | `open(/dev/tcm_sync_mem) failed errno=2` | 运行时0.1.1与TCM驱动3.0.0接口不匹配 | 需升级至v0.2.3（或容忍回退堆内存） |
| 2 | `missing tensor 'blk.24.ssm_conv1d.weight'` | 转换器保留MTP层并计入block_count=25 | 剥离blk.24 |
| 3 | `wrong number of tensors; expected 335, got 320` | `nextn_predict_layers=1` 使加载器额外计1层 | 同步置0，并截断`attention.recurrent_layers` |
| 4 | `tensor 'token_embd.weight' has wrong shape` | 剥离脚本`raw_shape`传了ggml序，被写入器反转两次→二维张量转置 | 传`tuple(reversed(t.shape))` |

**校验方法**：每步都用`gguf.GGUFReader`核对 block_count / nextn / tensor数 / 张量形状，并抽查张量字节MD5。四个坑全部由"加载时报错或头部校验"发现，无一是靠猜。

## 运行时对比：0.1.1(legacy IME) vs v0.2.3(ggml-spacemit) （2026-10-30）

口径：2B，`-p 128 -n 64`，预热跳过，2次重复。新版参数为 `-fa on -lm none`。

| 运行时 | 线程 | 模型 | pp128 | tg64 | 备注 |
|---|---|---|---|---|---|
| 0.1.1 (legacy) | 4 | Q4_0 | 10.40* | 2.84* | 旧版甜点，*pp512/tg128口径 |
| 0.1.1 (legacy) | 4 | Q4_K_M | 10.56* | 2.56* | 同上 |
| 0.1.1 (legacy) | **8** | Q4_0 | 10.40 | **0.86** | **decode崩塌(-70%)** |
| 0.1.1 (legacy) | **8** | Q4_K_M | 10.06 | **0.83** | 同上 |
| v0.2.3 (spacemit) | 4 | Q4_K_M | 4.60~4.79 | 2.36~2.45 | 新后端 t4 严重欠线程 |
| v0.2.3 (spacemit) | **8** | Q4_K_M | 7.99 | 3.11(n16) | 新后端甜点 |
| v0.2.3 (spacemit) | 8 | Q4_0 | 5.00 | 2.86 | 新后端对Q4_0反而更差 |

**三条硬结论**：
1. **legacy后端 t>4 会让 decode 崩塌**（2.84→0.86，−70%），印证官方"K1 ≤4线程"的约束，且原因是TCM/IME争用而非核数不足。prefill 基本不受影响（10.40 vs 10.40）。
2. **新版 ggml-spacemit 后端在 K1 上 prefill 全面劣化**（最好 7.99，仍比 legacy t4 的 10.4 低 23%），decode 略优（3.11 vs 2.84）。推测其 prefill 优化路径依赖 IME2，而 K1 运行时报 `use_ime2=0`（arch_id a03c，K3 为 a064），硬件不支持 IME2。
3. **两代后端无全面胜者**：legacy 赢 prefill（考试20分的主战场），新版赢 decode。

**最优组合建议**：
- prefill/长上下文优先 → **0.1.1 + Q4_0 + t4**（pp 10.4~10.8）
- decode 优先 → **v0.2.3 + Q4_K_M + t8**（tg 3.1）
- v0.2.3 的独立价值：其 `llama-quantize` 有小张量回退逻辑，**能产出 0.1.1 产不出的 Q4_0**，用于闭环"自产量化"

## 核心发现：自产量化 vs 官方GGUF（2026-10-30，+87.8% prefill）

**同一运行时（apt 0.1.1）、同一台机器、同一量化格式（Q4_0）、同一口径，唯一变量是"谁量化的"。**

| 文件 | 体积 | pp64 | pp512 | tg128 | 备注 |
|---|---|---|---|---|---|
| 官方 unsloth `Qwen3.5-2B-Q4_0.gguf` | 1.12 GiB | 11.24 | 10.84 | 2.84 | 下载成品 |
| **自产 `Qwen3.5-2B-Q4_0-self.gguf`** | 1.22 GiB | **21.08** | **20.36** | 2.80 | 新版quantize(F16回退)+embedding Q8_0 |
| 变化 | +8.9% | **+87.5%** | **+87.8%** | −1.4% | 3次重复，σ=±0.03~0.08 |

**为何这个反差就是线索**：体积大了 8.9%，prefill 却快 88%。若差异来自算力或带宽，prefill 应当**下降**。实则上升近一倍 ⇒ 走的是完全不同的代码路径。

**机制假设（待验证）**：prefill 每轮处理 512 token、decode 每轮 1 token，只有"按 token 数放大"的开销才会产生这种差异——即每层每 token 执行一次的小算子。最可能是 GDN 层的 `ssm_alpha`（仅16列）/`ssm_conv1d`/`ssm_norm`：官方 GGUF 将其压成 Q4_0，而 Q4_0 量化块为32列，16列张量装不进去，旧后端只能走逐元素反量化的退化路径；18个GDN层×512 token 使开销放大数百倍。自产文件因新版 quantize 的 **F16 回退**保留了这些小张量，直接命中快速路径。
（验证受限于 K1 解析 GGUF tokenizer 数组过慢，单文件>11分钟未完成，暂缓。）

**项目含义（报告主结论）**：
官方推荐的 GGUF 在 K1 上被其自身的量化选择拖累，prefill 仅 10.84 t/s。自建转换量化管线（F16回退 + embedding Q8_0）在**相同运行时与硬件**上把 prefill 提升至 20.36 t/s（**+87.8%**），decode 持平。
⇒ 单一变量、归因干净的优化，同时覆盖「Prefill性能(20分)」「转换量化(5分)」「可量化优化(10分)」三项。

## 待补全项（P0出口门前必须填齐）

- [x] 刷机后：Bianbu 2.3.5 / 内核6.6.63 / LXQt / isa含v+ime（2026-10-28实测）
- [x] llama.cpp 包版本 0.1.1-bpo1+6（维护者@spacemit.com）、spacemit-tcm 3.0.0-bpo1+2
- [ ] 自编译 llama.cpp 的 tag + commit（`git rev-parse HEAD`）
- [ ] Qwen3.5-2B/4B原始权重：来源URL + 每个文件的sha256
- [ ] 自产GGUF产物：量化参数 + sha256
- [ ] spacemit-com/llama.cpp：tag（v0.2.3）+ commit
- [ ] ggml-org/llama.cpp（B0基线）：commit
