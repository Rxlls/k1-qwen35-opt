# 基于K1 AI CPU的Qwen3.5本地部署与性能优化——实施计划与前置需求清单

> **文档性质**：项目启动阶段（2026-10-28）的原始计划，保留以记录当时的判断与后续修正。
> 其中部分结论已被实测推翻（例如「升级运行时能大幅提速」「TCM 未生效是主因」），
> 最新结论请以 [`方案书.md`](方案书.md) 与 [`技术文档.md`](技术文档.md) 为准。
>
> 适用赛题：《RISC-V K1 边缘大模型推理优化赛题说明》  
> 目标平台：进迭时空K1笔记本（8核X60，8GB LPDDR4x，Bianbu OS）  
> 目标模型：Qwen3.5-2B-Instruct、Qwen3.5-4B-Instruct  
> 文档版本：v1.0 / 2026-10-28

---

## 0. 先看结论：5条硬约束决定方案形状

在展开计划前，先把会影响全部技术选型的判断摆出来。这5条如果判断错，后面所有优化都是空转。

**① 8GB内存不是瓶颈，10.6GB/s内存带宽才是。**  
K1采用32位LPDDR4x-2666，峰值带宽约10.6GB/s。Qwen3.5是稠密模型（非MoE），decode阶段每生成1个token要把全部权重从内存搬一遍。因此decode吞吐有一个物理天花板：

```
理论decode上限(tok/s) ≈ 有效带宽 ÷ 每token读取字节数
```

按Q4量化估算：2B约1.3GB/次 → 理论上限8 tok/s，实际4~~6；4B约2.8GB/次 → 理论上限3.8 tok/s，实际2~~3。  
**结论：4B的decode不可能做到“快”，只能做到“比baseline快且稳定”。报告里必须讲清这条物理边界，否则评委会认为数据造假。**

**② Qwen3.5是混合注意力架构，这既是最大风险也是最大机会。**  
Qwen3.5采用8×(3×Gated DeltaNet → 1×Gated Attention)布局，4B规格为32层、hidden 2560、Gated Attention为16Q/4KV头、head_dim 256、原生上下文262144。含义：

- 32层中只有8层是full attention，**KV cache只有常规同规模模型的1/4**（4B约32KiB/token）→ 长上下文内存压力远小于预期，64K上下文KV仅约2GB。这是赛题“KV cache开销过高”这一难点的天然解法。
- 但DeltaNet层携带**循环状态（recurrent state）**，不能像纯attention那样任意裁剪尾部。多轮对话触发context shift时会退化为整体重新prefill → **这是“长上下文吞吐骤降”的真正元凶**，也是最有价值的优化点。
- 官方分支的GGUF架构名为`qwen35`（MoE为`qwen35moe`），**与`qwen3next`不是同一架构**（V头广播排布不同：qwen3next为块状，qwen3.5为交错），不能混用权重或强行加载。

**③ 必须用进迭时空的分支，而不是upstream主线。**  
`spacemit-com/llama.cpp`已发布v0.2.3，其中新增了`ggml-spacemit`设备后端，并专门优化了**GDN（Gated DeltaNet）算子**（m4宽度向量路径、卷积状态strided拷贝），release notes明确写“improves decode performance for GDN-architecture models (Qwen3.5 family)”。用upstream主线跑Qwen3.5在K1上会明显吃亏，且拿不到IME加速。  
**结论：优化版基于spacemit-com/llama.cpp v0.2.3；upstream主线仅作为B0对照组。**

**④ K1上线程数不能开满。**  
官方文档明确：`-t`在K1&#x4E0A;**≤4**（K3才≤8）。原因是IME/TCM只在Cluster 0（4核）上，TCM仅512KB。开8线程会导致TCM争用、推理异常。这条要写进所有脚本的默认参数，并在报告里作为“为什么不是线程越多越快”的分析点。

**⑤ 转换与量化必须在x86机器上做，不要在K1上做。**  
4B模型f16权重约8.4GB，`convert_hf_to_gguf.py`峰值内存约为权重的1.5倍，8GB的K1必OOM。转换+量化流水线放在x86（WSL2/Linux，≥16GB内存）上跑，产物再拷到K1。这同时满足赛题“从官方原始模型生成量化部署产物的转换与量化脚本”的可复现要求——脚本跑在CI/PC上，K1只负责推理。

---

## 1. 赛题解构：评分项 → 交付物 → 验收证据

把评分细则翻译成“评委要看什么”，避免做了一堆实验却没有对应证据。

| 评分项             | 分值 | 评委实际在找什么              | 我方交付物                                                      | 验收证据                                 |
| --------------- | -- | --------------------- | ---------------------------------------------------------- | ------------------------------------ |
| 2B本地部署稳定运行      | 6  | 能跑、不崩、有截图/日志          | 一键部署脚本+运行日志                                                | `llama-cli`/`server`成功输出，连续30分钟不掉    |
| 4B本地部署稳定运行      | 6  | 同上，且不OOM              | 同上                                                         | RSS峰值记录、无swap thrash                 |
| 自行完成转换量化且可复现    | 5  | 从官方原始权重到GGUF的全链路脚本    | `scripts/00_fetch.sh` → `01_convert.sh` → `02_quantize.sh` | 输入/输出sha256清单、固定commit、一条命令重跑        |
| 规定长上下文稳定运行      | 5  | 撑住指定ctx不崩             | ctx阶梯测试报告                                                  | 8K/16K/32K逐级通过，64K为加分                |
| 固定测试集多轮推理质量可用   | 3  | 不是胡言乱语                | 40题×3轮固定测试集+评分表                                            | 人工rubric+跨平台一致性指标                    |
| Prefill吞吐+口径    | 10 | 数字怎么测的、是否可比           | `llama-bench`原始输出                                          | pp64/pp512/pp2048，3次取中位数，标注线程/量化/ctx |
| 首token延迟优化+来源   | 10 | TTFT降了多少、为什么降         | TTFT专项对比表                                                  | 优化前后TTFT，且能拆到“量化/线程/批大小/内核”各贡献多少     |
| Decode吞吐+口径     | 10 | 同上                    | `llama-bench`/`llama-server` metrics                       | tg32/tg128/tg512，含长时稳定性曲线            |
| KV cache或调度路径优化 | 10 | 是否真动了KV/调度            | KV量化+状态快照实验                                                | 内存占用对比、多轮TTFT对比                      |
| 上下文增长吞吐衰减可控     | 10 | 曲线是否平缓                | 衰减曲线图                                                      | 2K→32K的tok/s衰减率                      |
| 长上下文内存/稳定性/时延   | 10 | 会不会OOM、抖动大不大          | 内存与延迟分布                                                    | RSS曲线、P95 inter-token latency        |
| 至少一项可量化优化+前后对比  | 5  | 有A/B                  | 优化矩阵                                                       | 每项优化的独立增益表                           |
| 收益归因清楚          | 5  | 能不能说清是prefill还是decode | 归因分析章节                                                     | 分路径拆解                                |
| 框架改造/量化/KV压缩创新  | 3  | 有没有真东西                | 设计说明+patch                                                 | diff、设计文档                            |
| 代码结构与文档可复现      | 2  | 别人能不能跑起来              | README+目录规范                                                | 干净机器30分钟内跑通                          |

