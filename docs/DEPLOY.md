# 模型转换与部署说明

> 适用对象：需要在进迭时空 K1（RISC-V，8 GB）上复现本项目的人类或自动化流程。
> 目标：从**官方原始权重**出发，自行产出量化 GGUF，并部署为可用的本地推理服务。
> 配套文档：优化策略与全部测试数据见 [`技术文档.md`](技术文档.md)；TCM 改造见 [`PATCH_TCM.md`](PATCH_TCM.md)；版本与校验值见 [`VERSIONS.md`](VERSIONS.md)。

---

## 0. 一页速览

| 阶段 | 在哪台机器 | 命令 | 参考耗时 |
|---|---|---|---|
| 1. 下载官方权重 | x86（≥16 GB 内存 / ≥60 GB 磁盘） | `00_fetch_models.sh` | 20~60 min（网速决定） |
| 2. 转 f16 GGUF | x86 | `01_convert.sh` | 2B 约 15 s / 4B 约 1~3 min |
| 3. 剥离 MTP 层 | 任一（建议 x86） | `02_strip_mtp.sh` | 2B 约 1 min / 4B 约 2~5 min |
| 4. 构建量化器 | **Linux/WSL**（需 g++、cmake） | `04_build_quantizer.sh` | 1~3 min（仅单一目标） |
| 5. 量化 | 任一 | `03_quantize.sh` | 2B 约 1 min / 4B 约 1~3 min |
| 6. 部署验证 | K1 | `deploy.sh full` | 30 s |

**为什么必须分两台机器**：4B 的原始权重 8.4 GB，`convert_hf_to_gguf.py` 峰值内存约 1.5 倍（≈12 GB），而 K1 可用内存仅 6.4 GB —— 必然 OOM。K1 只承担推理与测量。

**为什么需要第 4 步**：`03_quantize.sh` 必须用 **v0.2.3** 的 `llama-quantize`。apt 提供的 0.1.1 遇到 16 列的小张量（`ssm_alpha`）直接失败：

```
warning: blk.0.ssm_alpha.weight - ncols 16 not divisible by 32 (required for type q4_0)
llama_model_quantize: failed to quantize: no tensor type fallback is defined for type q4_0
```

v0.2.3 具备"装不下的张量回退为 F16"的逻辑，这正是本方案能产出可用 Q4_0 的前提。

> **常见疑问：为什么量化器是 0.2.3，跑模型的却是 0.1.1？**
> 因为这是两个独立程序，职责不同：
> - **生产端**（`llama-quantize`，只跑一次）：用 v0.2.3，因为它能处理小张量；0.1.1 做不到。
> - **消费端**（`llama-cli` / `llama-bench`，每次运行）：用 0.1.1，因为它在 K1 上 prefill 最快；v0.2.3 的新后端依赖 IME2，K1 不支持，实测反低 23%。
>
> GGUF 是文件格式标准，任何支持 GGUF V3 的运行时都能读，不存在"必须同版本"的约束。
> 更关键的是：本项目"自产 Q4_0 快 87.8%"的对比，**两个文件都是在同一个 0.1.1 上测的**——唯一变量是文件本身，
> 所以版本与文件没有混淆。详见 `技术文档.md` §5.1。

---

## 1. 环境准备

### 1.1 K1 侧

| 项 | 要求 | 验证命令 |
|---|---|---|
| 系统 | Bianbu 2.3.x LXQt（K1 专用镜像） | `cat /etc/os-release` |
| 内核 | 含 SpacemiT 补丁（IME/TCM 依赖） | `uname -r` |
| CPU 扩展 | 必须含 `v`（RVV）与 `ime` | `grep isa /proc/cpuinfo \| head -1` |
| 内存 | 8 GB（实测 7.7 GiB 可用） | `free -h` |
| 磁盘 | ≥10 GB 空闲 | `df -h ~` |
| 依赖包 | `llama.cpp-tools-spacemit`、`spacemit-tcm` | `dpkg -l \| grep spacemit` |

