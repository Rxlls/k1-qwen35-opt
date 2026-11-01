# 项目验证指南

> 面向：评审/答辩现场验收、交接复现、以及自测回归。
> 前提：设备为进迭时空 K1（Bianbu 2.3.5 / 内核 6.6.63），项目根目录在设备上为 `~/cie`，在仓库里为仓库根。
> **注意路径差异**：仓库里一键脚本是 `scripts/deploy.sh`，设备上部署后放在 `~/cie/tools/deploy.sh`（两者内容一致，md5 应相同）。验证前先确认用的是哪一份。

---

## 1. 验证总览

| # | 维度 | 关键动作 | 耗时 | 通过线 |
|---|---|---|---|---|
| V1 | 仓库与交付物完整性 | 文件清单、可执行位、行尾、体积 | 1 min | 6 项交付物齐全，脚本 755，无 CRLF |
| V2 | 环境与依赖 | `deploy.sh check` + 依赖包 + 传感器 | 1~4 min | 14 或 15 项全绿（见下） |
| V3 | 产物正确性 | 体积 + sha256 + GGUF 结构 | 2 min | sha256 一致；320 张量、nextn=0；非白名单 ≤1 |
| V4 | 功能正确性 | 冒烟出字（2B/4B） | 2 min | 中文无乱码；≥2.6 / ≥1.3 t/s |
| V5 | 性能一致性 | `llama-bench` 对照基线 | 10 min | 2B pp512 ≥19.7；4B ≥7.86（±3%） |
| V6 | 文档一致性 | AUDIT 清单 + 数字抽检 | 5 min | 无"文档有、归档无"的数字 |
| V7 | 可复现性（可选） | 转换链重跑（x86） | 40–60 min | 产物字节数一致、类型分布一致 |

**极速版（5 分钟，现场演示够用）**：V2 → V3（仅体积）→ V4。
**完整版（约 1 小时）**：V1 → V2 → V3 → V4 → V5 → V6 →（V7）。

---

## 2. V1 仓库与交付物完整性

**检查内容**：6 项交付物是否齐全、脚本是否可执行、是否混入大文件/CRLF。

```bash
git ls-files | wc -l                      # 应 ≥ 80
git ls-files -s scripts/ | head           # 权限应为 100755
file scripts/*.sh | grep -c CRLF          # 应为 0
du -sh .                                  # 应 < 20 MB（f16 中间产物 12.5 GB 不入库）
```

**判断标准**：`scripts/*.sh`、`tools/gguf_types.py`、`docs/DEPLOY.md`、`docs/技术文档.docx`、`patches/0001-tcm-dev-path.patch`、`configs/tuned_*.yaml` 六类齐全；可执行位为 755；无 CRLF；仓库不含 `*.gguf`。

**常见问题**：

| 现象 | 原因 | 排查 |
|---|---|---|
| clone 后 `Permission denied` | 提交时丢了可执行位 | `git update-index --chmod=+x scripts/*.sh` |
| K1 上跑脚本报 `$'\r': 未找到命令` | 文件被写成 CRLF | `sed -i 's/\r$//' scripts/*.sh`；提交前 `file` 自查 |
| 仓库 10 GB+ | 误把 f16 中间产物提交 | `.gitignore` 加 `models/ *.gguf`，`git rm --cached` |

---

## 3. V2 环境与依赖

**检查内容**：架构/扩展/内存/磁盘/系统/内核/两个 apt 包/TCM 节点与权限（11 项）+ 模型体积与 sha256（2 项）+ 冒烟（1 项）。
**项数说明**：没有 `docs/hashes.txt` 时是 **14 项**；存在时多一项 sha256 校验，是 **15 项**（耗时从约 1 分钟增到约 3 分钟，因为要哈希 4 GB）。

```bash
bash ~/cie/tools/deploy.sh check     # 只读环境检查（11 项）
bash ~/cie/tools/deploy.sh models    # 模型体积 + sha256（2 项）
bash ~/cie/tools/deploy.sh smoke     # 冒烟（1 项）
# 或一次跑完
bash ~/cie/tools/deploy.sh
```