**关键提醒：总分100分里，“性能数字”占60分，但其中一半分值（约30分）落在“口径是否清楚、归因是否成立”上。** 这意味着：一个提升15%但能精确归因的方案，得分会高于提升40%但说不清来源的方案。计划的重心必须放在**实验设计与归因方法**上，而不只是调参。

---

## 2. 技术基线分析

### 2.1 硬件天花板

| 项    | K1规格                                 | 对推理的直接影响                           |
| ---- | ------------------------------------ | ---------------------------------- |
| CPU  | 8×X60 @最高1.6GHz，RVA22，RVV 1.0 256bit | 向量宽度256bit，Q4量化下GEMM可向量化           |
| AI算力 | 2 TOPS，IME自定义指令，仅Cluster 0（4核）       | 只能用4线程吃满IME；`-t>4`反而退化             |
| 片上存储 | 512KB TCM/簇                          | 算子中间结果驻留TCM可省内存往返，是内核优化抓手          |
| 内存   | 32bit LPDDR4x-2666，8GB，带宽≈10.6GB/s   | decode的硬上限，见第0节公式                  |
| 存储   | eMMC（MuseBook默认32GB）+M.2 NVMe位       | 32GB装不下模型+工具链+数据集，**必须加NVMe或高速TF** |
| 散热   | 无风扇/被动，TDP 3~5W                      | 长时间生成必降频，稳定性测试必须记录频率与温度            |

### 2.2 Qwen3.5-4B关键结构（用于内存与算力估算）

| 项               | 值                              | 用途                                     |
| --------------- | ------------------------------ | -------------------------------------- |
| 参数量             | 4.21B                          | 量化体积估算                                 |
| 层数              | 32（24层GDN + 8层Gated Attention） | KV只算8层                                 |
| hidden          | 2560                           | 计算量估算                                  |
| FFN中间维          | 9216                           | 计算量估算                                  |
| 词表              | 248320（与lm_head绑定）             | **embedding单独就占635M参数，是8GB设备上的隐形大头**   |
| Gated Attention | 16 Q头 / 4 KV头 / head_dim 256   | KV/token = 8层×4头×256×2(K,V)×2B = 32KiB |
| GDN             | 32 V头 / 16 QK头 / head_dim 128  | 循环状态约2MB/层，24层约48MB（固定，不随ctx增长）        |
| 原生上下文           | 262144（YaRN可扩至约1M）             | 长上下文有充足空间，受限于内存而非模型                    |
| 许可              | Apache-2.0                     | 可自由分发量化产物                              |

**embedding的坑：**&#x8BCD;表248320×hidden2560=635M参数，占4B模型15%。若按f16存储占1.27GB，Q8_0占0.64GB，Q4占0.32GB。SpacemiT官方量化建议`token-embedding-type`设为q8_0，但在8GB设备上应实测q4_0是否更优——这是**几乎零成本、收益却可能超过5%的优化点**，很多队伍会漏掉。

### 2.3 性能预估（用于设定合理目标，实测后必须校准）

| 模型         | 量化     | 权重体积   | Decode预估      | Prefill预估(pp512) | 32K上下文KV   |
| ---------- | ------ | ------ | ------------- | ---------------- | ---------- |
| Qwen3.5-2B | Q4_K_M | ≈1.3GB | 4~6 tok/s     | 25~50 tok/s      | ≈0.5~0.8GB |
| Qwen3.5-2B | Q4_0   | ≈1.2GB | 5~7 tok/s     | 30~55 tok/s      | 同上         |
| Qwen3.5-4B | Q4_K_M | ≈2.8GB | 2~3 tok/s     | 8~15 tok/s       | ≈1.0GB     |
| Qwen3.5-4B | Q4_0   | ≈2.6GB | 2.2~3.2 tok/s | 10~17 tok/s      | 同上         |

> 预估依据：同代K1实测（qwen2.5-1.5B Q4/4线程 prefill 32.7 tok/s、decode 5.5 tok/s；qwen2.5-3B prefill 15.4、decode 3.0）叠加`ggml-spacemit`新后端与GDN算子优化后的合理外推。**这些数字只用于排期和判断“是否跑偏”，报告里一律以实测为准。**
>
> 重要推论：4B在pp2048下的TTFT可能达到2~4分钟。因此**4B的prefill测试矩阵应以pp64/pp128/pp512为主，pp2048只做一次记录**，否则实验时间会被拖垮，且用户体验结论也不好看。

---

## 3. 总体实施计划

### 3.1 阶段总览

| 阶段 | 名称           | 周期 | 核心任务                       | 出口门（不通过不许进下一阶段）               |
| -- | ------------ | -- | -------------------------- | ----------------------------- |
| P0 | 立项与环境固化      | 3天 | 设备整备、系统版本锁定、观测基线、仓库骨架      | 能一键采集频率/温度/内存；版本清单入库          |
| P1 | 最小闭环打通       | 4天 | 官方包跑通2B/4B，正确性校验           | 两模型均出token；输出与x86同量化结果语义一致    |
| P2 | 自建转换量化流水线    | 5天 | HF→GGUF→量化全脚本，含embedding策略 | 一条命令从原始权重产出4个GGUF，sha256可复现   |
| P3 | Baseline正式测量 | 4天 | B0/B1两套基线，参数网格寻优           | 基线数据入库（≥3次重复，CV<5%）；tuned配置确定 |
| P4 | 长上下文与KV/状态优化 | 6天 | ctx阶梯、KV量化、状态快照、内存治理       | 32K稳定运行；衰减曲线与内存曲线成型           |
| P5 | 框架级改造        | 8天 | GDN prefill分块、TCM常驻、IME内核  | 至少1项改造在A/B中带来≥10%稳定增益         |
| P6 | 收尾与提交        | 5天 | 一键脚本、复现验证、报告、演示            | 干净机器30分钟复现；六项提交物齐全            |

合计约5周（35天）。若赛程更紧，压缩顺序为：P5削减为1项改造 → P4的64K降级为加分项 → P2的imatrix标定取消。**P0/P1/P3不可压缩**，这三段是全部结论的地基。

### 3.2 P0 立项与环境固化（3天）

**目标：**&#x628A;“机器状态”变成可复现的已知量。边缘设备做性能测试，最大的敌人是环境漂移（降频、后台进程、内存碎片）。

关键步骤：