```bash
sudo apt update
sudo apt install -y llama.cpp-tools-spacemit spacemit-tcm
```

> **不要更换系统**。`llama.cpp-tools-spacemit` / `spacemit-tcm` 只存在于 Bianbu 的 apt 源；换成通用 Ubuntu 会同时失去 IME 加速路径与 K1 的 cpufreq/thermal 内核补丁，性能与稳定性都不可控（详见 `技术文档.md` §2.3）。

### 1.2 x86 侧

```bash
# Python 环境（版本 3.10~3.12 均可；不建议 3.13+，torch 轮子可能缺失）
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -U pip
pip install torch transformers gguf safetensors sentencepiece numpy
pip install modelscope                                  # 仅 00_fetch 需要

# 拉取 llama.cpp v0.2.3 源码（转换脚本在其中）
curl -L -o /tmp/llama023.zip \
  https://codeload.github.com/spacemit-com/llama.cpp/zip/refs/tags/v0.2.3
unzip -q /tmp/llama023.zip -d /tmp && mv /tmp/llama.cpp-0.2.3 ./llama.cpp
```

> `git clone https://github.com/...` 在受限网络下可能失败；`codeload.github.com` 通常可用，可用性更高。

### 1.3 目录约定

脚本统一以 `CIE_HOME` 为根（默认 `$PWD` / `~/cie`）：

```
$CIE_HOME/
├── models/     原始权重（qwen3.5-2b/、qwen3.5-4b/）与最终 GGUF
├── gguf/       转换中间产物（f16、nomtp）
├── llama.cpp/  v0.2.3 源码（提供 convert_hf_to_gguf.py）
├── src/llama023/bin/llama-quantize   第 4 步产物
├── tools/      运行期脚本
└── results/    测量输出
```

搬家只需 `export CIE_HOME=/新路径`，不必改脚本。

---

## 2. 转换流程（x86）

### 2.1 下载官方权重

```bash
bash scripts/00_fetch_models.sh 2b     # 约 4.6 GB
bash scripts/00_fetch_models.sh 4b     # 约 8.4 GB
```

**仓库名是 `Qwen/Qwen3.5-2B` 与 `Qwen/Qwen3.5-4B`，不存在 `-Instruct` 后缀**——赛题所称 "Instruct" 指后训练权重本身，不是仓库名的一部分。另注意别下成 `Qwen3.5-2B-Base`（基座模型）。

下完立刻记录校验值（可复现性的第一环）：

```bash
sha256sum models/qwen3.5-2b/*.safetensors > docs/hash_2b_raw.txt
```

### 2.2 转 f16 GGUF

```bash
bash scripts/01_convert.sh 2b     # → gguf/Qwen3.5-2B-f16.gguf
bash scripts/01_convert.sh 4b     # → gguf/Qwen3.5-4B-f16.gguf
```

脚本自带产物校验：架构必须是 `qwen35`，上下文长度 `262144`，张量数 2B=335 / 4B=441（含 MTP 层）。

### 2.3 剥离 MTP 层（**不可跳过**）

Qwen3.5 权重内置 MTP（multi-token prediction）模块，官方转换器会把它当作额外一层写入，`block_count` 因此多 1（2B 写 25、4B 写 33）。而运行时不支持 MTP，加载时报：

```
error loading model: missing tensor 'blk.24.ssm_conv1d.weight'
```

即使把 `block_count` 改回 24 仍会失败，因为加载器按 `block_count + nextn_predict_layers` 计算期望张量数：

```
done_getting_tensors: wrong number of tensors; expected 335, got 320
```

所以必须把 **3 个元数据键**一起改：`block_count`、`nextn_predict_layers`、`attention.recurrent_layers`（后者是长度 = 层数的布尔数组，需同步截断一位）。

