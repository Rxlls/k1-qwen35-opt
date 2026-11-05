#!/usr/bin/env python3
"""compose_video.py — 把分段录屏剪成提交用的演示视频

结构：片头卡 → 部署自检 → 2B 对照 → 4B 对照 → 多轮复用 → 长上下文 → 片尾卡
每段按阶段日志（毫秒时间戳）精确切分；计算段加速并标注倍数；结果段定格可读。
输出 1920x1080 / 30fps / H.264。
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30
IN = "C:/Users/RX/AppData/Local/Temp/vid"
WORK = "C:/Users/RX/AppData/Local/Temp/compose"
OUT = "docs/demo/k1-demo-final.mp4"

FONT_CN = "C:/Windows/Fonts/msyhbd.ttc"
FONT_EN = "C:/Windows/Fonts/arialbd.ttf"

# 录屏画面里要去掉的部分：顶部标签栏 34px、底部任务栏
CROP = "scale=1920:1080"          # 整屏保留 shell 外框，不再裁切放大


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("命令失败:", " ".join(cmd)[:300])
        print(r.stderr[-800:])
        sys.exit(1)


def phases(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        k, v = line.split()
        d[k] = int(v)
    base = d["CAP_START"]
    return {k: (v - base) / 1000.0 for k, v in d.items()}


def card(title, lines, out, accent="#2ea3f2"):
    """标题卡：水平居中；标题可用 \\n 分行，过长时自动收字号以保住两侧安全边距。"""
    img = Image.new("RGB", (W, H), "#0d1117")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=accent)

    MARGIN = 140                      # 左右安全边距
    usable = W - 2 * MARGIN
    tl = title.split("\n")
    ts = 96
    while ts > 48:
        f1 = ImageFont.truetype(FONT_CN, ts)
        if max(f1.getbbox(t)[2] for t in tl) <= usable:
            break
        ts -= 2
    f1 = ImageFont.truetype(FONT_CN, ts)   # 循环结束时未创建/需按最终字号重建
    f2 = ImageFont.truetype(FONT_CN, 48)
    if ts < 96:
        print("  卡片字号自适应：%d → %d（最长行 %d px）"
              % (96, ts, max(f1.getbbox(t)[2] for t in tl)))

    th = int(ts * 1.22)               # 标题行高
    lh = 76
    total = th * len(tl) + 40 + len(lines) * lh
    y = (H - total) // 2
    for t in tl:
        d.text(((W - f1.getbbox(t)[2]) // 2, y), t, font=f1, fill="#ffffff")
        y += th
    y += 40
    for ln in lines:
        d.text(((W - f2.getbbox(ln)[2]) // 2, y), ln, font=f2, fill="#c9d1d9")
        y += lh
    img.save(out)
    print("  卡片:", os.path.basename(out), title.replace("\n", " / "))


def seg(src, start, end, speed, out, label=None, crop=True):
    dur = end - start
    vf = [CROP] if crop else ["scale=1920:1080"]
    if speed != 1:
        vf.append("setpts=PTS/%.3f" % speed)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % start, "-i", src,
           "-t", "%.3f" % dur, "-vf", ",".join(vf), "-r", str(FPS),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-an", out]
    sh(cmd)
    print("  片段: %-28s %5.1fs → %.1fs" % (os.path.basename(out), dur, dur / speed))


def hold(src, t, dur, out, crop=True):
    vf = CROP if crop else "scale=1920:1080"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % t, "-i", src,
        "-frames:v", "1", "-vf", vf, "-r", str(FPS), os.path.join(WORK, "_hold.png")])
    sh(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", os.path.join(WORK, "_hold.png"),
        "-t", "%.2f" % dur, "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-an", out])
    print("  定格: %-28s %.1fs" % (os.path.basename(out), dur))


def cardclip(png, dur, out):
    sh(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-t", "%.2f" % dur,
        "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an", out])


def main():
    os.makedirs(WORK, exist_ok=True)
    clips = []

    def add(p):
        clips.append(p)

    # ---- 片头 ----
    card("把权重压进 IME\nK1 上的 Qwen3.5 加速",
         ["进迭时空 K1 · 8×X60 @1.6 GHz · 8 GB",
          "统一 Q4_0 量化：命中 IME 定点通路",
          "2B prefill +87.8%   ·   4B +113.2%"],
         os.path.join(WORK, "c0.png"))
    p = os.path.join(WORK, "c0.mp4"); cardclip(os.path.join(WORK, "c0.png"), 6, p); add(p)

    # ---- 1 部署自检 ----
    ph = phases(os.path.join(IN, "phases_seg1_deploy.log"))
    seg(os.path.join(IN, "seg1_deploy.mp4"), 2.0, ph["D_START"] + 0.3, 1, os.path.join(WORK, "s1a.mp4"))
    add(os.path.join(WORK, "s1a.mp4"))
    seg(os.path.join(IN, "seg1_deploy.mp4"), ph["D_START"] + 0.3, ph["D_DONE"] + 4.5, 1, os.path.join(WORK, "s1b.mp4"))
    add(os.path.join(WORK, "s1b.mp4"))

    # ---- 2/3 对照 ----
    for tag, src, ph_path, label in [
        ("2b", os.path.join(IN, "seg2_2b.mp4"), os.path.join(IN, "phases_seg2_2b.log"), "2B"),
        ("4b", os.path.join(IN, "seg3_4b.mp4"), os.path.join(IN, "phases_seg3_4b.log"), "4B"),
    ]:
        if not os.path.exists(src):
            print("跳过（文件不存在）:", src); continue
        ph = phases(ph_path)
        cp = os.path.join(WORK, "cap_%s.png" % tag)
        card("%s 对照" % label, ["同一段 534 token 提示词，同一运行时",
                                 "官方 GGUF（混合精度） vs 自产 GGUF（统一 Q4_0）",
                                 "计算段快进，数字为 llama-bench 实测"], cp)
        cpv = os.path.join(WORK, "cap_%s.mp4" % tag)
        cardclip(cp, 4, cpv); add(cpv)
        seg(src, 2.0, ph["BANNER_END"], 1.6, os.path.join(WORK, "%s_banner.mp4" % tag))
        add(os.path.join(WORK, "%s_banner.mp4" % tag))
        sp = 12 if tag == "2b" else 16
        seg(src, ph["A_START"], ph["A_DONE"], sp, os.path.join(WORK, "%s_a.mp4" % tag), "×%d 快进" % sp)
        add(os.path.join(WORK, "%s_a.mp4" % tag))
        hold(src, ph["A_DONE"] - 0.4, 4.0, os.path.join(WORK, "%s_ah.mp4" % tag))
        add(os.path.join(WORK, "%s_ah.mp4" % tag))
        seg(src, ph["B_START"], ph["B_DONE"], sp, os.path.join(WORK, "%s_b.mp4" % tag), "×%d 快进" % sp)
        add(os.path.join(WORK, "%s_b.mp4" % tag))
        hold(src, ph["B_DONE"] - 0.4, 5.0, os.path.join(WORK, "%s_bh.mp4" % tag))
        add(os.path.join(WORK, "%s_bh.mp4" % tag))

    # ---- 4 多轮复用 ----
    if os.path.exists(os.path.join(IN, "seg4_mt.mp4")):
        ph = phases(os.path.join(IN, "phases_seg4_mt.log"))
        seg(os.path.join(IN, "seg4_mt.mp4"), 2.0, ph["BANNER_END"], 1.6, os.path.join(WORK, "s4a.mp4"))
        add(os.path.join(WORK, "s4a.mp4"))
        seg(os.path.join(IN, "seg4_mt.mp4"), ph["M_START"], ph["M_END"], 2, os.path.join(WORK, "s4b.mp4"), "×2 快进")
        add(os.path.join(WORK, "s4b.mp4"))
        hold(os.path.join(IN, "seg4_mt.mp4"), ph["M_END"] - 0.4, 5.0, os.path.join(WORK, "s4c.mp4"))
        add(os.path.join(WORK, "s4c.mp4"))

    # ---- 5 长上下文 ----
    if os.path.exists(os.path.join(IN, "seg5_32k.mp4")):
        ph = phases(os.path.join(IN, "phases_seg5_32k.log"))
        seg(os.path.join(IN, "seg5_32k.mp4"), ph["BANNER_END"], ph["K_END"] - 0.5, 1.4, os.path.join(WORK, "s5a.mp4"))
        add(os.path.join(WORK, "s5a.mp4"))

    # ---- 片尾 ----
    card("结果与边界",
         ["prefill  +87.8%（2B） / +113.2%（4B）",
          "首字延迟 −44% / −52%",
          "32K 仍有效：保持率 24.9% / 21.1%",
          "decode 受带宽限制，未突破 —— 已在文档中如实记录"],
         os.path.join(WORK, "c9.png"), accent="#3fb950")
    p = os.path.join(WORK, "c9.mp4"); cardclip(os.path.join(WORK, "c9.png"), 9, p); add(p)

    # ---- 拼接 ----
    lst = os.path.join(WORK, "list.txt")
    with open(lst, "w", encoding="utf-8") as fp:
        for c in clips:
            fp.write("file '%s'\n" % c)
    sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
        "-c", "copy", "-movflags", "+faststart", OUT])
    size = os.path.getsize(OUT) / 1048576
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", OUT], capture_output=True, text=True).stdout.strip()
    print("\n成片: %s  %.2f MB  %s 秒" % (OUT, size, dur))


if __name__ == "__main__":
    main()
