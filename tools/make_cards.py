"""生成演示视频的片头 / 片尾卡片（1280x720，与 PPT 同一套配色）。"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BLUE = (30, 79, 168)
INK = (26, 34, 48)
GRAY = (74, 85, 104)
LIGHT = (232, 239, 248)

BOLD = "C:/Windows/Fonts/msyhbd.ttc"
REG = "C:/Windows/Fonts/msyh.ttc"


def f(path, size):
    return ImageFont.truetype(path, size)


def base():
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 10, H], fill=BLUE)          # 左侧竖条
    d.rectangle([0, 0, W, 6], fill=BLUE)           # 顶部细条
    return img, d


def title_card(path):
    img, d = base()
    d.text((84, 150), "K1 真机实录", font=f(BOLD, 76), fill=INK)
    d.text((86, 262), "Qwen3.5-2B · Q4_0 自产量化 · llama.cpp 0.1.1",
           font=f(REG, 30), fill=GRAY)
    d.line([86, 330, 560, 330], fill=BLUE, width=4)
    d.text((86, 372), "进迭时空 K1 · Bianbu 2.3.5 · riscv64 · 4 核 1.6 GHz",
           font=f(REG, 24), fill=GRAY)
    d.text((86, 420), "以下为本机实录，未加速；已剪去约 40 s 的模型加载段", font=f(REG, 24), fill=GRAY)
    d.text((86, H - 96), "全国 RISC-V 高水平创新及应用大赛 · 进迭时空赛题",
           font=f(REG, 20), fill=(140, 152, 168))
    img.save(path)
    return path


def end_card(path):
    img, d = base()
    d.text((84, 96), "实测结果", font=f(BOLD, 54), fill=INK)
    d.text((86, 176), "同一硬件、同一运行时，仅替换量化文件", font=f(REG, 26), fill=GRAY)

    rows = [
        ("2B", "10.84 → 20.36 t/s", "+87.8%"),
        ("4B", "3.80 → 8.10 t/s", "+113.2%"),
    ]
    y = 260
    for name, val, gain in rows:
        d.rectangle([86, y, W - 86, y + 120], fill=LIGHT)
        d.rectangle([86, y, 92, y + 120], fill=BLUE)
        d.text((120, y + 30), name, font=f(BOLD, 44), fill=BLUE)
        d.text((230, y + 38), val, font=f(REG, 32), fill=INK)
        d.text((W - 330, y + 34), gain, font=f(BOLD, 40), fill=(192, 57, 43))
        y += 140

    d.text((86, 566), "注：录制时每 0.14 s 抓一帧、约占 1 核，故画面性能行显示 2.4 t/s；无录制时实测 2.7 t/s。",
           font=f(REG, 19), fill=(140, 152, 168))
    d.text((86, H - 118), "prefill（pp512，t/s）；-t 4 -fa 1 -mmp 0 -r 3(2B)/2(4B)",
           font=f(REG, 21), fill=GRAY)
    d.text((86, H - 76), "数据归档：results/bench_2b_q4_0_self_191113.txt 等",
           font=f(REG, 21), fill=(140, 152, 168))
    img.save(path)
    return path


if __name__ == "__main__":
    out = os.path.dirname(os.path.abspath(__file__))
    print(title_card(os.path.join(out, "card_title.png")))
    print(end_card(os.path.join(out, "card_end.png")))