```bash
bash scripts/02_strip_mtp.sh                      # 处理 gguf/ 下全部 f16
# 或指定文件
python3 tools/strip_mtp.py in-f16.gguf out-f16-nomtp.gguf
```

**成功判据**（脚本会自动打印并校验）：

```
校验: block_count=24, nextn=0, recurrent_layers=24, tensors=320, 残留MTP=0
结果: OK
```

4B 应对应 `block_count=32 / tensors=426`。

> 实现要点：`gguf.GGUFWriter.add_tensor()` 的 `raw_shape` 参数期望 **numpy 顺序（维数倒序）**。若传入 ggml 顺序会被再倒一次，导致全部二维张量转置，加载时报 `tensor 'token_embd.weight' has wrong shape; expected 2048, 248320, got 248320, 2048`。`tools/strip_mtp.py` 已处理并附带形状与字节级校验。

### 2.4 构建量化器（v0.2.3）

```bash
bash scripts/04_build_quantizer.sh            # 本机（x86）构建，推荐
bash scripts/04_build_quantizer.sh riscv      # 交叉编译为 riscv64（需 RISCV_ROOT_PATH）
bash scripts/04_build_quantizer.sh check      # 只检查现状
```

脚本刻意关闭 `GGML_SPACEMIT`：**量化是纯 CPU 数学运算，不经过 IME/TCM**，关掉可完全绕开 SPERT 运行时依赖。产物只用于量化，不要拿它跑性能基准。

产物：`$CIE_HOME/src/llama023/bin/llama-quantize`。

### 2.5 量化

```bash
bash scripts/03_quantize.sh gguf/Qwen3.5-2B-f16-nomtp.gguf Q4_0
# 或一次产出两套
bash scripts/03_quantize.sh gguf/Qwen3.5-2B-f16-nomtp.gguf all
```

固定使用 `--token-embedding-type q8_0`：embedding 量化到 q8 是精度与体积的折中，压到 q4 会明显损质量。

### 2.6 产物校验（**必做**）

```bash
python3 tools/gguf_types.py <产物.gguf>
```

必须同时满足三项：

| 检查项 | 期望值 | 不符的后果 |
|---|---|---|
| `block_count` | 2B=24 / 4B=32 | 加载报 `missing tensor` 或张量数不符 |
| `nextn_predict_layers` | 0 | 期望张量数多 15 个 |
| 张量类型分布 | **全部 Q4_0**（`token_embd` 为 Q8_0） | 混入 Q5_K/Q6_K 会掉出 IME 白名单，prefill 掉到 1/2 甚至 1/7 |

`tools/gguf_types.py` 是极简二进制解析器（mmap + 偏移跳转），**秒级**完成；相比 `gguf-py` 在 K1 上解析 24.8 万条词表字符串需十几分钟，这个工具在排查时几乎是必需的。

> **复现判定标准（重要）**：同一构建内量化是**完全确定性**的，重复执行 sha256 不变。
> 但**跨架构不必要求 sha256 相同**——实测 x86-64 与 riscv64 两个构建产出的文件，
> 体积逐字节相同（1,325,654,048 B）、张量数与类型分布相同、首段/中段抽样数据块相同，
> 仅末段约 1 MiB（0.08%）因浮点量化尺度的计算路径不同而有差异。
> 因此跨架构复现应判"体积 + 张量数 + 类型分布 + 抽样块"，而不是 sha256 全等。

---

## 3. 部署到 K1

### 3.1 传输

```bash
scp <产物>.gguf a@<K1-IP>:~/cie/models/
```

传完核对体积（Q4_0：2B 约 1.2 GB、4B 约 2.5 GB）。半传的文件会在加载时报 `failed to read tensor`。

### 3.2 一键部署

