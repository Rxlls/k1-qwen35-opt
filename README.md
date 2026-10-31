# k1-qwen35-opt

在进迭时空 K1 笔记本（RISC-V，8GB 内存）上部署并优化 Qwen3.5-2B / 4B 的本地推理。
基于进迭时空开源 llama.cpp，构建从官方原始权重到量化 GGUF 的完整可复现管线。

**核心结果：在不改动硬件与运行时的前提下，仅通过自建量化管线替换官方预置 GGUF，prefill 吞吐提升 87.8%（2B）/ 113.2%（4B）。**

> **主线运行时固定为 `llama.cpp-tools-spacemit` 0.1.1**（Bianbu 官方源版本，K1 上 prefill 最快）。
> 自编译的 v0.2.3 仅作对照：其在 K1 上缺 IME2，实测 prefill 比 0.1.1 低 23%~75%，故不采用；
> 同一组文件在 v0.2.3 上只提升 5.6%——收益的适用范围与原因见 [技术文档 §8.8](docs/技术文档.md)。

| 指标 | 官方 GGUF Q4_0 | 自产 Q4_0 | 变化 |
|---|---|---|---|
| 2B pp64 | 11.24 t/s | **21.08 t/s** | +87.5% |
| 2B pp512 | 10.84 t/s | **20.36 t/s** | **+87.8%** |
| 2B tg128 | 2.84 t/s | 2.80 t/s | -1.4% |
| 4B pp64 | 3.94 t/s | **8.93 t/s** | +126.6% |
| 4B pp512 | 3.80 t/s | **8.10 t/s** | **+113.2%** |
| 4B tg128 | 1.32 t/s | **1.43 t/s** | +8.3% |

---

## 一句话原理

官方 GGUF 采用 unsloth Dynamic 混合精度，文件名叫 Q4_0，实际混用 `Q5_K` / `Q6_K` / `Q8_0` / `Q4_1`。
而 K1 的 IME 加速白名单只认 `Q4_K_M` / `Q4_0` / `Q4_1` / `Q2_K` / `Q3_K`。
落在白名单外的张量（其中 18 个 `ssm_out` 属于 GDN 层，prefill 时每个 token 都要算）整体退化为通用标量路径。

**这不是调参问题，是量化类型的二元判定。**

## 硬件与软件环境

| 项 | 规格 |
|---|---|
| 设备 | 进迭时空 K1 笔记本（MUSE Book 类） |
| CPU | 8 × X60 @ 1.6 GHz，含 RVV 1.0、Zvfh、**IME** 扩展 |
| 内存 | 8 GB LPDDR4x-2666（有效带宽 10.6 GB/s） |
| 系统 | Bianbu 2.3.5 LXQt，内核 6.6.63 |
| 运行时 | `llama.cpp-tools-spacemit` 0.1.1（build `17ce6aa`） |
| 模型 | `Qwen/Qwen3.5-2B`、`Qwen/Qwen3.5-4B`（官方后训练权重） |

## 目录结构

```
.
├── docs/
│   ├── 方案书.md            方案书（含开发计划、预期成果、应用价值）
│   ├── 技术文档.md          技术文档（优化策略、测试报告、完整数据）
│   ├── DEPLOY.md            模型转换与部署说明（含故障排查手册）
│   ├── PATCH_TCM.md         框架改造设计说明 + 实施与验证记录
│   ├── DEFENSE.md           答辩提纲
│   ├── PLANNING.md          启动阶段计划（保留以记录判断与修正）
│   └── VERSIONS.md          环境与产物版本档案
├── scripts/                 全流程脚本（按序号执行）
│   ├── 00_fetch_models.sh   下载官方原始权重（x86）
│   ├── 01_convert.sh        HF → f16 GGUF
│   ├── 02_strip_mtp.sh      剥离 MTP 层 + 修正 3 个元数据键
│   ├── 03_quantize.sh       f16 → Q4_0 / Q4_K_M
│   ├── 04_build_quantizer.sh 构建 v0.2.3 量化器（03 的前置）
│   ├── deploy.sh            K1 一键部署验证（all/full/check/deps/models/smoke）
│   └── build_patched_011.sh 交叉编译带 TCM 修复的 0.1.1
├── tools/
│   ├── collect_env.sh       环境快照 + TCM 诊断
│   ├── monitor.sh           频率/温度/内存 1Hz 采样
│   ├── bench_quick.sh       标准基准封装（口径固化）
│   ├── strip_mtp.py         MTP 剥离核心实现
│   ├── gguf_types.py        极简 GGUF 解析器（秒级读张量类型）
│   ├── quality_v2.sh        质量测试（关闭思考模式）
│   ├── quality_prompts.txt  20 题固定测试集
│   └── ...
├── configs/                 推荐参数与实测基线
├── patches/                 框架改造补丁
├── results/                 全部原始测量数据与评审记录
├── vendor/                  第三方预编译依赖（spine-runtime，仅 v0.2.3 构建用）
├── LICENSE                  MIT
└── README.md
```

> 赛题原文（主办方文件）不随仓库分发；构建产物与模型权重大于仓库容量上限，均由脚本重新生成。

## 快速开始

### 只验证环境（K1，30 秒）

