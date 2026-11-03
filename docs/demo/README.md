# 真机演示视频

三段录像，全部在 K1 本机录制（labwc/Wayland + `grim` 连拍 + x264），未使用外部录屏设备。

| 文件 | 时长 | 内容 | 用途 |
|---|---|---|---|
| `k1-2b-ab.mp4` | 40 s | **2B 对照**：同一段 534 token 提示词，官方 vs 自产 | 答辩主用 |
| `k1-4b-ab.mp4` | 73 s | **4B 对照**：同上，换 4B 模型 | 答辩主用 |
| `k1-2b-demo.mp4` | 37 s | 2B 自产单模型生成中文（第一版，字号较小） | 展示"能跑、能出字" |

## 对照视频的画面内容

```
0–3 s     片头
3–7.5 s   终端：A/B 两个文件的定义、提示词说明、-c 2048
7.5 s 起  A · 官方 Q4_0，预填充 534 token（6× 快进，右上角角标）
+3 s      定格：A 的 Prompt / Generation
           B · 自产 Q4_0，同一提示词（6× 快进）
+3 s      定格：B 的 Prompt / Generation
片尾 6 s  四列对照表 + 与归档值的差异说明
```

### 实测值（画面）与归档值

| | 官方 Q4_0 | 自产 Q4_0 | 画面增益 | 归档增益 |
|---|---|---|---|---|
| **2B** prefill | 10.3 | **18.9** | **+83.5%** | +87.8%（10.84 → 20.36） |
| **2B** decode | 2.9 | 2.8 | −3.4% | −1.4%（2.84 → 2.80） |
| **4B** prefill | 3.6 | **7.4** | **+105.6%** | +113.2%（3.80 → 8.10） |
| **4B** decode | 1.3 | 1.4 | +7.7% | +8.3%（1.32 → 1.43） |

画面值比归档值低 5~9%，原因是录制本身有开销：`grim` 每帧约 120 ms，按 0.35 s 一帧抓，
约占 1/3 个核（4 核里）。两个模型同向受影响，所以**比值仍然对得上**（2B 1.83× vs 归档 1.88×，
4B 2.06× vs 2.13×）。片尾卡上印了这条说明。

## 复现

```bash
# 在 K1 上：自动开终端、抓帧、编码（2B 约 4 分钟，4B 约 10 分钟）
bash tools/record_ab.sh /tmp/k1_ab_2b.mp4 2b 0.23
bash tools/record_ab.sh /tmp/k1_ab_4b.mp4 4b 0.23

# 在本机合成（片头 + 6× 快进 + 定格 + 片尾）
python tools/make_cards_ab.py 2b
python tools/compose_ab.py --video /tmp/k1_ab_2b.mp4 \
    --phases /tmp/cie_phases_2b.log --speed 6 \
    --title tools/card_title_2b.png --end tools/card_end_2b.png \
    --out docs/demo/k1-2b-ab.mp4
```

`compose_ab.py` 读取 `demo_ab.sh` 写入的阶段时间戳（`/tmp/cie_phases.log`），按真实时间剪辑，
所以快进是准确的 N 倍，不是估算；帧率也用「帧数 ÷ 实测耗时」反算，不做固定帧率假设。

## 录制环境上的三个硬约束

1. **必须指定 `-c 2048`**。不指定时 llama-cli 按模型默认的长上下文分配 KV：4B 一次吃到
   **7.19 GB RSS**，7.8 GB 的机器被 OOM killer 杀掉（日志里显示"已杀死"）。加 `-c 2048` 后
   峰值降到 **2.69 GB**。2B 侥幸没被杀，但同样超标。
2. **终端字号 22 + DejaVu Sans Mono**。字号小则缩到 1280 宽后不可读；而 `Noto Sans Mono CJK SC`
   会让 qterminal 报 "Using a variable-width font"，导致画面出现重复行。
3. **窗口尺寸靠 profile 的 `size=@Size(1920 996)`**。`LastWindowMaximized=true` 对 `-e` 启动不生效，
   `wlrctl toplevel maximize` 在没有焦点时也不生效——profile 里的 `size` 键才是可靠办法
   （注意文件末尾还有一行 `size=0` 会覆盖它，必须一并改掉）。

## 已知限制

- 帧率约 2.7 fps（`grim` 单帧 120 ms + 0.23 s 间隔），6× 快进后约 16 fps，静态画面够用；
  正常速度段会明显卡顿，所以正片只放快进段。
- 无音频、无鼠标指针（脚本预置，不在 GUI 里交互）。
- `wf-recorder` 未安装（sudo 需密码），拿不到 30 fps 原生录屏。