```bash
sudo apt install -y git          # 若无
git clone https://github.com/Rxlls/k1-qwen35-opt ~/cie-repo
cp -r ~/cie-repo/scripts ~/cie-repo/tools ~/cie-repo/configs ~/cie/

bash ~/cie/tools/deploy.sh full      # 装依赖 → 环境检查 → 模型校验 → 冒烟
bash ~/cie/tools/deploy.sh check     # 仅环境检查（只读，可随时跑）
bash ~/cie/tools/deploy.sh models    # 仅模型校验
bash ~/cie/tools/deploy.sh smoke     # 仅冒烟
```

`check` 覆盖 10 项：架构、RVV、IME、内存、磁盘、系统版本、内核、两个依赖包、TCM 设备节点。

若模型文件名与默认不同，用环境变量指定，脚本也会自动匹配 `Qwen3.5-2B-*.gguf`（优先选 Q4_0 成品、自动排除 `-f16` / `-nomtp` 中间产物）：

```bash
MODEL_2B=我的模型.gguf bash ~/cie/tools/deploy.sh models
```

### 3.3 手工验证（与脚本等价）

```bash
llama-cli -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf \
  -p "你好" -n 8 -c 2048 -t 4 -st --no-mmap
```

**`-t 4` 不可省**，理由见 §5.1。

---

## 4. 运行

```bash
# 单轮
llama-cli -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -c 4096 -st --no-mmap

# 交互对话（4B 默认开启思考模式，必须显式关闭，否则输出被 <think> 占满）
llama-cli -m ~/cie/models/Qwen3.5-4B-Q4_0-self.gguf -t 4 -c 4096 -cnv \
  --chat-template-kwargs '{"enable_thinking":false}'

# HTTP 服务
llama-server -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -c 8192 \
  --host 127.0.0.1 --port 8080 --metrics

# 基准（口径固定，勿改）
bash ~/cie/tools/bench_quick.sh Qwen3.5-2B-Q4_0-self.gguf my_tag
```

### 4.1 参数速查

| 参数 | 必须值 | 说明 |
|---|---|---|
| `-t` | **4** | 不指定会崩溃（§5.1） |
| `-fa` | `1`（bench）/ `on`（v0.2.3） | FlashAttention，长上下文必需 |
| `-mmp` | `0`（v0.2.3 起改为 `-lm none`） | 关 mmap，避免页缺失干扰测量 |
| `-c` | 2048~32768 | 32K 实测峰值内存 2B=1.74 GB / 4B=3.57 GB |
| `--chat-template-kwargs` | `{"enable_thinking":false}` | 仅 `llama-cli -cnv` / `llama-server` 需要；`llama-bench` 不走模板，无需 |

---

## 5. 故障排查

### 5.1 `thread_n N exceeds perfer_core_ids size 4` → 核心转储

```
ggml/src/ggml-cpu/spacemit/ime.cpp:1704:
  thread_n 7 exceeds perfer_core_ids size 4
（core dumped）
```

**原因**：spacemit 后端只为 Cluster 0 登记 4 个 preferred core（`num_perfer_cores=4`），`set_numa_thread_affinity()` 对 `thread_id ≥ 4` 直接 `ggml_abort`。而 `llama-cli` 默认线程数 = `hardware_concurrency()` = 8。

**修复**：显式传 `-t 4`。注意这与 `llama-bench -t 8` 不同——bench 不走绑核路径，只是变慢（decode −70%），不会崩。

### 5.2 `alloc_chunk: open(/dev/tcm_sync_mem) failed, errno=2`

**原因**：0.1.1 硬编码 `/dev/tcm_sync_mem`，而新版驱动只提供 `/dev/tcm`。

**影响**：TCM 退回堆内存，`use_ime2` 无法启用。实测**对吞吐无显著影响**（详见 `PATCH_TCM.md` §10.5），可忽略；若要修，打 `patches/0001-tcm-dev-path.patch` 并重新交叉编译。

### 5.3 `open(/dev/tcm) failed, errno=13` 与「不要随意放开 TCM 权限」