1. **设备建档**：记录机型、序列号、`/etc/bianbu-version`、`uname -a`、`cat /proc/cpuinfo`（确认`isa`含`v`扩展）、`free -h`、`df -h`、BIOS/固件版本。
2. **存储规划**：实测（2026-10-28）系统已由刷机流程装入NVMe（nvme0n1p6=/，119G），eMMC未出现在lsblk中。`/data`直接建在根分区即可（系统约8G+模型约15G，119G充裕），无需单独分区；`ls /dev/mmcblk*`若复核到eMMC可挂为备份盘。
3. **散热整备**：加装散热支架/外置风扇，固定机身姿态。**这不是小事——被动散热的K1跑10分钟decode后会降频20%以上，不控制变量则A/B对比全部失效。**
4. **系统瘦身**：基准测试统一在`multi-user.target`（无GUI）下运行，释放0.5~1GB内存；关闭无关服务（蓝牙、自动更新、索引）。
5. **频率策略**：`cpupower frequency-set -g performance`固定高频；记录`/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`。
6. **观测脚本**：写`tools/monitor.sh`，1秒采样CPU频率、温度、`MemAvailable`、`SwapCached`、进程RSS，输出CSV。**所有性能测试必须与该CSV同时段采集。**
7. **仓库骨架**：建立第7节的目录结构，`.gitignore`排除模型与产物，`docs/VERSIONS.md`记录全部版本。
8. **Bianbu Cloud备用实例**：注册`cloud.spacemit.com`，申请8GB实例。用途有两个——横向验证（云上K1与本机结果一致性）和**备份方案**（若本机硬件故障不至于停摆）。注意云实例无GUI、eMMC仅64GB。

**系统选择结论：统一到Bianbu OS（K1专用镜像）。已装Bianbu则版本锁定不动；若装的是Ubuntu等通用RISC-V系统，P0第一步就是重装Bianbu。**  
重装原因：通用Ubuntu缺SpacemiT的apt源，装不到`llama.cpp-tools-spacemit`与`spacemit-tcm`；内核大概率缺IME/TCM驱动与K1的cpufreq/thermal补丁。前者意味着拿不到2 TOPS AI算力加速（性能可能差2~3倍，而这正是"AI CPU"赛题的立意所在），后者意味着降频不可控、基准数据不可信。推荐镜像：**Bianbu 2.x LXQt桌面版**（官方实测进桌面内存占用649MB，约为GNOME版1210MB的54%，在8GB上对4B长上下文余量影响显著）。重装前两个动作：①若Ubuntu装在NVMe而eMMC仍保留出厂Bianbu，先在启动菜单确认，可能无需重装、直接切回；②备份目标盘数据，烧录会清空。唯一例外：若组委会另行下发"统一镜像"要求（为保证评审数据可比性，这类比赛常见），以组委会通知为准，需在赛题交流群确认。  
赛题正文只约束四件事——模型规格（Qwen3.5-2B/4B-Instruct）、必须使用进迭时空开源llama.cpp、必须本地推理不依赖云端API、必须提供baseline与优化版对比；**全文未对操作系统提出要求**，且把Bianbu Linux BSP与Bianbu LXQt列在官方软件生态中。

**出口门：**

- [ ] `tools/collect_env.sh`一条命令输出完整环境报告
- [ ] 系统版本已写入`docs/VERSIONS.md`，并确认无升级/重装计划（中途换系统会使前后数据不可比）
- [ ] `tools/monitor.sh`能稳定采样，CSV字段完整
- [ ] `/data`可用空间≥100GB
- [ ] 空载与满载（8核`stress-ng`）下的频率/温度曲线已记录，知道本机的降频拐点
- [ ] 云实例可SSH登录

**风险：**&#x4D;useBook类机型eMMC仅32GB，若M.2不可用必须立刻改用高速TF卡（U3/A2以上），否则模型加载时间会成为测试噪声的主要来源。

### 3.3 P1 最小闭环打通（4天）

**目标：**&#x5148;用官方预编译包把两模型跑起来，证明“硬件+系统+模型”这条链没问题，再谈优化。

关键步骤：

1. `sudo apt update && sudo apt install llama.cpp-tools-spacemit`；若包不存在，退回`llama-server`包，或直接源码编译（P1阶段先不折腾编译）。
2. `sudo apt install spacemit-tcm`，装`spacemit-tcm-smi`。**这是K1/K3跑推理的必备运维工具**：程序异常退出后TCM状态不会自动释放，后续推理会报错，必须`spacemit-tcm-smi -c`清理。不装这个，后面会遇到大量“莫名其妙跑不起来”。
3. 下载Qwen3.5-2B/4B的GGUF（先用现成Q4_0或Q4_K_M验证链路）。
4. 跑通三种入口：`llama-bench`（性能）、`llama-cli`（交互）、`llama-server`（API+`--metrics`）。
5. **正确性校验（关键，不能跳）**：
   - 固定`temperature=0`、固定prompt、固定seed，在K1和x86上跑同一份GGUF，对比输出。
   - 检查是否出现乱码、重复、提前EOS、thinking块异常。
   - 重点验证GDN路径：让它做需要长程依赖的任务（如“把上面第3段的第2句原样复述”），若循环状态实现有误，这类任务会立刻暴露。
   - 若spacemit分支跑Qwen3.5异常，**立刻降到upstream主线验证模型本身没问题**，从而把“模型问题”和“后端问题”分开。
6. 记录首版数据（不作为正式baseline，只作量级判断）：`llama-bench -m model.gguf -t 4 -p 64 -n 64 -fa 1 -mmp 0`。

**出口门：**

- [ ] 2B与4B均能用`llama-cli`正常多轮对话
- [ ] `llama-server`的`/metrics`能取到`tokens_predicted_total`等指标
- [ ] 正确性校验表：5类任务×2模型，全部通过
- [ ] 首版decode/prefill数字落在2.3节预估区间内（偏离超过2倍则说明参数或环境有问题，先排查再往下走）

**风险与应对：**

- Qwen3.5的`qwen35`架构需要较新的llama.cpp；若v0.2.3不支持，改用v0.2.x最新tag，并在`docs/VERSIONS.md`记录commit。
- 若出现TCM报错，先`spacemit-tcm-smi -i`查看状态再`-c`清理，不要急着重启。

### 3.4 P2 自建转换量化流水线（5天）

**目标：**&#x4EA7;出一套“从官方原始权重出发、一条命令可重跑”的GGUF，这是5分的硬性提交物。

关键步骤：

1. 在x86机器（WSL2或原生Linux，≥16GB内存，≥60GB磁盘）搭环境：Python 3.10+、torch(CPU)、transformers、gguf、safetensors、sentencepiece。
2. 从ModelScope/HF拉`Qwen/Qwen3.5-2B-Instruct`与`Qwen/Qwen3.5-4B-Instruct`原始权重，**记录每个文件的sha256**。
3. `convert_hf_to_gguf.py`转f16。注意Qwen3.5是混合架构，转换脚本需支持`qwen35`；若报未知架构，说明llama.cpp版本过旧。
4. 量化策略矩阵（这是P2的核心实验，不是简单跑一遍）：

| 配置                         | embedding类型 | 目的                    |
| -------------------------- | ----------- | --------------------- |
| A: Q4_K_M + q8_0 embedding | q8_0        | 厂商推荐路线，质量优先           |
| B: Q4_0 + q8_0 embedding   | q8_0        | IME友好路线，速度优先          |
| C: Q4_0 + q4_0 embedding   | q4_0        | 极限省内存，测质量损失           |
| D: Q3_K_M                  | q8_0        | 对照，看是否还能用             |
| E: Q8_0                    | —           | 质量参考基准（仅x86上跑，K1上跑不动） |