**判断标准**：末尾出现 `结果: 通过 14 项，失败 0 项` 或 `通过 15 项，失败 0 项`（取决于有无哈希清单），且**失败必须为 0**。其中三条硬门槛：
- ISA 串同时含 `_zve*`（RVV）与 `_ime`；
- `llama.cpp-tools-spacemit` = `0.1.1-bpo1+6`、`spacemit-tcm` = `3.0.0-bpo1+2`；
- `/dev/tcm` 为 `crw-------`（600），**不要 chmod**。

**常见问题**：

| 现象 | 原因 | 排查 |
|---|---|---|
| `[FAIL] 架构 x86_64` | 在 PC 上跑了 | 本脚本必须在 K1 上跑 |
| `alloc_chunk: open(/dev/tcm_sync_mem) failed, errno=2` | 原版 0.1.1 找旧节点，回退堆内存 | **预期且最快**，不是错误 |
| `open(/dev/tcm) failed, errno=13` | 混入了打补丁的库 | `ldd $(command -v llama-cli) \| grep ggml`，确认库都在 `/lib` |
| 冒烟 180 s 超时但屏幕有字 | llama.cpp 写 `/dev/tty` 绕过 `$(...)` | 脚本已用 `setsid` 修；自测时同样加 `setsid` |
| `[FAIL] 正常` | 同上（rc=0 却判失败） | 同上 |
| 自检突然变慢/失败 | 有孤儿 `llama-cli` 占满核 | `pkill -9 -f "llama[-]cli"; pkill -9 -f "llama[-]bench"`，确认 `load<1` |

---

## 4. V3 产物正确性

**检查内容**：体积（粗筛）→ sha256（精确）→ GGUF 结构（语义）。

```bash
cd ~/cie/models
ls -l Qwen3.5-2B-Q4_0-self.gguf Qwen3.5-4B-Q4_0-self.gguf
sha256sum -c ~/cie/docs/hashes.txt          # 需先有 hashes.txt
python3 ~/cie/tools/gguf_types.py Qwen3.5-2B-Q4_0-self.gguf
python3 ~/cie/tools/gguf_types.py --group Qwen3.5-2B-Q4_0-self.gguf
```

**判断标准**：

| 项 | 2B 自产 | 4B 自产 |
|---|---|---|
| 张量总数 | 320 | 320 |
| `block_count` | 24 | 32 |
| `nextn_predict_layers` | 0 | 0 |
| 类型分布 | `{'F32':133,'Q8_0':1,'Q4_0':186}` | 同构（数量按层数放大） |
| 非 IME 白名单张量 | **1**（仅 token_embd） | **1** |

> **体积只看量级，别用作判定**：`llama-bench` 报表按 GiB 截断，比实际字节数少 0.01 GiB（如 1,325,654,048 B 报 1.22 GiB，实为 1.23 GiB）。精确判定用 sha256。
> **跨架构不要比 sha256**：x86 与 RISC-V 量化的产物体积逐字节相同、结构相同，仅末尾约 1 MiB 因浮点舍入不同——判定用"体积 + 张量数 + 类型分布 + 抽样块"。

**常见问题**：

| 现象 | 原因 | 排查 |
|---|---|---|
| `missing tensor 'blk.24.ssm_conv1d.weight'` | MTP 层被当成第 25 层 | 跑 `scripts/02_strip_mtp.sh` |
| `wrong number of tensors; expected 335, got 320` | 只改 `block_count`，没改 `nextn_predict_layers` | 用 `tools/strip_mtp.py`（一次改 3 个键） |
| `token_embd.weight has wrong shape` | 写 GGUF 时形状转置 | 用仓库内 `strip_mtp.py`（已修 `raw_shape` 顺序） |
| 体积对但加载失败 | 下载/拷贝截断 | sha256 比对；`head -c 4` 应为 `GGUF` |