```bash
bash scripts/deploy.sh check
```

输出架构、RVV/IME 扩展、内存、磁盘、依赖包、TCM 节点共 10 项检查。

### 完整复现（x86 + K1）

```bash
# 1. 下载官方权重（x86，需 ≥16GB 内存与 60GB 磁盘）
bash scripts/00_fetch_models.sh 2b

# 2. 转换为 f16 GGUF
bash scripts/01_convert.sh 2b

# 3. 剥离 MTP 层（运行时不支持 MTP，必须做）
bash scripts/02_strip_mtp.sh

# 4. 构建量化器（v0.2.3；apt 的 0.1.1 无法处理 16 列小张量）
bash scripts/04_build_quantizer.sh

# 5. 量化
bash scripts/03_quantize.sh gguf/Qwen3.5-2B-f16-nomtp.gguf Q4_0

# 6. 校验产物（block_count=24 / nextn=0 / 全 Q4_0，三项必须同时满足）
python3 tools/gguf_types.py gguf/Qwen3.5-2B-Q4_0.gguf

# 7. 拷到 K1 → 一键部署验证 → 跑基准
scp gguf/Qwen3.5-2B-Q4_0.gguf <K1>:~/cie/models/
bash ~/cie/tools/deploy.sh full
bash ~/cie/tools/bench_quick.sh Qwen3.5-2B-Q4_0.gguf my_tag
```

逐步说明、参数含义与**故障排查手册**见 [`docs/DEPLOY.md`](docs/DEPLOY.md)。

### 一键基准（K1，已有模型时）

```bash
bash tools/bench_quick.sh Qwen3.5-2B-Q4_0-self.gguf 2b_q4self
# 固定口径：-t 4 -fa 1 -mmp 0 -r 3
```

## 关键发现

1. **量化类型是二元判定，不是体积梯度**
   Q5_K_M 体积仅比 Q4_K_M 大 16%，但因不在 IME 白名单，同一任务 50 分钟未能完成（Q4_K_M 只需 10.7 分钟）。

2. **温度是 30 秒判据**
   4 核满载执行 IME 向量指令时 SoC 达 55°C 以上；走通用标量路径时 CPU 仍占 390%，温度仅 31~32°C。
   **判断某量化格式是否命中加速路径，不必等基准跑完，看 30 秒温度即可。**

3. **三条候选原因被逐条排除**
   TCM 未生效（修复后 512KB 真实 TCM 分配成功，性能无变化）、运行时版本太旧（v0.2.3 反低 23%）、线程数不足（8 线程使 decode 崩 70%）。
   **三次否证 + 一次证实，归因收敛到量化类型这一个变量。**

4. **decode 受带宽硬约束**
   实测有效带宽约 3.4 GB/s，仅为峰值 10.6 GB/s 的 32%。decode 优化空间在内存访问效率，不在算法。

## 重要约束

| 约束 | 说明 |
|---|---|
| **线程数必须显式设为 4** | 不只是变慢：`llama-cli` 用默认 8 线程会直接 abort（`ime.cpp:1704: thread_n N exceeds perfer_core_ids size 4`，core dump）；`llama-bench -t 8` 则只是 decode 掉 70% |
| 仅用 Q4_0 | Q4_K_M 的 prefill 只有 Q4_0 的 52%；Q5_K / Q3_K_M / KV q8_0 不在白名单 |
| 长 prompt 首字延迟高 | 1200 token 需约 62 秒，长文档问答不可用 |
| 量化器需 v0.2.3 | 0.1.1 无法处理 16 列小张量（`ssm_alpha`），报 `ncols not divisible by 32`；用 `scripts/04_build_quantizer.sh` 构建 |

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/方案书.md](docs/方案书.md) | 方案书：背景、技术路线、开发计划、预期成果、应用价值 |
| [docs/技术文档.md](docs/技术文档.md) | 技术文档：完整优化策略、测试方法、全部数据 |
| [docs/DEPLOY.md](docs/DEPLOY.md) | 模型转换与部署说明：环境准备、五步转换、参数速查、故障排查手册 |
| [docs/PATCH_TCM.md](docs/PATCH_TCM.md) | 框架改造设计说明（§0）+ 诊断、patch、编译、上板验证全记录 |
| [docs/VERSIONS.md](docs/VERSIONS.md) | 环境版本、产物 sha256、镜像校验值 |
| [docs/DEFENSE.md](docs/DEFENSE.md) | 答辩提纲与预设问答 |
| [docs/PLANNING.md](docs/PLANNING.md) | 启动阶段计划（保留以记录当时的判断与修正） |

## 未包含在仓库中的内容

以下内容体积过大，通过脚本重新生成：

- 模型原始权重（13 GB）
- 转换中间产物与量化 GGUF（24 GB）
- 上游 llama.cpp 源码（180 MB，`01_convert.sh` 会提示获取方式）
- 交叉编译产物（9~11 MB，可用 `build_patched_011.sh` 重建）

## 许可证

本项目代码采用 MIT 许可证。模型权重遵循 Qwen 官方许可（Apache-2.0）。
运行时基于 [spacemit-com/llama.cpp](https://github.com/spacemit-com/llama.cpp)，遵循其原始许可。