> 为什么Q4_0值得重点测：IME的矩阵指令对Q4_0的8×8打包布局最友好，社区早期优化（rvv_q4_0_8x8）就是围绕Q4_0做的。而K-quants（Q4_K_M）的super-block结构在RISC-V上解包开销更大。**在小模型+SIMD较窄的场景，Q4_0经常反超Q4_K_M**，这是可量化、可归因的发现。
>
> 为什么embedding单独调：见2.2节，635M参数的embedding在8GB设备上是体积大头，且它只参与查表（每次读1行）和最后的lm_head投影（每次读全表）。q8_0→q4_0可省0.3GB内存，对4B在32K上下文下是“能不能跑”的差别。

1. 可选：`llama-imatrix`用中文校准语料生成importance matrix，做imatrix量化（`--imatrix`）。**收益不确定但成本低，值得一试**；若时间紧可放弃。
2. 每个产物记录：文件名、量化参数、体积、sha256、生成命令、llama.cpp commit。

**出口门：**

- [ ] `scripts/00_fetch.sh && 01_convert.sh && 02_quantize.sh`在干净x86上一条链跑通
- [ ] 至少产出A/B/C三套GGUF，附sha256清单
- [ ] 质量初筛：在x86上跑固定20题，A/B/C与Q8_0参考输出的token一致率>85%（C可放宽）
- [ ] 产物已拷至K1的`/data/models/`，K1上可加载

**风险：**&#x8F6C;换脚本对`qwen35`的支持可能不完整（尤其MTP模块、tied embedding）。若转换后模型输出退化，先检查`token_embd`与`output`是否被正确绑定，以及GDN的`A_log`、`dt_bias`、`conv1d`张量是否被正确映射。

### 3.5 P3 Baseline正式测量与参数寻优（4天）

**目标：**&#x5EFA;立两套可信基线，并通过网格搜索找到这台机器的“最优静态配置”。

**基线定义（必须两套，这是归因的基础）：**

| 代号 | 定义                                                                                | 作用               |
| -- | --------------------------------------------------------------------------------- | ---------------- |
| B0 | upstream `ggml-org/llama.cpp`（固定commit）+ 默认参数 + 社区GGUF                            | 证明“厂商分支值多少钱”     |
| B1 | `spacemit-com/llama.cpp` v0.2.3 + 官方推荐参数（`-t 4 -fa 1 -mmp 0 --no-mmap`）+ 自产Q4_K_M | 证明“我们的调优与改造值多少钱” |
| O  | 自编译优化版 + tuned参数 + 自产量化 + KV/状态优化 + 改造                                            | 最终成绩             |


**参数网格（每维只测3~4档，全因子会爆炸）：**

| 维度 | 候选值 | 预期 |
|---|---|---|
| 线程`-t` | 2 / 4 / 8 | 4最优；8因TCM争用退化 |
| 绑核 | 默认 / `--cpu-mask 0x0f`（Cluster0）/ `0xff` | 绑Cluster0稳 |
| 批线程`-tb` | 4 / 8 | prefill可能受益于8 |
| 微批`-ub` | 128 / 256 / 512 | 8GB下256更稳 |
| FlashAttention `-fa` | 0 / 1 | 配合KV量化必须为1 |
| mmap | 开 / `--no-mmap` | 无mmap抖动更小 |
| KV类型`-ctk/-ctv` | f16 / q8_0 / q4_0 | q8_0省一半且质量损失小 |
| 量化 | A/B/C三套 | B可能最快 |

方法：**逐维扫描（one-factor-at-a-time）确定单维最优，再对交互强的两维（`-t`×`-tb`、`-fa`×KV类型）做小规模组合验证**。每配置3次重复取中位数，丢弃首次（warmup），记录CV。

**出口门：**
- [ ] B0/B1/O三套在2B、4B上各有完整pp/tg数据，至少覆盖pp64、pp512、tg128
- [ ] 参数寻优表：每个维度的增益百分比
- [ ] `configs/tuned_2b.yaml`、`configs/tuned_4b.yaml`确定
- [ ] 重复性验证：同配置连续5次，decode tok/s的CV<5%
- [ ] 温度/频率与性能的对应关系已记录（证明测试不是在做热降频下的噪声比较）

**这是全项目最容易被低估的阶段。** 很多队伍在这里只跑一次就下结论，结果后面的“优化增益”其实是热降频波动。**建议把至少1/4的总时间花在测量方法论上。**

### 3.6 P4 长上下文与KV/状态优化（6天）

**目标：**攻下赛题第三大方向，也是Qwen3.5架构特性最能发挥的地方。

关键步骤：
1. **上下文阶梯测试**：2K/4K/8K/16K/32K/64K，每级记录pp512、tg128、RSS峰值、P95 inter-token latency。绘制“tok/s vs ctx”衰减曲线与“RSS vs ctx”曲线。
2. **KV量化**：`-ctk q8_0 -ctv q8_0`（需`-fa 1`）。测量：内存下降多少、decode是否变慢（RISC-V上量化KV可能走非优化路径，**必须实测，不能假设更快**）、质量是否可接受。
3. **多轮对话的TTFT治理（本项目最有价值的优化之一）**：
   - 现象：Qwen3.5的GDN层带循环状态，context shift时无法只裁剪尾部，llama.cpp会整体重新prefill → 第N轮TTFT接近第1轮，多轮体验崩坏。
   - 手段一：prompt cache复用（`--prompt-cache`/slot save-restore），纯文本场景应可用（注意官方对“多模态+混合模型”禁用了cache复用，纯文本不受影响）。
   - 手段二：调`--ctx-checkpoints`（快照窗口数量），在内存与回滚粒度间取平衡。
   - 手段三（进阶，属P5改造）：为GDN循环状态做定长快照，实现“回滚到最近快照+重算少量token”，把context shift从O(ctx)降到O(窗口)。
   - 测量：3轮对话的TTFT序列（第1/2/3轮），优化前后对比。
4. **内存抖动治理**：
   - `vm.swappiness=10`；评估zram（能防OOM但会增加延迟，仅作兜底）。
   - 关闭透明大页的`always`模式改用`madvise`，避免大页回收造成长尾延迟。
   - 用P95/P99 inter-token latency而非均值衡量“抖动”，这才是评委想看的。
5. **长上下文稳定性**：32K上下文下连续生成2000 token，记录RSS曲线是否单调上升（内存泄漏）、频率是否掉档、是否触发OOM killer。

**出口门：**
- [ ] 2B在32K、4B在16K下稳定完成多轮对话不崩（64K为加分项）
- [ ] 衰减曲线：32K相对2K的decode衰减率有明确数字，且优化版优于B1
- [ ] 多轮TTFT：第3轮TTFT ≤ 第1轮的1.5倍（优化前通常接近1:1甚至更差，即每轮都全量重算）
- [ ] 2000 token长生成RSS增长<50MB（无泄漏）
- [ ] P95/P99延迟分布图

