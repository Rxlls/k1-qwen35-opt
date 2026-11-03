"""把对照录屏剪成成片：片头 + 官方/自产两段（计时 N× 快进，由 --speed 指定）+ 结果定格 + 片尾。

用法：python tools/compose_ab.py --video /tmp/k1_ab.mp4 --phases /tmp/cie_phases.saved.log
"""
import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

SPEED = 4.0
W, H = 1280, 720
FPS = 30


def read_phases(path):
    d = {}
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            k, v = line.split()
            d[k] = int(v)
    return d


def badge(path, text="×N 快进"):
    """右上角快进角标"""
    w, h = 168, 52
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=(30, 79, 168, 235))
    f = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 28)
    box = d.textbbox((0, 0), text, font=f)
    d.text(((w - (box[2] - box[0])) / 2, (h - (box[3] - box[1])) / 2 - 4),
           text, font=f, fill=(255, 255, 255, 255))
    img.save(path)
    return path


def grab_frame(video, t, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
                    "-frames:v", "1", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="/tmp/k1_ab.mp4")
    ap.add_argument("--phases", default="/tmp/cie_phases.saved.log")
    ap.add_argument("--title", default="tools/card_title_ab.png")
    ap.add_argument("--end", default="tools/card_end_ab.png")
    ap.add_argument("--out", default="docs/demo/k1-2b-ab.mp4")
    ap.add_argument("--speed", type=float, default=4.0, help="计时段快进倍率")
    args = ap.parse_args()

    p = read_phases(args.phases)
    t0 = p["CAP_START"]

    def sec(k):
        return (p[k] - t0) / 1000.0

    ban_end = sec("BANNER_END")
    a0, a1 = sec("A_START"), sec("A_DONE")
    b0, b1 = sec("B_START"), sec("B_DONE")

    global SPEED
    SPEED = args.speed
    tmp = tempfile.mkdtemp(prefix="ab_")
    bd = badge(os.path.join(tmp, "badge.png"), "×%g 快进" % SPEED)
    fa = grab_frame(args.video, a1 + 1.2, os.path.join(tmp, "freeze_a.png"))
    fb = grab_frame(args.video, b1 + 1.0, os.path.join(tmp, "freeze_b.png"))

    fc = (
        f"[0:v]scale={W}:{H},fps={FPS},setsar=1,trim=duration=3,setpts=PTS-STARTPTS[t];"
        f"[1:v]trim=0:{ban_end:.3f},setpts=PTS-STARTPTS,scale={W}:{H},fps={FPS},setsar=1[ban];"
        f"[1:v]trim={a0:.3f}:{a1:.3f},setpts=(PTS-STARTPTS)/{SPEED},scale={W}:{H},fps={FPS},setsar=1[ar];"
        f"[ar][5:v]overlay=W-w-36:36[ao];"
        f"[2:v]scale={W}:{H},fps={FPS},setsar=1,trim=duration=3,setpts=PTS-STARTPTS[ah];"
        f"[1:v]trim={b0:.3f}:{b1:.3f},setpts=(PTS-STARTPTS)/{SPEED},scale={W}:{H},fps={FPS},setsar=1[br];"
        f"[br][5:v]overlay=W-w-36:36[bo];"
        f"[3:v]scale={W}:{H},fps={FPS},setsar=1,trim=duration=3,setpts=PTS-STARTPTS[bh];"
        f"[4:v]scale={W}:{H},fps={FPS},setsar=1,trim=duration=6,setpts=PTS-STARTPTS[e];"
        f"[t][ban][ao][ah][bo][bh][e]concat=n=7:v=1:a=0[v]"
    )

    cmd = ["ffmpeg", "-y", "-v", "error",
           "-loop", "1", "-t", "3", "-i", args.title,
           "-i", args.video,
           "-loop", "1", "-t", "3", "-i", fa,
           "-loop", "1", "-t", "3", "-i", fb,
           "-loop", "1", "-t", "6", "-i", args.end,
           "-loop", "1", "-t", "1", "-i", bd,
           "-filter_complex", fc, "-map", "[v]",
           "-c:v", "libx264", "-crf", "22", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out]
    subprocess.run(cmd, check=True)

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", args.out],
                         capture_output=True, text=True).stdout.strip()
    print("片头 3s ｜ 说明段 %.1fs ｜ A %.1fs→%.1fs(%.0f×) ｜ B %.1fs→%.1fs(%.0f×) ｜ 片尾 6s"
          % (ban_end, a0, a1, SPEED, b0, b1, SPEED))
    print("输出 %s，时长 %ss，%.0f KB" % (args.out, dur, os.path.getsize(args.out) / 1024))


if __name__ == "__main__":
    main()