**现象**：`/dev/tcm` 权限为 `crw------- root:root`，普通用户打不开，报 `errno=13`（EACCES）。

**先别急着 chmod。** 实测（2B，同一二进制 0.1.1，`-t 4 -p 512 -n 64 -fa 1`）：

| `/dev/tcm` 权限 | 运行时 | pp512 | 说明 |
|---|---|---|---|
| `600`（出厂默认） | apt 原版 0.1.1 | **20.36** | 打不开 → 纯堆内存 → **最快** |
| `666`（放开） | apt 原版 0.1.1 | **12.72** | 能打开但拿不到同步块 → **慢 38%** |
| `666` | 打了 TCM patch 的 0.1.1 | **20.36** | 完整 TCM，与堆内存持平 |

**机制**：未打补丁的 0.1.1 只认 `/dev/tcm_sync_mem`。权限放开后，它**能**打开 `/dev/tcm` 并打印
`tcm is available, blk_size: 131072, blk_num: 4, is_fake_tcm: 0`，但取不到同步块，仍打印
`alloc_chunk: open(/dev/tcm_sync_mem) failed` 并 `falling back to heap`。
这个"**半可用**"状态反而比"完全不可用"慢得多——TCM 被映射了却无法同步，形成额外的串行开销。

**结论**：

- 使用 **apt 原版 0.1.1**（本项目基线）：保持 `/dev/tcm` 为 `600`，**不要 chmod**。
  `falling back to heap` 是预期且最优的行为，`errno=13` 也不会出现（因为它根本不打开 `/dev/tcm`）。
- 使用 **打了 TCM patch 的版本**：`600` 下同样能正常跑（实测 `rc=0`，同模型同参数 3.0 t/s，与堆内存持平），
  只有想验证"TCM 是否真的分配上了"时才需要 `sudo chmod 666 /dev/tcm`（重启失效）或 udev 规则持久化：

  ```bash
  echo 'KERNEL=="tcm", MODE="0666"' | sudo tee /etc/udev/rules.d/99-tcm.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger
  ```

**另一个坑：TCM 是独占资源。** 一个进程（哪怕卡死的）持有 `/dev/tcm` 时，后续进程拿不到，性能同样退化。
基准测试前确认无残留：

```bash
fuser /dev/tcm          # 有输出说明被占用
pkill -9 -f "llama[-]bench"   # 注意方括号：避免 pkill 匹配到自己
```

### 5.4 转换/加载阶段的四类报错

| 报错 | 根因 | 修复 |
|---|---|---|
| `missing tensor 'blk.24.ssm_conv1d.weight'` | MTP 层被当作第 25 层 | 执行 `02_strip_mtp.sh` |
| `wrong number of tensors; expected 335, got 320` | 只改了 `block_count`，`nextn_predict_layers` 仍为 1 | 用 `strip_mtp.py`（会同时改 3 个键） |
| `tensor 'token_embd.weight' has wrong shape` | 写 GGUF 时形状被转置 | 用仓库内的 `strip_mtp.py`（已修正 `raw_shape` 顺序） |
| `ncols 16 not divisible by 32` | 用了 0.1.1 的量化器 | 执行 `04_build_quantizer.sh` 换 v0.2.3 |

### 5.5 加载正常但速度只有预期 1/3 ~ 1/7

**先看温度**——但**必须选对传感器**，`thermal_zone0` 不是 SoC：

```bash
for z in /sys/class/thermal/thermal_zone*; do
  printf '%-28s %s\n' "$(cat $z/type)" "$(cat $z/temp)"
done
```

本机实测（2026-11-01）：

| 节点 | type | 读数 | 说明 |
|---|---|---|---|
| `thermal_zone0` | `sbs-5-000b` | 28800（恒定） | **电池电量计**，与 CPU 无关，不能用来判断 |
| `thermal_zone1` | `cluster0_thermal` | 44000 空闲 → 53000 满载 | **Cluster 0（带 IME 的 4 核）**，看这个 |
| `thermal_zone2` | `cluster1_thermal` | 同步跟随 | Cluster 1 |

