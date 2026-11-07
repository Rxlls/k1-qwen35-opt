# 演示素材

本目录供 README 引用，全部来自本项目的 K1 实机测量，未做数值改写。

| 文件 | 内容 | 来源 |
|---|---|---|
| `00-k1-device.png` | **设备外观**：K1 笔记本（MUSE Book）整机 | `00-k1-device.avif`（转存为 PNG） |
| `01-k1-terminal.png` | **实机终端截屏**：同一条 `llama-bench` 命令下官方 GGUF 与自产 GGUF 的 pp512 / tg64 原始输出 | `docs/figs/demo/raw/bench2b_raw.png` |
| `02-prefill-gain.png` | prefill 吞吐柱状图：2B 10.84 → 20.36（+87.8%）、4B 3.80 → 8.10（+113.2%） | `docs/figs/fig1_core_gain.png` |
| `03-context-decay.png` | 0～32K 长上下文吞吐衰减曲线 | `docs/figs/fig2_context_decay.png` |
| `04-ime-whitelist.png` | 量化类型是否命中 IME 白名单的二元判定 | `docs/figs/fig3_whitelist.png` |
| `05-thread-scaling.png` | 线程数与吞吐/温度的关系 | `docs/figs/fig4_threads.png` |

## 关于图片口径

- `00-k1-device.png` 为设备外观图，由同目录 `00-k1-device.avif` 转存为 PNG（便于 GitHub 直接显示）；AVIF 为原始文件。
- `01-k1-terminal.png` 是 K1 桌面（Bianbu 2.3.5 LXQt / Wayland）的**原始终端截屏**，
  `docs/figs/demo/raw/` 下另有同批次其余原始截屏。
- `02`～`05` 为根据 `results/` 实测数据绘制的图表，非设备照片。

MUSE Pi Pro 与 MUSE Book 同为 K1 开发板的整机形态，本项目全部实测在 K1 笔记本（MUSE Book）上完成。

## 演示视频

成片位于 [`docs/demo/k1-demo-final.mp4`](../docs/demo/k1-demo-final.mp4)：1920×1080、3 分 31 秒、
中文旁白，内容为交付包自检 → 2B/4B 官方与自产对照 → 多轮检查点复用 → 32K 长上下文记录 → 结果边界。
计算段按 8～16 倍快进，画面内数字由 `llama-bench` 实时输出；录屏抓帧约占 4% CPU，
故画面数值略低于技术文档中的权威值，两个口径已在文档与视频说明中分别注明。
