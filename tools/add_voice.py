#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给演示视频配旁白（edge-tts）。

- 逐句合成后按时间戳铺到时间轴上，句子之间不重叠
- 某句超出可用时长时用 atempo 微调（上限 1.15×），仍超出则报错退出
- 输出带音轨的成片；无音轨母版另存一份便于回退

用法：
    python tools/add_voice.py                     # 默认 YunyangNeural
    python tools/add_voice.py --voice zh-CN-YunxiNeural
    python tools/add_voice.py --list              # 只列出旁白文本与时长预算
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs/demo/k1-demo-silent.mp4")
OUT = os.path.join(ROOT, "docs/demo/k1-demo-final.mp4")
WORK = "C:/Users/RX/AppData/Local/Temp/voice"

VOICE = "zh-CN-YunxiNeural"          # 云希·阳光男声（比新闻腔更亲和）
RATE = "+0%"

# (起始秒, 旁白)。文字是"读出来的稿子"，Q4_0 写成"Q4 零"才会被读成 Q4 零而非下划线。
LINES = [
    # 发音实测（2026-11-06，云希）：
    #   "32K" 被逐位读成"三二K" → 必须写"三十二K"
    #   "两B"/"2B" 的 B 按拼音读作 bì（与"两臂"时长完全一致）→ 改用"二十亿/四十亿"
    #   "K1" 读作"K一"、Qwen3.5 读作"Qwen 三点五"、prefill/decode 按英文词读，均正确
    (0.5,   "在进迭时空 K1 上，我们把 Qwen三点五的权重统一压成 Q4零。"),
    (8.0,   "先看交付包：解压之后直接跑自检，十一项全部通过。"),
    (14.0,  "接下来是二十亿的对照：同一段提示词，同一个运行时，只换量化文件。"),
    (22.0,  "左边是官方发布的文件，右边是我们自己量化的。计算过程快进。"),
    (42.9,  "官方的二十亿模型是 10.78。"),
    (47.5,  "换成自产文件。"),
    (56.0,  "自产 20.24，提升 87.8%。"),
    (60.9,  "差别不在体积，而在张量类型有没有命中 IME 白名单。"),
    (68.2,  "同样的方法用在四十亿上。"),
    (72.5,  "四十亿这一段比较慢，快进十六倍；它的权重是二十亿的两倍，每一步都更慢。"),
    (107.0, "官方四十亿跑出 3.80。"),
    (111.5, "自产文件跑同一段提示词。"),
    (126.0, "自产 8.10，提升 113.2%。模型越大，矩阵乘占比越高，增益也更大。"),
    (135.0, "多轮对话时，运行时会保存上下文检查点。"),
    (145.0, "第二轮直接复用了上一轮，从 30 秒降到 12 秒。"),
    (155.0, "但每个检查点约二十兆，粒度不可能更细。"),
    (178.5, "三十二K输入也能跑，prefill 保持率 24.9%；但首字要 67 分钟。"),
    (188.0, "这一段是原始记录回放，实际跑了七十分钟。"),
    (200.6, "总结：prefill 提升近九成和一倍，首字延迟降四到五成；"
            "decode 受带宽限制，已在文档中如实记录。"),
]


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write("命令失败: %s\n%s\n" % (" ".join(map(str, cmd)), r.stderr[-800:]))
        raise SystemExit(1)
    return r


def dur(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=nw=1:nk=1", path]).stdout.strip())


def synth(text, voice, rate, out):
    key = hashlib.sha1((text + voice + rate).encode("utf-8")).hexdigest()[:16]
    cached = os.path.join(WORK, "clip_%s.mp3" % key)
    if os.path.exists(cached) and dur(cached) > 0.2:
        sh(["cp", "-f", cached, out])
        return out
    sh([sys.executable, "-m", "edge_tts", "--voice", voice, "--rate", rate,
        "--text", text, "--write-media", out])
    sh(["cp", "-f", out, cached])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--rate", default=RATE)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default=OUT, help="输出路径（默认覆盖成片）")
    args = ap.parse_args()

    if not os.path.exists(SRC):
        sys.stderr.write("找不到无音轨母版：%s\n先跑 tools/compose_video.py\n" % SRC)
        raise SystemExit(1)

    total = dur(SRC)
    os.makedirs(WORK, exist_ok=True)
    print("母版 %.1f s，旁白 %d 句，音色 %s" % (total, len(LINES), args.voice))

    prepared = []
    for i, (start, text) in enumerate(LINES):
        nxt = LINES[i + 1][0] if i + 1 < len(LINES) else total
        budget = nxt - start - 0.35          # 句间留 0.35 s 气口
        mp3 = os.path.join(WORK, "line%02d.mp3" % i)
        synth(text, args.voice, args.rate, mp3)
        d = dur(mp3)
        speed = 1.0
        if d > budget:
            speed = min(1.15, d / budget)
            if d / speed > budget + 0.05:
                sys.stderr.write("第 %d 句放不下：%.1fs > 预算 %.1fs\n  %s\n"
                                 % (i + 1, d, budget, text))
                raise SystemExit(2)
        print("  %2d  %5.1fs 起  时长 %4.1fs  预算 %4.1fs  %s"
              % (i + 1, start, d, budget, ("提速 %.2f×" % speed) if speed > 1 else ""))
        prepared.append((start, mp3, speed, d))

    if args.list:
        return

    # 逐句延迟叠加到静音底上
    inputs = ["-f", "lavfi", "-t", "%.3f" % total, "-i", "anullsrc=r=48000:cl=stereo"]
    for _, mp3, _, _ in prepared:
        inputs += ["-i", mp3]
    fc = []
    for i, (start, mp3, speed, d) in enumerate(prepared, start=1):
        chain = "[%d:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo" % i
        if speed > 1.0:
            chain += ",atempo=%.4f" % speed
        chain += ",adelay=%d|%d[a%d]" % (int(start * 1000), int(start * 1000), i)
        fc.append(chain)
    mix_in = "[0:a]" + "".join("[a%d]" % i for i in range(1, len(prepared) + 1))
    fc.append("%samix=inputs=%d:duration=first:normalize=0,"
              "loudnorm=I=-16:TP=-2:LRA=11[mix]" % (mix_in, len(prepared) + 1))

    mixed = os.path.join(WORK, "mix.wav")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + inputs + \
          ["-filter_complex", ";".join(fc), "-map", "[mix]", "-ac", "2", "-ar", "48000", mixed]
    sh(cmd)
    print("混音完成：%.1f s" % dur(mixed))

    out_path = args.out
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", SRC, "-i", mixed,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out_path])
    print("成片（带旁白）：%s  %.2f MB  %.1f s"
          % (os.path.basename(out_path), os.path.getsize(out_path) / 1048576, dur(out_path)))

    with open(os.path.join(WORK, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"voice": args.voice, "rate": args.rate,
                   "lines": [{"t": s, "text": t} for s, t in LINES]},
                  f, ensure_ascii=False, indent=2)
    print("旁白稿：%s" % os.path.join(WORK, "script.json"))


if __name__ == "__main__":
    main()