---

## 5. V4 功能正确性

**检查内容**：模型能否在 K1 上稳定出字，中文是否正常，两个尺寸是否都通过。

```bash
llama-cli -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -p 你好 -n 40 -c 1024 -t 4 -st --no-mmap
llama-cli -m ~/cie/models/Qwen3.5-4B-Q4_0-self.gguf -p 你好 -n 40 -c 1024 -t 4 -st --no-mmap
```

**判断标准**：出现中文回复、无乱码/无重复；末尾 `[ Prompt: … | Generation: … ]` 中 Generation ≥2.6（2B）/ ≥1.3（4B）。
注意：该模型默认开思考模式，输出是"思考过程 + 最终回复"，属正常。

**常见问题**：

| 现象 | 原因 | 排查 |
|---|---|---|
| `thread_n N exceeds perfer_core_ids size 4` + core dump | 没传 `-t 4` | 必须显式 `-t 4`；`llama-cli` 默认取 8 核 |
| SIGSEGV 且日志含 `/dev/tcm` | 加载了自建库但路径不全 | `ldd` 检查；用 `LD_LIBRARY_PATH` 指向整套 lib |
| 输出英文思考、迟迟不给答案 | 思考模式 | 加 `-n 200` 让它跑完，或接受现状（本运行时关不掉） |
| `-c 32768` 卡住 | 本机已知问题 | 改用 `-c 16384` 或用 `llama-bench -d` 分段测 |

---

## 6. V5 性能一致性

**检查内容**：在固定口径下重跑基线，与文档值比对。

```bash
# 官方 vs 自产（同一进程跑两次，避免环境漂移）
llama-bench -m ~/cie/models/Qwen3.5-2B-Q4_0.gguf      -t 4 -p 64,512 -n 128 -fa 1 -r 3
llama-bench -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -p 64,512 -n 128 -fa 1 -r 3
# 长上下文
llama-bench -m ~/cie/models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -p 512 -n 64 -d 0,4096,8192 -fa 1 -r 2
```

**判断标准**（±3% 内视为一致）：

| 指标 | 2B 官方 | 2B 自产 | 4B 官方 | 4B 自产 |
|---|---|---|---|---|
| pp512 | 10.84 | **20.36**（≥19.7） | 3.80 | **8.10**（≥7.86） |
| tg128 | 2.84 | 2.80 | 1.32 | 1.43 |

**测量前置条件（必须）**：
1. `pkill -9 -f "llama[-]cli"; pkill -9 -f "llama[-]bench"`，等 `load < 1`；
2. 记录 `cluster0_thermal`（**不是** `thermal_zone0`，那是电池）；
3. 一次只跑一个负载，不要与桌面操作/截图并发；
4. `-c` 固定、`-fa 1`、`-t 4`、mmap 关闭。

**常见问题**：

| 现象 | 原因 | 排查 |
|---|---|---|
| 数值整体偏低 30–60% | 有孤儿进程抢占 | 见上"测量前置条件" |
| 只有 ~10 t/s 且温度不高 | 掉出 IME 白名单 | `gguf_types.py` 查类型；白名单外的换成 Q4_0 |
| `-t 8` 的 tg 组跑不完 | 8 线程 decode 崩塌（实测 240 s 未完成） | 不要用 `-t 8` 做长测 |
| 结果忽高忽低 | 温度/频率未记录、或与他人的负载重叠 | 记录温度，单机串行 |

---

## 7. V6 文档一致性

**检查内容**：文档里的每个数字，能否在 `results/` 里找到出处。

```bash
grep -rn "20.36\|10.84\|8.10\|3.80" docs/*.md | wc -l     # 一致性抽检
ls ~/cie/results/ | wc -l                                   # 归档文件数（应 ≥ 60）
sed -n '1,40p' docs/AUDIT.md                                # 未闭环项清单
```

**判断标准**：`docs/AUDIT.md` 中"仍未闭环"只剩 32K 内存一项；无"文档有值、归档无文件"的数字；图 5/6/7/8 与正文一致。