### 3.7 P5 框架级改造（8天）

**目标：**拿“工程与创新”3分，同时为prefill/decode提供真实增益。**只做1~2项，做深不做多。**

候选改造按投入产出排序：

| 优先级 | 改造项 | 技术要点 | 预期收益 | 风险 |
|---|---|---|---|---|
| ★★★ | GDN prefill分块并行 | DeltaNet的prefill若按token串行扫描则无法利用8核；改为chunked parallel scan（块内并行+块间状态传递），配合RVV向量化 | prefill +20~40% | 需理解chunked GDN公式，数学门槛高 |
| ★★★ | embedding/lm_head量化与布局优化 | 强制q4_0 embedding + 输出层tile化，减少每token全表读取 | decode +5~10%，省0.3~0.9GB | 低 |
| ★★☆ | GDN循环状态TCM常驻 | 把当前活跃层的状态块放进512KB TCM，减少L1/L2往返 | decode +5~15% | 状态2MB/层放不下，只能分块/部分常驻；需与后端调度配合 |
| ★★☆ | 双簇分工 | Cluster0跑IME矩阵乘，Cluster1跑norm/激活/采样等逐元素算子 | decode +5~10% | 线程同步开销可能吃掉收益 |
| ★☆☆ | KV分页/更细粒度分配 | 8个full-attn层独立KV池，按实际ctx分配 | 长上下文内存-20% | 改动面大，llama.cpp已有类似机制 |
| ☆☆☆ | 权重稀疏化/剪枝 | 收益不确定，质量风险高 | — | 不建议，性价比最低 |

**方法要求：每次改造必须做成可开关的编译选项或运行时flag，能做A/B。** 不能A/B的改造在答辩时等于没做。

**出口门：**
- [ ] 至少1项改造在固定配置下带来≥10%的可重复增益（3次CV<5%）
- [ ] 改造项有独立patch/diff与设计说明（含公式推导或数据布局图）
- [ ] 改造后质量不退化（固定测试集得分不低于改造前）
- [ ] 能明确回答“这项改造加速的是prefill还是decode，为什么”

### 3.8 P6 收尾与提交（5天）

1. **一键部署脚本**：`deploy.sh`在干净Bianbu上从零到能对话，包含依赖安装、模型校验、服务启动、systemd单元。
2. **复现验证**：找一台未参与开发的机器（或重置系统）跑一遍，计时。目标30分钟内完成。
3. **报告撰写**：结构建议——
   - 背景与目标 → 平台与模型分析（第2节内容）→ 基线与方法学 → 优化路线与逐项收益 → 长上下文专项 → 改造设计说明 → 局限与展望
   - 每张图必须标注：模型、量化、线程、ctx、重复次数、测试时间
4. **演示材料**：3分钟视频，含4B在K1上真实对话（**注意选短prompt，4B的prefill慢，长prompt会让演示很难看**）。
5. **代码整理**：删掉临时脚本，统一命名，补README，确保`git clone`后能跑。

**出口门（对照赛题六项提交要求逐条勾选）：**
- [ ] 可运行代码
- [ ] 一键部署脚本
- [ ] 从官方原始模型生成量化产物的转换与量化脚本
- [ ] 模型转换与部署说明文档
- [ ] baseline与优化版性能测试报告
- [ ] 框架改造/模型压缩的设计说明

---

## 4. 优化技术路线（分层，便于归因）

把优化按“改动成本”分四层，报告里按层呈现，归因自然清晰。

### L0 运行时配置（0代码改动，1天出结果）
`-t 4`绑Cluster0、`-tb`调优、`-ub 256`、`-fa 1`、`--no-mmap`、`--mlock`评估、`performance`调频、headless运行、关THP always。
**预期总增益：10~25%。这一层必须做满，因为它是“免费的”，且是后续所有对比的基准平台。**

### L1 量化策略（1天，脚本改动）
Q4_0 vs Q4_K_M、embedding q8_0 vs q4_0、可选imatrix、Q3_K_M兜底。
**预期：decode 5~15%，内存 10~25%。**

### L2 KV与调度（3天，参数+少量代码）
KV q8_0、ctx-checkpoints调优、prompt cache复用、slot save/restore、长上下文内存预分配策略。
**预期：长上下文内存-40~50%，多轮TTFT-50%以上。**

### L3 内核与框架改造（8天，C++改动）
GDN prefill分块、TCM常驻、双簇分工、embedding tile化。
**预期：prefill +20~40%，decode +5~15%。**

> 归因方法：按L0→L1→L2→L3顺序逐层叠加测量，每层记录“增量”而非“总量”。这样报告里可以给出瀑布图：baseline → +L0 → +L1 → +L2 → +L3，每一段都有数字。**这是最能拿满“收益归因”5分的呈现方式。**

---

## 5. 评测方法与口径规范

### 5.1 指标定义（必须写进报告，否则“口径不清”扣分）

| 指标 | 定义 | 采集方式 |
|---|---|---|
| Prefill吞吐(pp) | 处理N个prompt token的速率，tok/s | `llama-bench -p N`，或server日志`prompt eval time` |
| TTFT | 请求发出到首token返回的墙钟时间，ms | 客户端打时间戳，含HTTP开销 |
| Decode吞吐(tg) | 生成阶段速率，tok/s | `llama-bench -n N`，或`predicted_per_second` |
| P95 inter-token latency | 相邻token间隔的95分位 | 流式响应逐token打点 |
| 内存峰值 | 进程RSS峰值 + 系统MemAvailable最低值 | `monitor.sh` 1Hz采样 |
| 衰减率 | (2K时tok/s − 32K时tok/s)/2K时tok/s | 阶梯测试 |

### 5.2 测试矩阵（最小可行版）

| 模型 | 量化 | ctx | pp | tg | 重复 |
|---|---|---|---|---|---|
| 2B | Q4_K_M / Q4_0 | 2K | 64/512/2048 | 128 | 3 |
| 2B | Q4_0 | 8K/16K/32K | 512 | 128 | 3 |
| 4B | Q4_K_M / Q4_0 | 2K | 64/512 | 128 | 3 |
| 4B | Q4_0 | 8K/16K | 512 | 128 | 3 |
| 4B | Q4_0 | 32K | 256 | 64 | 2（耗时长） |

外加：多轮TTFT测试（3轮×5组）、长时稳定性（2000 token×1次）、质量测试集（40题×3轮）。

### 5.3 质量评估（3分的“结果质量可用”）

三路证据，互相补强：
1. **人工rubric**：40题分5类（中文常识、多轮指代、长文摘要、代码生成、数学推理），每题1~5分，两人独立打分取均值。
2. **跨平台一致性**：同prompt、`temperature=0`，比较K1(Q4)与x86(Q8_0)输出的token级一致率与语义相似度。**这是量化损失最客观的代理指标**，且完全可复现。
3. **客观题正确率**：从C-Eval/GSM8K各抽30题，看准确率相对Q8_0的保留率。

### 5.4 可复现性要求

