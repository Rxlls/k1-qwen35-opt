"""对照视频的片头 / 片尾卡片（数据取本次实录画面值，并注明与归档值的差异来源）。"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BLUE = (30, 79, 168)
INK = (26, 34, 48)
GRAY = (74, 85, 104)
LIGHT = (232, 239, 248)
RED = (192, 57, 43)

BOLD = "C:/Windows/Fonts/msyhbd.ttc"
REG = "C:/Windows/Fonts/msyh.ttc"


def f(p, s):
    return ImageFont.truetype(p, s)


def base():
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 10, H], fill=BLUE)
    d.rectangle([0, 0, W, 6], fill=BLUE)
    return img, d


def title(path):
    img, d = base()
    d.text((84, 130), "对照实验", font=f(BOLD, 76), fill=INK)
    d.text((86, 240), "同一段 534 token 提示词 · 官方 Q4_0 vs 自产 Q4_0", font=f(REG, 30), fill=GRAY)
    d.line([86, 306, 700, 306], fill=BLUE, width=4)
    d.text((86, 348), "K1 · Bianbu 2.3.5 · riscv64 · 4 核 1.6 GHz · llama.cpp 0.1.1",
           font=f(REG, 24), fill=GRAY)
    d.text((86, 396), "只换 GGUF 文件，运行时、线程数、参数完全相同", font=f(REG, 24), fill=GRAY)
    d.text((86, 444), "计时段为 4× 快进，结果帧为实时画面", font=f(REG, 24), fill=GRAY)
    d.text((86, H - 96), "全国 RISC-V 高水平创新及应用大赛 · 进迭时空赛题",
           font=f(REG, 20), fill=(140, 152, 168))
    img.save(path)
    return path


def end(path, prompt_a="9.8", prompt_b="17.7", gen_a="2.6", gen_b="2.7", gain="+80.6%"):
    img, d = base()
    d.text((84, 70), "对照结果", font=f(BOLD, 54), fill=INK)
    d.text((86, 148), "同一提示词、同一运行时，只替换量化文件", font=f(REG, 26), fill=GRAY)

    # 四列：型号 / prefill / decode / 相对提升
    d.text((430, 196), "prefill（Prompt）", font=f(REG, 21), fill=GRAY)
    d.text((650, 196), "decode（Generation）", font=f(REG, 21), fill=GRAY)
    d.text((890, 196), "相对 A", font=f(REG, 21), fill=GRAY)

    rows = [("A · 官方 Q4_0", prompt_a, gen_a, "—", GRAY),
            ("B · 自产 Q4_0", prompt_b, gen_b, gain, BLUE)]
    y = 228
    for name, pv, gv, gain_txt, col in rows:
        d.rectangle([86, y, W - 86, y + 104], fill=LIGHT)
        d.rectangle([86, y, 92, y + 104], fill=col)
        d.text((118, y + 32), name, font=f(BOLD, 28), fill=col)
        d.text((430, y + 24), pv, font=f(BOLD, 46), fill=INK)
        d.text((430 + 22 * len(pv) + 12, y + 44), "t/s", font=f(REG, 22), fill=GRAY)
        d.text((650, y + 34), gv, font=f(REG, 34), fill=INK)
        d.text((650 + 22 * len(gv) + 10, y + 46), "t/s", font=f(REG, 20), fill=GRAY)
        d.text((890, y + 30), gain_txt, font=f(BOLD, 42 if gain_txt != "—" else 34),
               fill=RED if gain_txt != "—" else (150, 160, 175))
        y += 120

    d.text((86, 496), "注：录制时每 0.14 s 抓一帧、约占 1 核，绝对值低于无录制归档值"
                      "（10.84 → 20.36，+87.8%）；", font=f(REG, 19), fill=(140, 152, 168))
    d.text((86, 524), "      decode 基本不变（2.6 / 2.7），收益集中在 prefill —— 与机制分析一致。",
           font=f(REG, 19), fill=(140, 152, 168))
    d.text((86, H - 92), "归档：results/bench_2b_q4_0_self_191113.txt · docs/技术文档.md §8.1",
           font=f(REG, 20), fill=(140, 152, 168))
    img.save(path)
    return path


if __name__ == "__main__":
    print(title("tools/card_title_ab.png"))
    print(end("tools/card_end_ab.png"))