**判据本身要按机器的空闲基线校准**。同一台机器实测：

| 场景 | cluster0_thermal 峰值（满载 90 s 内取 max） |
|---|---|
| 空闲 | 44.0 °C |
| 跑 Q4_0（命中 IME） | 53.0 °C |
| 跑 Q4_K_M（不在白名单） | 53.0 °C |

⇒ **温度不足以区分两条路径**：两者满载都会升到 53 °C 左右，差值在噪声内。
早期的"≥55 °C / 31~32 °C"二分法来自采样时机不同的两次记录（慢的那次在升温前就取了数），不要照抄。

**可靠的判据是数字本身**：直接看 `llama-bench -p 512 -n 128` 的 pp512——2B 上 ≥18 t/s 说明命中 IME，
≈10.5 t/s 说明掉出白名单；或者直接查量化类型（`tools/gguf_types.py`），这是根因，不是结果。
温度只适合做"有没有真的在算"的粗查（满载却几乎不发热 → 多半卡在等锁或已退出）。

掉出白名单的典型原因：量化类型为 `Q5_K` / `Q6_K` / `Q8_0`（KV 也一样），或使用了混合精度 GGUF。本项目实测：官方 unsloth GGUF 文件名为 Q4_0，实际混用 Q5_K/Q6_K/Q8_0，prefill 因此只有自产统一 Q4_0 的 53%。

### 5.6 模型能加载但输出乱码 / 重复

几乎都是转换链某步被跳过。按 §2.6 三项校验逐条核对，不要凭"能跑"判断正确性。

### 5.7 冒烟测试报 `timeout: 被监视的命令已核心转储`

**现象**：`deploy.sh` 走到冒烟测试，末尾三行是

```
CPU_RISCV64_SPACEMIT: alloc_chunk: open(/dev/tcm) failed, errno=13
CPU_RISCV64_SPACEMIT: failed to allocate init_barrier from shared mem, falling back to heap
timeout: 被监视的命令已核心转储
```

**判读顺序（别先怀疑 TCM 权限）**：

1. `errno=13` 与 `falling back to heap` 都是**预期现象**，不是失败原因（见 §5.3）。原版 0.1.1 在这里会报 `errno=2`，同样是预期。
2. `核心转储` 说明进程被信号打死。`deploy.sh` 会把子进程退出码翻译成信号名：`139=SIGSEGV`（多为动态库混用）、`134=SIGABRT`（线程数超 `perfer_core_ids`）、`132=SIGILL`。
3. 最常见的根因是**动态库混用**：shell 里残留了别的构建的 `LD_LIBRARY_PATH`，或 `PATH` 里的 `llama-cli` 与 `ldd` 解析出的 lib 不是同一次编译的产物（§10.3 记过同类坑）。

**定位三行**：

```bash
echo "[$LD_LIBRARY_PATH]"                                  # 有没有残留
command -v llama-cli
ldd "$(command -v llama-cli)" | grep -E 'llama|ggml'       # 每行都应指向同一目录
bash ~/cie/tools/deploy.sh smoke                           # 新版会打印「二进制:」「动态库:」两行
```

`deploy.sh` 的二进制择序是 `LLAMA_CLI` > `/usr/bin/llama-cli`（apt 原版，项目基线）> `PATH`，
默认避开自建产物的库路径问题；要用自建版就显式指定：

```bash
LLAMA_CLI=$HOME/cie/src/llama011/bin/llama-cli \
LD_LIBRARY_PATH=$HOME/cie/src/llama011/lib \
  bash ~/cie/tools/deploy.sh smoke
```

**2026-11-01 实测基线**（同机、同模型，`-p 你好 -n 8 -c 2048 -t 4 -st --no-mmap`）：