- 所有测试加`taskset`绑核，避免调度漂移。
- 每次测试前`sync && echo 3 > /proc/sys/vm/drop_caches`清页缓存（除测mmap冷启动场景）。
- 记录测试时的环境温度（室温）、机器温度、频率。
- 原始输出（`llama-bench`的JSON、monitor CSV、server日志）全部入库存档，不只留汇总表。

---

## 6. 前置需求清单

> 说明：版本号中标注「锁定」的为实测后必须固定并写入`docs/VERSIONS.md`的项；标注「≥」的为最低要求。**所有下载项建议保留sha256，赛题要求“可复现”，校验和是最便宜的证明。**

### 6.1 硬件与外设

| 项 | 规格要求 | 用途 | 备注 |
|---|---|---|---|
| K1笔记本 | 8核X60 / 8GB LPDDR4x / Bianbu OS | 目标平台 | 记录机型与固件版本 |
| NVMe SSD | M.2 2242/2280，≥256GB，PCIe3.0即可 | 模型、数据集、编译产物 | **强烈建议**，默认32GB eMMC不够用 |
| 或高速TF卡 | U3/A2，≥128GB | 替代方案 | 加载速度明显慢于NVMe，会影响冷启动测试 |
| 散热支架/外置风扇 | USB供电即可 | 抑制降频 | **必备**，否则长时测试数据不可用 |
| x86开发机 | ≥16GB内存，≥60GB空闲磁盘，Win11+WSL2或原生Linux | 模型转换、量化、交叉验证 | 4B的f16转换峰值内存约12GB |
| 千兆网络 | 局域网 | 大文件传输 | 8.4GB模型走WiFi会很痛苦 |
| 电源 | 65W PD（原装） | 保证不降频 | 电池供电会限频 |

### 6.2 操作系统与基础软件（K1端）

| 项 | 版本/规格 | 用途 | 安装方式 |
|---|---|---|---|
| Bianbu OS | 锁定镜像变体（GNOME/LXQt/Minimal）+版本号+内核 | 系统底座 | 预装，**不要随意升级或重装** |
| `llama.cpp-tools-spacemit` | 锁定（随v0.2.3发布） | 官方预编译推理工具 | `apt install llama.cpp-tools-spacemit` |
| `spacemit-tcm` | 锁定 | `spacemit-tcm-smi`监控/清理TCM | `apt install spacemit-tcm` |
| `build-essential` | GCC ≥13（Bianbu自带） | 源码编译 | `apt install build-essential` |
| `cmake` | ≥3.20 | 构建llama.cpp | `apt install cmake` |
| `ninja-build` | ≥1.10 | 加速构建 | 可选但推荐 |
| `git` | ≥2.30 | 拉取源码 | `apt install git` |
| `python3` | ≥3.10 | 测试脚本、server客户端 | 系统自带 |
| `python3-venv`/`pip` | — | 隔离Python依赖 | `apt install python3-venv python3-pip` |
| `cpupower`/`cpufrequtils` | 任意 | 固定performance调频 | `apt install linux-cpupower` |
| `stress-ng` | 任意 | 满载降频测试 | 可选 |
| `tmux` | ≥3.0 | 长时测试保活 | `apt install tmux` |
| `sysstat` | 任意 | `sar`采集系统指标 | `apt install sysstat` |
| `htop`/`btop` | 任意 | 实时观测 | 可选 |
| `jq` | ≥1.6 | 解析JSON结果 | `apt install jq` |
| `rsync`/`zstd` | 任意 | 传输与压缩 | 建议 |
| `stress`、`lm-sensors` | 任意 | 温度读取 | `apt install lm-sensors` |

> **关于"Bianbu OS"与"Bianbu LXQt"的区分（容易混淆，需在报告里写清）：**
> Bianbu OS是系统名，官方提供三个镜像变体——GNOME桌面版、LXQt桌面版、Minimal命令行版，三者是同一发行版的不同桌面封装，不是三个系统。官方数据（基于K1 MUSEBOOK）显示：进桌面未运行应用时，GNOME版内存占用约1210MB，LXQt版约649MB，**相差约560MB**。在8GB设备上这560MB直接决定4B模型能否开到32K上下文，因此：
> - 若本机是LXQt变体：保持不动，已是内存最优的官方形态。
> - 若本机是GNOME变体：不必重装系统，基准测试切`multi-user.target`（headless）即可；若愿意重装为LXQt，**必须在P0阶段就定下来**，因为换镜像会使已测基线全部作废。
>
> 确认命令：`cat /etc/os-release`（看Bianbu版本）、`cat /etc/bianbu-version`、`echo $XDG_CURRENT_DESKTOP`（看桌面环境，GNOME/LXQt）、`uname -r`（内核）。

### 6.3 模型与数据

| 项 | 规格 | 用途 | 获取 | 体积 |
|---|---|---|---|---|
| Qwen3.5-2B-Instruct原始权重 | safetensors，Apache-2.0 | 转换与量化的源头 | ModelScope/HF `Qwen/Qwen3.5-2B-Instruct` | ≈4.2GB(f16) |
| Qwen3.5-4B-Instruct原始权重 | 同上 | 同上 | `Qwen/Qwen3.5-4B-Instruct` | ≈8.4GB(f16) |
| tokenizer相关文件 | 随权重 | 转换必需 | 同上 | ≈15MB |
| 参照GGUF（可选） | unsloth `Q4_K_M`/`UD-Q4_K_XL` | 与自产GGUF交叉校验，排除转换bug | `unsloth/Qwen3.5-2B-GGUF`、`unsloth/Qwen3.5-4B-GGUF` | ≈1.3/2.8GB |
| SpacemiT模型包（可选） | `archive.spacemit.com/spacemit-ai/model_zoo/vlm/`下的Qwen3.5-2B/4B | 官方已拆分验证的参照实现 | 官网 | 数GB |
| imatrix校准语料 | 中文通用文本，≥200万token | imatrix量化（可选） | 自建/wiki | ≈50MB |
| 固定测试集 | 40题×5类×3轮，JSON格式 | 质量评估 | 自建 | <1MB |
| 长上下文测试集 | NIAH针测试+长文摘要，8K/16K/32K | 长上下文能力验证 | 自建 | <5MB |
| perplexity语料 | held-out中文文本，≥10万token | 量化质量客观指标 | 自建 | ≈5MB |

### 6.4 工具链与源码

| 项 | 版本 | 用途 | 说明 |
|---|---|---|---|
| `spacemit-com/llama.cpp` | **锁定 v0.2.3**（记录commit） | 优化版基础 | 含`ggml-spacemit`后端与GDN算子优化 |
| `ggml-org/llama.cpp` | 锁定某commit | B0基线对照 | 证明厂商分支价值 |
| RISC-V工具链 | 使用源码树内`cmake/riscv64-spacemit-linux-gnu-gcc.cmake` | 本地编译 | 需GCC支持`rv64gcv_zvfh_zfh_zicbop_zihintpause_zba` |
| CMake | ≥3.20 | 构建 | 编译命令见6.4.1 |
| ONNXRuntime（可选） | `archive.spacemit.com/spacemit-ai/onnxruntime/`最新版 | 仅多模态SMT扩展需要 | **纯文本赛题不需要，别浪费时间** |