**常见问题**：

| 现象 | 原因 | 排查 |
|---|---|---|
| 文档改了但 docx 没变 | 只改了 md | `pandoc 技术文档.md -o x.docx --reference-doc=技术文档.docx` + `tools/format_docx.py` |
| docx 版式错乱 | 换了样式模板 | 必须用**原 docx** 作 `--reference-doc`；生成后核对"48 表 / 4 图" |

---

## 8. V7 可复现性（可选，40–60 min，在 x86 上做）

```bash
bash scripts/00_fetch_models.sh 2b
bash scripts/01_convert.sh 2b
bash scripts/02_strip_mtp.sh
bash scripts/04_build_quantizer.sh
bash scripts/03_quantize.sh <f16-nomtp.gguf> Q4_0
```

**判断标准**：产物字节数与设备端**完全相同**，类型分布一致（`gguf_types.py`）；sha256 允许不同（末 1 MiB 浮点舍入差异）。

**常见问题**：`SPERT_DIR is not set`（要用 `-DGGML_SPACEMIT=ON -DSPERT_DIR=…`，不是废弃的 `GGML_CPU_RISCV64_SPACEMIT`）；`unknown type name 'vfloat16m2_t'`（K1 本机 GCC 13 缺 Zvfh，必须交叉编译）；`ncols 16 not divisible by 32`（0.1.1 量化器无小张量回退，用 v0.2.3）。

---

## 9. 最终验收判定

### 9.1 一票否决项（任一不满足即视为未通过）

1. `deploy.sh` 自检未全绿（14 或 15 项，失败 > 0）；
2. 冒烟不出字，或输出乱码；
3. 交付模型 sha256 与 `docs/hashes.txt` 不符；
4. 2B 自产 pp512 < 19.7 t/s（即相对基线的增益消失）；
5. 文档中的核心数字（+87.8% / +113.2%）在 `results/` 找不到对应记录。

### 9.2 通过判定

> 在 K1 上执行 `bash ~/cie/tools/deploy.sh`，输出 `结果: 通过 14 项（含哈希清单时 15 项），失败 0 项`；
> 两个自产 GGUF 的 sha256 与 `docs/hashes.txt` 一致；
> 2B/4B 冒烟均出中文且 Generation ≥2.6 / ≥1.3 t/s；
> `llama-bench` 复跑 2B pp512 ≥19.7 t/s、4B ≥7.86 t/s（±3%）；
> `docs/AUDIT.md` 无未处理的不一致（仅允许 32K 内存一项标注为"终端观测值"）。

同时满足以上五条 → **项目可判定为正常工作**。

### 9.3 结论记录（建议随交付一并提交）

```
验证时间：
设备/系统：K1 / Bianbu 2.3.5 / 内核 6.6.63
自检：14/14
sha256：一致（2B/4B 自产）
冒烟：2B ___ t/s，4B ___ t/s
bench：2B pp512 ___，4B pp512 ___
温度/频率：___ °C / 1600 MHz
结论：通过 / 不通过（原因）
```

---

## 10. 附：最短排查路径

遇到"跑不起来/跑得慢"，按此顺序 3 步定位，覆盖本项目 90% 的故障：

```bash
# 1) 环境对不对（架构/扩展/依赖/TCM）
bash ~/cie/tools/deploy.sh check

# 2) 库有没有混（最隐蔽的一类）
ldd "$(command -v llama-cli)" | grep -E 'llama|ggml'      # 必须全部指向同一目录
echo "[$LD_LIBRARY_PATH]"

# 3) 有没有别的进程在抢（最容易被忽略的一类）
ps -eo pcpu,comm --sort=-pcpu | head -5; cut -d' ' -f1-3 /proc/loadavg
```

三步都干净，再看 `docs/DEPLOY.md` §5 的六类故障（`-t` 断言、TCM 路径、权限、混库、冒烟误判、温度判据）逐条对照。