| 配置 | 结果 |
|---|---|
| `/usr/bin/llama-cli`（apt 原版，`LD_LIBRARY_PATH` 为空） | `rc=0`，Prompt 10.4 t/s，Generation 3.1 t/s |
| 自建 patch 版 + 自建 lib，`/dev/tcm` 仍为 `600` | `rc=0`，Generation 3.0 t/s（同样回退堆内存） |

两条路径都能正常出字 → 若出现 core dump，问题在**当次 shell 的环境态**，与模型文件、TCM patch、`/dev/tcm` 权限均无关。
换一个干净 shell（`env -u LD_LIBRARY_PATH bash ~/cie/tools/deploy.sh smoke`）即可验证。

### 5.8 冒烟测试在桌面终端里"明明出字却判失败"

**现象**：在桌面终端（qterminal / tmux）里跑 `deploy.sh`，冒烟环节屏幕上明明打印了
`[ Prompt: 11.6 t/s | Generation: 3.1 t/s ]` 和 `Exiting...`，脚本却报
`[FAIL] 正常` → `冒烟失败（3 种组合均未出字）`，最终 `通过 13 项，失败 1 项`；
同一个脚本用 `ssh host 'bash deploy.sh'` 跑却是 14/14。

**根因**：llama.cpp 的 console 在**存在控制终端**时会直接写 `/dev/tty`，
绕过 `$(...)` 命令替换建立的管道。于是：

- 屏幕上：输出正常（走的是 tty）
- `SMOKE_OUT` 变量：空字符串
- 判定：`grep -qiE 'Generation:|Exiting'` 不中 → 判失败，但退出码其实是 0

所以日志里会出现自相矛盾的 `[FAIL] 正常`（"正常"是 `rc_desc 0` 的翻译）。

**三种运行方式的结果**：

| 运行方式 | 有无控制终端 | 冒烟判定 |
|---|---|---|
| 桌面终端 / tmux / 脚本内的 `$(...)` | 有 | 屏幕有字，变量为空 → **误判失败** |
| `ssh host 'bash deploy.sh'` | 无 | 正常捕获 → 14/14 |
| 桌面终端 + `setsid` | 无（已脱离） | 正常捕获 → 14/14 |

**修复**（2026-11-01，`run_smoke` 内已加）：

```bash
local pre=""; command -v setsid >/dev/null 2>&1 && pre="setsid"
SMOKE_OUT=$(timeout 180 $pre "$bin" ... </dev/null 2>&1)
```

`setsid` 让子进程脱离控制终端，`/dev/tty` 不可用后 console 回落到 stdout；`</dev/null` 顺手关掉 stdin。
**凡是"在脚本里用 `$(...)` 包 llama-cli/llama-bench"的场合都应照此办理**，否则捕获会静默为空。

---

## 6. 复现性记录

提交/交付时至少保留以下四项：

```bash
cat /etc/os-release | head -3        # 系统版本
uname -r                             # 内核
dpkg -l | grep -E 'llama|spacemit-tcm'   # 运行时版本
sha256sum models/*.gguf              # 产物校验值
```

本项目的实测值见 `docs/VERSIONS.md`。

---

## 7. 已知边界（本方案不解决的问题）

| 边界 | 数值 | 说明 |
|---|---|---|
| decode 带宽天花板 | 有效带宽 3.4 GB/s ≈ 峰值 32% | 2B 实测 tg 2.80 t/s，未优化内存访问效率 |
| 长 prompt 首字延迟 | 1200 token ≈ 62 s | 长文档问答不可用 |
| KV cache 量化 | 不可行 | q8_0 使注意力路径掉出 IME，31 min 未完成（f16 仅 17.9 min） |
| 4B 在 256K 上下文 | 内存不足 | 32K 峰值 3.57 GB，外推 256K 需约 10.5 GB > 8 GB |
| IME2 指令 | 不可用 | K1 的 X60 不支持，运行时报 `use_ime2=0` |