**6.4.1 编译命令（K1本机，锁定）**

```bash
cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CPU_RISCV64_SPACEMIT=ON \
    -DGGML_CPU_REPACK=OFF \
    -DLLAMA_OPENSSL=OFF \
    -DGGML_RVV=ON \
    -DGGML_RV_ZVFH=ON \
    -DGGML_RV_ZFH=ON \
    -DGGML_RV_ZICBOP=ON \
    -DGGML_RV_ZIHINTPAUSE=ON \
    -DGGML_RV_ZBA=ON \
    -DCMAKE_TOOLCHAIN_FILE=${PWD}/cmake/riscv64-spacemit-linux-gnu-gcc.cmake \
    -DCMAKE_INSTALL_PREFIX=build/installed

cmake --build build --parallel 6 --config Release
```

> `--parallel 6`而非`8`：8GB内存下8路编译易OOM，建议保持6，或先加4GB swap。
> `GGML_CPU_REPACK=OFF`：官方基础版本用OFF；若后续测出`ON`更快可在报告里作为一项参数优化。

### 6.5 Python依赖（x86转换机 + K1测试端）

| 包 | 版本要求 | 用途 |
|---|---|---|
| `torch` | ≥2.3，CPU版即可 | `convert_hf_to_gguf.py`读取权重 |
| `transformers` | 需支持`qwen35`架构（以llama.cpp `requirements.txt`为准） | 加载原始模型配置 |
| `gguf` | 随llama.cpp `requirements.txt` | GGUF写出与检查 |
| `safetensors` | ≥0.4 | 权重读取 |
| `sentencepiece` | ≥0.2 | tokenizer |
| `numpy` | ≥1.24 | 数据处理 |
| `huggingface_hub` + `hf_transfer` | 最新 | 加速下载（国内建议配镜像或改用ModelScope） |
| `modelscope` | 最新 | 国内下载替代方案 |
| `openai` | ≥1.0 | 调用`llama-server`的OpenAI兼容接口 |
| `requests`/`httpx` | 最新 | 流式TTFT与逐token打点 |
| `pandas`/`matplotlib` | 最新 | 结果汇总与作图 |
| `psutil` | 最新 | 进程RSS采集 |
| `datasets` | 最新 | 加载C-Eval/GSM8K子集 |


### 6.6 评测与观测工具

| 工具 | 来源 | 用途 |
|---|---|---|
| `llama-bench` | llama.cpp构建产物 | **核心性能工具**，pp/tg标准口径 |
| `llama-quantize` | 同上 | 量化 |
| `llama-imatrix` | 同上 | importance matrix（可选） |
| `llama-perplexity` | 同上 | 量化质量客观指标 |
| `llama-batched-bench` | 同上 | 吞吐-并发关系（长上下文调度分析） |
| `llama-server` + `--metrics` | 同上 | Prometheus指标，TTFT/latency来源 |
| `spacemit-tcm-smi` | `spacemit-tcm`包 | TCM状态查看与清理（**必备**） |
| `perf` | `apt install linux-perf` | 热点函数定位（P5改造用） |
| `monitor.sh`（自写） | — | 频率/温度/RSS 1Hz采样 |
| `bench_client.py`（自写） | — | 流式TTFT、逐token延迟、多轮测试 |

### 6.7 文档、账号与合规

| 项 | 用途 |
|---|---|
| 赛题说明Markdown（已有） | 需求源头，评分细则对照 |
| SpacemiT官方llama.cpp文档（中/英） | 参数、编译、模型列表 |
| SpacemiT K1数据手册 | 写报告“平台分析”章节引用 |
| llama.cpp upstream `docs/` | 参数语义、`llama-bench`口径 |
| Qwen3.5 Model Card | 架构参数、推荐采样参数、许可证 |
| ModelScope/HuggingFace账号 | 下载大模型（注意配置镜像加速） |
| GitHub账号 | fork、提交patch、发布release |
| `cloud.spacemit.com`账号 | Bianbu Cloud 8GB实例（备份+横向验证） |
| 提交模板/往届优秀作品 | 对齐评委预期（若有） |

### 6.8 存储与网络预算

| 项 | 估算 |
|---|---|
| 原始权重（2B+4B） | ≈13GB |
| f16 GGUF中间产物 | ≈13GB（可与原始权重放同一机器，转换后删） |
| 量化产物（A/B/C/D四套×2模型） | ≈12GB |
| 参照GGUF | ≈4GB |
| 源码与构建产物 | ≈8GB（llama.cpp build目录较大） |
| 数据集与测试集 | <1GB |
| **K1端总需求** | **≥40GB**（故必须NVMe/TF扩容） |
| **x86转换机总需求** | **≥60GB空闲** |
| 下载总量 | ≈20GB，建议在x86上下载后rsync到K1 |

### 6.9 版本固化清单（`docs/VERSIONS.md`模板）

```yaml
platform:
  board: "<机型>"
  bianbu_version: "<cat /etc/bianbu-version>"
  kernel: "<uname -r>"
  cpu: "K1 8xX60, isa=<cat /proc/cpuinfo | grep isa>"
  ram_total: "<free -h>"
toolchain:
  gcc: "<gcc --version>"
  cmake: "<cmake --version>"
  python: "<python3 --version>"
llama_cpp_spacemit:
  tag: "v0.2.3"
  commit: "<git rev-parse HEAD>"
  build_flags: "<见6.4.1>"
llama_cpp_upstream:
  commit: "<git rev-parse HEAD>"
models:
  qwen3_5_2b_instruct_sha256: "<...>"
  qwen3_5_4b_instruct_sha256: "<...>"
artifacts:
  qwen3_5_2b_q4km_q8emb:
    file: "..."
    size: "..."
    sha256: "..."
    quantize_cmd: "..."
```

---

## 7. 仓库结构与脚本骨架

```
k1-qwen35-opt/
├── README.md                    # 30分钟跑通指南
├── docs/
│   ├── VERSIONS.md              # 6.9节版本固化清单
│   ├── PLAN.md                  # 本实施计划
│   ├── ANALYSIS.md              # 平台与模型分析（报告第2章素材）
│   ├── DESIGN_GDN_PREFILL.md    # 改造设计说明（若做）
│   └── BENCH_METHOD.md          # 测试口径规范
├── scripts/
│   ├── 00_fetch_models.sh       # x86：下载原始权重+sha256
│   ├── 01_convert_gguf.sh       # x86：HF→f16 GGUF
│   ├── 02_quantize.sh           # x86：量化矩阵A/B/C/D
│   ├── 03_verify_artifact.sh    # 校验体积/sha256/可加载
│   ├── 10_build_k1.sh           # K1：源码编译
│   ├── 11_deploy.sh             # K1：一键部署（依赖+模型+systemd）
│   ├── 20_bench_baseline.sh     # B0/B1基线
│   ├── 21_bench_tuned.sh        # 优化版
│   ├── 22_bench_longctx.sh      # 上下文阶梯
│   ├── 23_bench_multiturn.sh    # 多轮TTFT
│   ├── 30_quality_eval.sh       # 固定测试集
│   └── 90_report_assets.sh      # 生成图表与汇总表
├── configs/
│   ├── tuned_2b.yaml
│   ├── tuned_4b.yaml
│   └── bench_matrix.yaml
├── tools/
│   ├── monitor.sh               # 频率/温度/RSS采样
│   ├── collect_env.sh           # 环境快照
│   └── bench_client.py          # 流式TTFT/逐token延迟
├── results/
│   ├── raw/                     # 原始JSON/CSV/日志（必须入库）
│   └── summary/                 # 汇总表与图
├── patches/                     # 框架改造diff（若有）
└── data/
    └── testset/                 # 固定测试集
```

---

## 8. 风险登记册

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| spacemit分支对`qwen35`支持不完整（CRASH/输出乱码） | 中 | 高 | P1先验证；退到v0.2.x最新tag；用upstream交叉验证是模型问题还是后端问题 |
| 转换脚本不支持MTP/tied embedding，产物退化 | 中 | 高 | P2做A/B：自产GGUF vs 官方GGUF在同一prompt下的输出一致性 |
| 长时测试热降频导致数据不可比 | 高 | 中 | 固定散热、固定调频、测试间冷却到同一温度、记录频率、CV>5%则重测 |
| 4B在32K上下文OOM | 中 | 中 | KV q8_0、`-ub 128`、headless运行、预留swap兜底；实在不行4B降到16K，报告里说明边界 |
| 框架改造无收益或引入bug | 中 | 中 | 改造必须可开关；设“无收益也保留分析结论”的退路（负结果也是结论） |
| 时间不足，P5做不完 | 高 | 低 | P5降级为“只做embedding量化+L0/L1/L2”，仍可拿基础优化分 |
| 32GB eMMC空间不足 | 高 | 高 | P0第一件事就解决存储 |
| 赛题未明确“规定长上下文长度” | 中 | 中 | 按8K/16K/32K/64K全测，主动向组委会确认口径 |

---

## 9. 七天快速启动清单（可直接勾选执行）

**第1天｜设备与系统**
- [ ] 记录机型、Bianbu版本、内核、CPU isa、内存、磁盘
- [ ] 装NVMe SSD/TF卡，挂载`/data`，确认≥100GB可用
- [ ] 装散热支架，`apt install lm-sensors`并确认能读温度
- [ ] `apt install spacemit-tcm`，`spacemit-tcm-smi -i`能出状态
- [ ] 写`collect_env.sh`与`monitor.sh`，跑通一次采样
- [ ] 注册`cloud.spacemit.com`，申请8GB实例并SSH成功

**第2天｜跑通第一个token**
- [ ] `apt install llama.cpp-tools-spacemit`
- [ ] 下载Qwen3.5-2B的现成GGUF
- [ ] `llama-cli -m ... -t 4 -c 4096`出中文回答
- [ ] `llama-bench -m ... -t 4 -p 64 -n 64 -fa 1 -mmp 0`出数据
- [ ] 记录首版数字，与2.3节预估对比

**第3天｜4B与正确性**
- [ ] 4B跑通，记录RSS峰值
- [ ] 5类任务正确性校验（复述、多轮指代、长文摘要、代码、算术）
- [ ] 与x86同GGUF输出对比，确认无系统性偏差
- [ ] 建仓库骨架，首次提交

**第4-5天｜转换量化流水线**
- [ ] x86装Python环境
- [ ] 拉原始权重，记sha256
- [ ] `convert_hf_to_gguf.py`转f16（先2B）
- [ ] 量化Q4_K_M+Q8_0 embedding、Q4_0+Q8_0 embedding、Q4_0+Q4_0 embedding
- [ ] 产物拷到K1，三个都能加载
- [ ] 4B重复一遍

**第6-7天｜基线测量**
- [ ] B0（upstream）编译并测pp64/pp512/tg128
- [ ] B1（spacemit官方包+推荐参数）同口径测
- [ ] 参数网格：`-t`/`-tb`/`-ub`/`-fa`/`-no-mmap`/KV类型
- [ ] 3次重复，算CV，确认<5%
- [ ] 定下`tuned_2b.yaml`/`tuned_4b.yaml`
- [ ] 出第一版瀑布图（baseline → +L0 → +L1）

---

## 10. 一句话总结

这个赛题的胜负手不在“把模型跑起来”（那只是25分的地板），而在**能否用Qwen3.5混合注意力的架构特性，把长上下文和prefill这两个K1最痛的场景讲清楚、优化到位、归因明白**。8GB内存与10.6GB/s带宽是不可逾越的物理边界，报告里大方承认边界、并在边界内做到极致，比虚报数字更能得分。

---

## 附录A：Bianbu重装速查（当前若装的是Ubuntu等通用系统）

**镜像格式二选一，千万别混（最常见的坑）：**

| 文件名形态 | 镜像类型 | 烧录方式 |
|---|---|---|
| `bianbu-k1-xxx.img.zip`（文件名带img） | SD卡/U盘镜像 | 解压后用balenaEtcher或`dd`写入U盘/TF卡 |
| `bianbu-k1-xxx.zip`（不带img） | eMMC镜像 | 用官方Titan Flasher经USB直刷eMMC，或解压后fastboot刷写 |

**重装前先做一步：确认eMMC是否还留有出厂Bianbu。** Ubuntu若装在NVMe，出厂Bianbu可能还在eMMC上，开机启动菜单切回即可，无需重装。

**推荐路线（笔记本，系统进eMMC、NVMe留作数据盘）：**
1. 从`archive.spacemit.com/image/k1/version/bianbu/`下载K1+LXQt桌面版最新稳定镜像，记录sha256
2. Windows上balenaEtcher三步：Flash from file → Select target（认准U盘，勿选电脑硬盘）→ Flash!，烧完自动校验
3. U盘插K1，开机连按Esc（以开机画面提示为准）进启动菜单，选U盘设备
4. 首次启动按提示创建用户；root默认密码bianbu
5. **不要把根文件系统迁到NVMe**：Bianbu默认引导目标为eMMC，迁NVMe需改U-Boot的`root=`环境变量并重挂/boot分区，性价比极低；NVMe格式化后挂`/data`放模型与数据集
6. 刷机U盘保留作救援盘，赛中系统异常可快速恢复

**路线B：PC直连笔记本烧eMMC（Titan Flasher，免U盘）**
1. Windows PC安装`titantools_for_windows-latest`（含驱动，需C盘>10GB）
2. 下载**不带img的**`bianbu-k1-xxx.zip`（K1+LXQt桌面版eMMC镜像）
3. 笔记本关机，按官方文档进入刷机模式（BOOTROM，通常是按住刷机/恢复键再接USB），用USB-C数据线连PC（原装65W线即可）
4. Titan Flasher加载镜像，点烧录，完成后开机
5. 注意：直刷会**清空整个eMMC**，若eMMC还留有出厂Bianbu，烧录前先在启动菜单确认是否可直接切回使用；NVMe上的Ubuntu不受影响，可留作对照系统
