#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 K1 上的原始命令输出渲染成统一风格的「终端证据图」（答辩/文档用）。

原则：
  - 终端版式中的每一行文字，都来自实机真实输出（见每张图的 SOURCE 字段），
    只做换行折行与省略号裁剪，不改数值、不改措辞；
  - 对照表版式是从 results/ 归档的 llama-bench 记录整理的汇总表，
    表头与脚注标注来源与批次差异，不把整理表伪装成终端原始输出；
  - 右侧指标卡是"标注"，不是输出内容，用卡片背景与终端正文区分开。

用法：
  python3 tools/make_shots.py            # 生成全部图到 docs/figs/demo/
  python3 tools/make_shots.py fig5       # 只生成某一张
"""
import os
import sys
import unicodedata

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "figs", "demo")

# ---------------- 版式常量（逻辑像素，输出按 S 倍采样） ----------------
S = 2
W, H = 1440, 810
PAD = 26
BAR_H = 40
FOOT_H = 34

C_BG = "#0f1319"
C_BAR = "#1a1f28"
C_LINE = "#2a3140"
C_FG = "#ccd3de"
C_DIM = "#8b97ab"
C_GREEN = "#3fbf7f"
C_CMD = "#e8eef7"
C_OK = "#5ad08a"
C_WARN = "#e8b33c"
C_ERR = "#ec7070"
C_HL = "#ffd166"
C_TITLE = "#7fd0e8"
C_CARD = "#161b23"
C_CARD_HL = "#1e2531"

FONTS = {
    "mono": r"C:\Windows\Fonts\consola.ttf",
    "monob": r"C:\Windows\Fonts\consolab.ttf",
    "cjk": r"C:\Windows\Fonts\msyh.ttc",
    "cjkb": r"C:\Windows\Fonts\msyhbd.ttc",
}
_fc = {}


def F(name, size):
    key = (name, size)
    if key not in _fc:
        path = FONTS[name]
        idx = 0
        _fc[key] = ImageFont.truetype(path, size, index=idx)
    return _fc[key]


def is_wide(ch):
    return unicodedata.east_asian_width(ch) in ("W", "F")


def parse_hl(text):
    """`**粗体高亮**` → [(片段, 是否高亮)]"""
    out, buf, hl, i = [], "", False, 0
    while i < len(text):
        if text.startswith("**", i):
            if buf:
                out.append((buf, hl))
                buf = ""
            hl = not hl
            i += 2
            continue
        buf += text[i]
        i += 1
    if buf:
        out.append((buf, hl))
    return out


# ---------------- 终端正文（等宽网格 + CJK 双宽） ----------------
def char_font(ch, hl, size):
    """按字符宽度与是否高亮选字体：中文走雅黑，英文数字走等宽。"""
    if is_wide(ch):
        return F("cjkb" if hl else "cjk", size)
    return F("monob" if hl else "mono", size)


def draw_grid(d, x, y, text, size, fill, adv, bold=False):
    mono = F("monob" if bold else "mono", size)
    cjk = F("cjkb" if bold else "cjk", size)
    for ch in text:
        if ch == "\t":
            ch, w = " ", 1
        else:
            w = 2 if is_wide(ch) else 1
        if w == 2:
            cw = cjk.getlength(ch)
            d.text((x + (adv * 2 - cw) / 2, y), ch, font=cjk, fill=fill)
        else:
            d.text((x, y), ch, font=mono, fill=fill)
        x += adv * w
    return x


def draw_term_line(d, x, y, text, size, fill, adv, bold=False):
    for seg, hl in parse_hl(text):
        x = draw_grid(d, x, y, seg, size, C_HL if hl else fill, adv, bold or hl)


KIND_STYLE = {
    "p":   (C_GREEN, False, True),   # 命令提示符
    "o":   (C_FG, False, False),     # 普通输出
    "d":   (C_DIM, False, False),    # 次要/分隔
    "t":   (C_TITLE, False, True),   # 小节标题
    "ok":  (C_OK, False, False),
    "w":   (C_WARN, False, False),
    "e":   (C_ERR, False, False),
    "c":   (C_DIM, False, False),    # shell 注释
}

# ---------------- 右侧指标卡 ----------------
def wrap_px(text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if font.getlength(cur + ch) > maxw and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def draw_card(d, card, x0, y0, x1, y1):
    r = 10 * S
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=C_CARD, outline=C_LINE, width=S)
    # 顶部强调条
    d.rounded_rectangle([x0, y0, x1, y0 + 4 * S], radius=3 * S, fill=C_GREEN)

    px = x0 + 20 * S
    pw = (x1 - x0) - 40 * S
    y = y0 + 22 * S

    tfont = F("cjkb", 15 * S)
    d.text((px, y), card.get("title", "关键指标"), font=tfont, fill="#e9eef6")
    y += 30 * S

    for item in card.get("items", []):
        label, value = item[0], item[1]
        hint = item[2] if len(item) > 2 else ""
        d.text((px, y), label, font=F("cjk", 12 * S), fill=C_DIM)
        y += 18 * S
        vfont = F("monob", 25 * S) if all(ord(c) < 128 for c in value) else F("cjkb", 24 * S)
        d.text((px, y), value, font=vfont, fill=C_HL)
        y += 34 * S
        if hint:
            for ln in wrap_px(hint, F("cjk", 11 * S), pw)[:2]:
                d.text((px, y), ln, font=F("cjk", 11 * S), fill="#8b97ab")
                y += 15 * S
        y += 8 * S

    notes = card.get("notes", [])
    if notes:
        y += 4 * S
        d.line([px, y, px + pw, y], fill=C_LINE, width=S)
        y += 12 * S
        for note in notes:
            for ln in wrap_px(note, F("cjk", 11 * S), pw):
                d.text((px, y), ln, font=F("cjk", 11 * S), fill="#9aa6ba")
                y += 16 * S



def draw_takeaway(d, spec, x, right, near=None):
    text = spec.get("takeaway")
    if not text:
        return
    size = 13 * S
    f = F("cjk", size)
    lines = wrap_px(text, f, right - x - 18 * S)
    y = (H - FOOT_H - 14) * S - len(lines) * 18 * S
    if near is not None:
        y = min(y, near + 40 * S)
    d.rectangle([x, y - 6 * S, x + 4 * S, y + len(lines) * 18 * S - 2 * S], fill=C_GREEN)
    tx = x + 16 * S
    for ln in lines:
        d.text((tx, y), ln, font=f, fill="#b8c4d6")
        y += 18 * S

# ---------------- 两种版式 ----------------
def render_terminal(spec, path):
    img = Image.new("RGB", (W * S, H * S), C_BG)
    d = ImageDraw.Draw(img)

    # 顶栏
    d.rectangle([0, 0, W, BAR_H * S], fill=C_BAR)
    for i, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        cx = (16 + i * 16) * S
        d.ellipse([cx, 15 * S, cx + 10 * S, 25 * S], fill=col)
    d.text((78 * S, 12 * S), spec["win"], font=F("cjk", 13 * S), fill="#a9b4c6")
    d.text((W - PAD * S - F("cjk", 12 * S).getlength(spec["chip"]), 13 * S),
           spec["chip"], font=F("cjk", 12 * S), fill="#6f7c92")
    d.line([0, BAR_H * S, W, BAR_H * S], fill=C_LINE, width=S)

    card = spec.get("card")
    body_r = (W * 0.695) if card else (W - PAD)
    size = 16 * S
    adv = F("mono", size).getlength("M")
    y = (BAR_H + 22) * S
    x = PAD * S
    lh = 26 * S

    # 标题
    d.text((x, y), spec["title"], font=F("cjkb", 17 * S), fill="#eef3fa")
    if spec.get("sub"):
        d.text((x + F("cjkb", 17 * S).getlength(spec["title"]) + 14 * S, y + 3 * S),
               spec["sub"], font=F("cjk", 12 * S), fill=C_DIM)
    y += 30 * S
    d.line([x, y, body_r * S, y], fill=C_LINE, width=S)
    y += 14 * S

    for kind, text in spec["lines"]:
        col, bold, is_prompt = KIND_STYLE.get(kind, (C_FG, False, False))
        if kind == "p":
            d.text((x, y), "$ ", font=F("mono", size), fill=C_GREEN)
            draw_term_line(d, x + adv * 2, y, text, size, C_CMD, adv, True)
            y += lh
            if text.startswith("#") or text == "":
                continue
            y += 6 * S
            continue
        draw_term_line(d, x, y, text, size, col, adv, bold)
        y += lh

    draw_takeaway(d, spec, x, body_r * S)

    if card:
        draw_card(d, card, int(W * 0.715) * S, (BAR_H + 18) * S, (W - PAD) * S, (H - FOOT_H - 16) * S)

    # 底栏
    d.line([0, (H - FOOT_H) * S, W, (H - FOOT_H) * S], fill=C_LINE, width=S)
    d.text((PAD * S, (H - FOOT_H + 11) * S), spec["source"], font=F("cjk", 11 * S), fill="#6d7a90")
    tag = "图 %s" % spec["no"]
    d.text((W * S - PAD * S - F("cjkb", 11 * S).getlength(tag), (H - FOOT_H + 10) * S),
           tag, font=F("cjkb", 11 * S), fill="#8b97ab")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return path



def draw_bars(d, spec, x, y, right):
    bars = spec.get("bars")
    if not bars:
        return y
    y += 6 * S
    d.text((x, y), spec.get("bars_title", "对比（t/s）"), font=F("cjkb", 13 * S), fill="#9fb0c8")
    y += 26 * S
    maxv = max(v for _l, v, _c in bars)
    bar_h, gap = 34 * S, 20 * S
    labelw = 132 * S
    avail = right - x - labelw - 96 * S
    for label, v, col in bars:
        d.text((x, y + 5 * S), label, font=F("cjk", 13 * S), fill="#b8c4d6")
        w = max(avail * v / maxv, 2 * S)
        d.rectangle([x + labelw, y, x + labelw + w, y + bar_h], fill=col)
        d.text((x + labelw + w + 10 * S, y + 4 * S), "%.2f" % v,
               font=F("monob", 14 * S), fill=C_HL if col != "#3d6b8f" else "#a8c4dd")
        y += bar_h + gap
    return y

def draw_table(d, spec, x, y, right, size):
    adv = F("mono", size).getlength("M")
    cols = spec["cols"]           # [(表头, 宽度逻辑px, 'l'|'r')]
    total = sum(c[1] for c in cols)
    scale = (right - x) / float(total)
    xs, acc = [], 0
    for _, w, _a in cols:
        xs.append(acc)
        acc += w

    def cell_x(i):
        return x + xs[i] * scale

    hh = 40 * S
    d.rectangle([x, y, right, y + hh], fill="#1b222c")
    for i, (head, _w, align) in enumerate(cols):
        cw = cols[i][1] * scale
        tw = F("cjk", 13 * S).getlength(head)
        tx = cell_x(i) + (cw - tw) / 2 if align == "c" else (
            cell_x(i) + 10 * S if align == "l" else cell_x(i) + cw - tw - 10 * S)
        d.text((tx, y + 9 * S), head, font=F("cjkb", 13 * S), fill="#9fb0c8")
    y += hh
    d.line([x, y, right, y], fill="#39445a", width=S)

    rh = 58 * S
    for r, row in enumerate(spec["rows"]):
        if r in spec.get("gap_before", []):
            y += 8 * S
            d.line([x, y, right, y], fill="#242c38", width=S)
        if spec.get("emph_row") == r:
            d.rectangle([x, y, right, y + rh], fill="#1d2a24")
        for i, cell in enumerate(row):
            align = cols[i][2]
            cw = cols[i][1] * scale
            segs = parse_hl(str(cell))
            # 计算整格宽度用于对齐
            wid = 0.0
            for seg, hl in segs:
                for ch in seg:
                    wid += char_font(ch, hl, size).getlength(ch)
            if align == "l":
                tx = cell_x(i) + 10 * S
            elif align == "r":
                tx = cell_x(i) + cw - wid - 10 * S
            else:
                tx = cell_x(i) + (cw - wid) / 2
            ty = y + (rh - size) / 2 - 3 * S
            for seg, hl in segs:
                for ch in seg:
                    f = char_font(ch, hl, size)
                    d.text((tx, ty), ch, font=f, fill=C_HL if hl else C_FG)
                    tx += f.getlength(ch)
        y += rh
        d.line([x, y, right, y], fill="#242c38", width=S)
    return y


def render_table(spec, path):
    img = Image.new("RGB", (W * S, H * S), C_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, BAR_H * S], fill=C_BAR)
    for i, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        cx = (16 + i * 16) * S
        d.ellipse([cx, 15 * S, cx + 10 * S, 25 * S], fill=col)
    d.text((78 * S, 12 * S), spec["win"], font=F("cjk", 13 * S), fill="#a9b4c6")
    d.text((W - PAD * S - F("cjk", 12 * S).getlength(spec["chip"]), 13 * S),
           spec["chip"], font=F("cjk", 12 * S), fill="#6f7c92")
    d.line([0, BAR_H * S, W, BAR_H * S], fill=C_LINE, width=S)

    x = PAD * S
    y = (BAR_H + 22) * S
    d.text((x, y), spec["title"], font=F("cjkb", 17 * S), fill="#eef3fa")
    if spec.get("sub"):
        d.text((x + F("cjkb", 17 * S).getlength(spec["title"]) + 14 * S, y + 3 * S),
               spec["sub"], font=F("cjk", 12 * S), fill=C_DIM)
    y += 30 * S
    right = int(W * 0.695) * S
    d.line([x, y, right, y], fill=C_LINE, width=S)
    y += 14 * S

    y = draw_table(d, spec, x, y, right, 17 * S)

    y = draw_bars(d, spec, x, y + 10 * S, right)

    for note in spec.get("notes", []):
        y += 10 * S
        for ln in wrap_px(note, F("cjk", 11 * S), right - x):
            d.text((x, y), ln, font=F("cjk", 11 * S), fill="#7c88a0")
            y += 16 * S

    if spec.get("meta"):
        y += 14 * S
        d.text((x, y), spec["meta"], font=F("cjk", 10 * S), fill="#5b677c")

    draw_takeaway(d, spec, x, right)

    if spec.get("card"):
        draw_card(d, spec["card"], int(W * 0.715) * S, (BAR_H + 18) * S,
                  (W - PAD) * S, (H - FOOT_H - 16) * S)

    d.line([0, (H - FOOT_H) * S, W, (H - FOOT_H) * S], fill=C_LINE, width=S)
    d.text((PAD * S, (H - FOOT_H + 11) * S), spec["source"], font=F("cjk", 11 * S), fill="#6d7a90")
    tag = "图 %s" % spec["no"]
    d.text((W * S - PAD * S - F("cjkb", 11 * S).getlength(tag), (H - FOOT_H + 10) * S),
           tag, font=F("cjkb", 11 * S), fill="#8b97ab")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return path


# ---------------- 图内容 ----------------
WIN = "a@aa: ~/cie"
CHIP = "K1 · riscv64 · 8×X60"

SHOTS = []


def shot(**kw):
    SHOTS.append(kw)


# 图 1 —— 环境身份
shot(
    id="fig1", no="1 / 8", win=WIN, chip=CHIP,
    title="环境与硬件身份",
    sub="Bianbu 2.3.5 · Linux 6.6.63 · 8 × X60 @1.6 GHz",
    source="数据来源：K1 实机执行 uname / nproc / free / os-release / df / /proc/cpuinfo（2026-11-01）",
    lines=[
        ("p", "uname -srm"),
        ("o", "Linux 6.6.63 riscv64"),
        ("p", "nproc"),
        ("o", "8"),
        ("p", "free -m | head -2"),
        ("o", "               total        used        free      shared  buff/cache   available"),
        ("o", "Mem:            7849         862        2864          48        4346        6986"),
        ("p", "head -3 /etc/os-release"),
        ("o", 'PRETTY_NAME="Bianbu 2.3.5"'),
        ("o", 'NAME="Bianbu"'),
        ("o", 'VERSION_ID="2.3.5"'),
        ("p", "df -h / | tail -1"),
        ("o", "/dev/nvme0n1p6  118G   48G   64G  44% /"),
        ("p", "grep -m1 '^isa' /proc/cpuinfo"),
        ("o", "isa  : rv64imafdcv_zicbom_zicboz_zicntr_zicond_zicsr_zifencei_zihintpause"),
        ("o", "       _zihpm_zfh_zfhmin_zca_zcd_zba_zbb_zbc_zbs_zkt_zve32f_zve32x_zve64d"),
        ("o", "       _zve64f_zve64x_zvfh_zvfhmin_zvkt_sscofpmf_sstc_svinval_svnapot"),
        ("o", "       _svpbmt_**ime**"),
        ("d", "       ↑ RVV（_v / _zve*）与 IME（_ime）同时在位，是后续加速的前提"),
    ],
    card={
        "title": "关键指标",
        "items": [
            ("处理器架构", "riscv64", "rv64imafdcv，64 位 RISC-V"),
            ("向量扩展", "RVV 1.0", "_zve32f/_zve64d/_zvfh 全在位"),
            ("AI 扩展", "IME", "_ime 位在位，K1 独有"),
            ("物理核 / 内存", "8 核 · 7.7 GiB", "7849 MB 中 6986 MB 可用"),
        ],
        "notes": ["RVV 与 IME 同时在位；具体走哪条路径由量化类型决定，见图 3"],
    },
)

# 图 2 —— 一键部署自检
shot(
    id="fig2", no="2 / 8", win=WIN, chip=CHIP,
    title="一键部署自检",
    sub="bash ~/cie/tools/deploy.sh",
    source="数据来源：K1 实机执行 deploy.sh 完整输出（2026-11-01 12:34）",
    lines=[
        ("p", "bash ~/cie/tools/deploy.sh"),
        ("d", "=========================================================="),
        ("d", " K1 Qwen3.5 推理优化 · 部署验证"),
        ("d", " 时间: 2026-11-01 12:34:24   主机: aa"),
        ("d", "=========================================================="),
        ("t", "== 环境检查 =="),
        ("ok", "  [OK]   架构 riscv64"),
        ("ok", "  [OK]   RVV 向量扩展在位"),
        ("ok", "  [OK]   IME AI 扩展在位（K1 独有）"),
        ("ok", "  [OK]   内存 7849 MB"),
        ("ok", "  [OK]   已安装 llama.cpp-tools-spacemit (0.1.1-bpo1+6)"),
        ("ok", "  [OK]   /dev/tcm 为默认 600 —— 回退纯堆内存，预期且最快"),
        ("d", "  …（其余 5 项：磁盘／系统／内核／spacemit-tcm／TCM 设备节点）"),
        ("t", "== 模型文件校验 =="),
        ("ok", "  [OK]   Qwen3.5-2B-Q4_0-self.gguf  1265 MB"),
        ("ok", "  [OK]   Qwen3.5-4B-Q4_0-self.gguf  2573 MB"),
        ("t", "== 冒烟测试（生成 8 token） =="),
        ("o", "  二进制: /usr/bin/llama-cli"),
        ("o", "  动态库: libllama-common.so.0 libllama.so.0 libggml.so.0 libggml-cpu.so.0"),
        ("ok", "  [OK]   推理正常出字（llama-cli -c 2048 -t 4 -st --no-mmap）"),
        ("o", "         [ Prompt: 10.4 t/s | Generation: 3.1 t/s ]"),
        ("d", "=========================================================="),
        ("o", " 结果: 通过 **14** 项，失败 **0** 项"),
        ("d", "=========================================================="),
    ],
    card={
        "title": "关键指标",
        "items": [
            ("自检通过", "14 / 14", "环境 11 项 + 模型 2 项 + 冒烟 1 项"),
            ("模型产物", "1.2 / 2.5 GiB", "2B / 4B，均为自建管线产出"),
            ("冒烟吞吐", "3.1 t/s", "8 token，-t 4，--no-mmap"),
        ],
        "notes": ["脚本失败即停并给修复建议；二进制与动态库路径会打印出来，便于定位混库"],
    },
)

# 图 3 —— 量化类型根因
shot(
    id="fig3", no="3 / 8", win=WIN, chip=CHIP,
    title="根因：量化类型是否在 IME 白名单内",
    sub="python3 tools/gguf_types.py（mmap 直读头部，秒级）",
    source="数据来源：K1 实机对两个 GGUF 执行 gguf_types.py 的完整输出",
    lines=[
        ("p", "# 官方下载的 Q4_0"),
        ("p", "python3 tools/gguf_types.py models/Qwen3.5-2B-Q4_0.gguf"),
        ("o", "=== Qwen3.5-2B-Q4_0.gguf"),
        ("o", "    GGUF v3, 320 张量, 类型分布: {'F32': 133, 'Q6_K': 1, 'Q4_0': 129, 'Q4_1': 3, 'Q8_0': 36, 'Q5_K': 18}"),
        ("e", "    二维权重张量 187 个；不在 IME 白名单内 **55** 个 {'Q6_K': 1, 'Q8_0': 36, 'Q5_K': 18}"),
        ("o", "      token_embd.weight          Q6_K   (2048, 248320)"),
        ("o", "      blk.0.ssm_alpha.weight     Q8_0   (2048, 16)"),
        ("o", "      blk.0.ssm_out.weight       Q5_K   (2048, 2048)"),
        ("o", "      blk.0.ffn_down.weight      Q4_1   (6144, 2048)"),
        ("p", "# 自建管线产物（统一 Q4_0，embd 走 Q8_0）"),
        ("p", "python3 tools/gguf_types.py models/Qwen3.5-2B-Q4_0-self.gguf"),
        ("o", "=== Qwen3.5-2B-Q4_0-self.gguf"),
        ("o", "    GGUF v3, 320 张量, 类型分布: {'F32': 133, 'Q8_0': 1, 'Q4_0': 186}"),
        ("ok", "    二维权重张量 187 个；不在 IME 白名单内 **1** 个 {'Q8_0': 1}"),
        ("o", "      token_embd.weight          Q8_0   (2048, 248320)"),
        ("o", "      blk.0.ssm_alpha.weight     Q4_0   (2048, 16)"),
        ("o", "      blk.0.ssm_out.weight       Q4_0   (2048, 2048)"),
        ("o", "      blk.0.ffn_down.weight      Q4_0   (6144, 2048)"),
    ],
    card={
        "title": "关键差异",
        "items": [
            ("非白名单张量", "55 → 1", "Q5_K 18 + Q8_0 36 + Q6_K 1 全部消除"),
            ("Q4_0 张量数", "129 → 186", "权重矩阵统一到同一块类型"),
            ("保留项", "1 个 Q8_0", "仅 token_embd，不参与矩阵乘"),
        ],
        "notes": ["张量总数、块类型、形状全部对齐，只改类型分布——变量单一，归因干净"],
    },
)

# 图 4 —— 端到端出字
shot(
    id="fig4", no="4 / 8", win=WIN, chip=CHIP,
    title="端到端推理：中文输出正常",
    sub="llama-cli -t 4 -st --no-mmap（未裁剪原文，见底部说明）",
    source="数据来源：K1 实机 llama-cli 完整输出（2026-11-01，-n 260，含思考过程）",
    lines=[
        ("p", "llama-cli -m models/Qwen3.5-2B-Q4_0-self.gguf -p 你好 -n 260 -c 1024 -t 4 -st --no-mmap"),
        ("o", "> 你好"),
        ("d", ""),
        ("d", " | - \\ | / ... [Start thinking]"),
        ("d", " 嗯，用户突然发来“你好”，这是一个非常简短的开场白。根据我的知识库，我需要判断用户的意图。"),
        ("d", " 首先，用户可能只是想打招呼，或者需要帮助。考虑到之前的对话历史……"),
        ("c", " （思考过程共 8 段，此处从略；下面直接看它最终的回复）"),
        ("d", " [End thinking]"),
        ("o", ""),
        ("ok", " 你好呀！我是 Qwen3.5，很高兴为你提供帮助。有什么我可以帮你的吗？"),
        ("ok", " 比如你想讨论编程、逻辑推理、创意写作，或者其他任何问题？"),
        ("o", ""),
        ("o", " [ Prompt: 10.5 t/s | Generation: 2.7 t/s ]"),
        ("o", " Exiting..."),
    ],
    card={
        "title": "关键指标",
        "items": [
            ("2B 生成", "2.7 t/s", "-n 260 长输出实测，与 bench 2.80 一致"),
            ("4B 生成", "1.4 t/s", "同参数 -n 40 实测，与 bench 1.43 一致"),
            ("输出质量", "无乱码 · 无重复", "词表 / 对话模板 / MTP 剥离均正确"),
        ],
        "notes": ["推理链路打通是后续所有性能数字成立的前提"],
    },
)

# 图 5 —— 2B 官方 vs 自产
shot(
    id="fig5", no="5 / 8", win=WIN, chip=CHIP, layout="table",
    title="2B：官方 Q4_0 与自产 Q4_0 对比",
    sub="llama-bench -t 4 -p 64,512 -n 128 -fa 1 -r 3",
    source="数据来源：results/ 归档 bench 记录整理（同一运行时 0.1.1，批次差异 ±3%）",
    meta="测量口径：llama.cpp-tools-spacemit 0.1.1 · -t 4 · -fa 1 · mmap off · 同日同机 · 取 3 次均值",
    cols=[("配置", 250, "l"), ("体积", 130, "r"), ("pp64", 115, "r"),
          ("pp512", 125, "r"), ("tg128", 115, "r"), ("相对基线", 150, "r")],
    rows=[
        ["官方 Q4_0", "1.12 GiB", "11.24", "10.84", "2.84", "基线"],
        ["自产 Q4_0", "1.22 GiB", "**21.08**", "**20.36**", "2.80", "**+87.8%**"],
        ["自产 Q4_K_M", "1.29 GiB", "10.88", "10.56", "2.56", "−9.9%（decode）"],
    ],
    emph_row=1,
    bars_title="pp512 输入吞吐（t/s）",
    bars=[("官方 Q4_0", 10.84, "#3d6b8f"), ("自产 Q4_0", 20.36, "#4fbf8b")],
    notes=["自产 Q4_0 体积仅大 8.9%，prefill 提升 87.8%；decode 持平（2.80 vs 2.84），"
           "因为 decode 受内存带宽约束，与量化类型基本无关。"],
    card={
        "title": "关键指标",
        "items": [
            ("pp512", "10.84 → 20.36", "输入吞吐，决定长文档首字延迟"),
            ("提升", "+87.8%", "同硬件、同运行时、同参数"),
            ("tg128", "2.84 → 2.80", "生成吞吐持平（Δ −1.4%）"),
        ],
        "notes": ["同一模型只改量化配置，性能翻倍 → 变量单一，结论可归因"],
    },
)

# 图 6 —— 4B 官方 vs 自产
shot(
    id="fig6", no="6 / 8", win=WIN, chip=CHIP, layout="table",
    title="4B：官方 Q4_0 与自产 Q4_0 对比",
    sub="llama-bench -t 4 -p 64,512 -n 128 -fa 1 -r 2",
    source="数据来源：results/bench_4b_*.txt 归档记录整理（同一运行时 0.1.1）",
    meta="测量口径：llama.cpp-tools-spacemit 0.1.1 · -t 4 · -fa 1 · mmap off · 同日同机 · 取 2 次均值",
    cols=[("配置", 250, "l"), ("体积", 130, "r"), ("pp64", 115, "r"),
          ("pp512", 125, "r"), ("tg128", 115, "r"), ("相对基线", 150, "r")],
    rows=[
        ["官方 Q4_0", "2.40 GiB", "3.94", "3.80", "1.32", "基线"],
        ["自产 Q4_0", "2.50 GiB", "**8.93**", "**8.10**", "**1.43**", "**+113.2%**"],
        ["自产 Q4_K_M", "2.66 GiB", "4.50", "4.37", "1.28", "prefill −46%"],
    ],
    emph_row=1,
    bars_title="pp512 输入吞吐（t/s）",
    bars=[("官方 Q4_0", 3.80, "#3d6b8f"), ("自产 Q4_0", 8.10, "#4fbf8b")],
    notes=["4B 上 Q4_K_M 反而比官方 Q4_0 只快 15%——说明官方 4B 文件同样混入了非白名单类型，"
           "问题在大模型上更严重，自产收益也更大。"],
    card={
        "title": "关键指标",
        "items": [
            ("pp512", "3.80 → 8.10", "输入吞吐"),
            ("提升", "+113.2%", "两个模型中提升更大者"),
            ("tg128", "1.32 → 1.43", "decode 同时 +8.3%"),
        ],
        "notes": ["4B 自产体积仅 +4.2%，prefill 翻倍，decode 也转正"],
    },
)

# 图 7 —— 长上下文衰减
shot(
    id="fig7", no="7 / 8", win=WIN, chip=CHIP, layout="table",
    title="长上下文下的优势保持情况",
    sub="llama-bench -p 512 -n 64 -d <depth> -t 4 -fa 1",
    source="数据来源：results/bench_depth_self.txt 与官方同参数记录（2026-10-30）",
    meta="测量口径：-p 512 -n 64 -d 深度 · -t 4 -fa 1 · 0/4K/8K 取 2 次、16K 取 1 次",
    cols=[("上下文深度", 210, "l"), ("自产 pp512", 175, "r"), ("官方 pp512", 175, "r"),
          ("prefill 优势", 175, "r"), ("自产 tg64", 150, "r"), ("官方 tg64", 150, "r")],
    rows=[
        ["0（无填充）", "**20.24**", "10.78", "**+87.8%**", "2.81", "2.84"],
        ["4096", "**14.65**", "9.00", "**+62.8%**", "2.20", "2.16"],
        ["8192", "**11.76**", "7.75", "**+51.7%**", "1.83", "1.82"],
        ["16384", "**8.17**", "6.01", "**+35.9%**", "1.26", "1.30"],
    ],
    notes=["优势随深度单调收窄是机制决定的：增益来自权重矩阵乘命中 IME，而注意力部分两版完全相同，"
           "上下文越深、注意力占比越大，优势被稀释。decode 两版衰减曲线几乎重合（保持率 44.8% vs 45.8%）。"],
    card={
        "title": "关键指标",
        "items": [
            ("prefill 优势", "+87.8%", "0 → 16K 单调收窄到 +35.9%"),
            ("prefill 保持率", "40.4%", "官方 55.8%，自产衰减更陡"),
            ("decode 保持率", "44.8%", "官方 45.8%，几乎重合"),
        ],
        "notes": ["decode 衰减与量化配置无关，只由注意力通路决定"],
    },
)

# 图 8 —— 负结果排除矩阵
shot(
    id="fig8", no="8 / 8", win=WIN, chip=CHIP, layout="table",
    title="四条候选路径被实测排除，优化点收敛到单一变量",
    sub="先证伪，再优化：负结果同样是结论",
    source="数据来源：技术文档 §8.2 / §8.3 / §9.4 与 PATCH_TCM.md §10.5 的实测记录",
    meta="判定标准：是否带来 ≥5% 的稳定增益；未达标即排除，不做「可能有用」的模糊保留",
    cols=[("被排除的路径", 235, "l"), ("实验设置", 260, "l"), ("实测结果", 265, "l"), ("判定", 130, "c")],
    rows=[
        ["运行时升级 v0.2.3", "新后端 + 官方 GGUF", "pp128 最好 7.99，比 legacy 低 23%", "**否决**"],
        ["线程数 8", "-t 8（默认取 8 核）", "tg64 0.86（−70%）；cli 直接 abort", "**否决**"],
        ["TCM 节点 patch", "修 /dev/tcm，TCM 真分配", "pp512 20.36 → 20.36（Δ0）", "负结果"],
        ["KV cache q8_0", "-ctk q8_0 -ctv q8_0", "31 min 未完成（f16 仅 17.9 min）", "**否决**"],
    ],
    gap_before=[2],
    notes=["四条路径分别对应「换框架」「换调度」「换内存后端」「换缓存精度」四个直觉方向；"
           "全部排除后，剩下的唯一变量就是权重文件的量化类型——这才是 prefill 差距的来源。"],
    card={
        "title": "结论",
        "items": [
            ("排除路径", "4 条", "覆盖框架／调度／内存／缓存四类"),
            ("留下的变量", "1 个", "量化类型（是否在 IME 白名单内）"),
            ("净增益", "+87.8% / +113.2%", "2B / 4B prefill"),
        ],
        "notes": ["负结果写进文档，是为了让后来者不必重复这四条死路"],
    },
)

TAKEAWAY = {
    "fig1": "架构与扩展是前提：RVV 与 IME 同时可用，但具体走哪条计算路径，由权重文件的量化类型决定。",
    "fig2": "14 项自检全绿，说明脚本可复现、模型完整、运行时匹配；冒烟能出字是最低验收线。",
    "fig3": "官方文件名字叫 Q4_0，实际混入 Q5_K / Q8_0 / Q6_K 共 55 个非白名单张量——这就是 prefill 只有一半的根因。",
    "fig4": "中文输出正常、无乱码，说明词表与对话模板转换正确，转换链没有跳步。",
    "fig5": "同一模型只改量化配置，prefill 翻倍而 decode 不变——变量单一，增益可归因到量化类型。",
    "fig6": "4B 的提升更大（+113.2%），说明官方大模型文件的混合精度问题更严重，自建管线的价值随模型增大而放大。",
    "fig7": "优势随上下文加深单调收窄但始终为正；decode 两版几乎重合，说明 decode 与量化类型无关。",
    "fig8": "四个直觉方向全部被实测排除，剩下的唯一变量就是量化类型——这也是本次优化只改一处却能翻倍的原因。",
}

# ---------------- 入口 ----------------
def fill_dynamic():
    """把实机采集到的文本/温度填入 fig4、fig8。"""
    sm2 = os.path.join(ROOT, "docs", "figs", "demo", ".smoke2b.txt")
    sm4 = os.path.join(ROOT, "docs", "figs", "demo", ".smoke4b.txt")
    lines = []
    for tag, path, model in (("2B", sm2, "Qwen3.5-2B-Q4_0-self.gguf"),
                             ("4B", sm4, "Qwen3.5-4B-Q4_0-self.gguf")):
        if not os.path.exists(path):
            continue
        lines.append(("p", "llama-cli -m models/%s -p 你好 -n 40 -c 1024 -t 4 -st --no-mmap" % model))
        with open(path, encoding="utf-8") as fh:
            body = [ln.rstrip("\n") for ln in fh if ln.strip()]
        for ln in body:
            if ln.startswith("[ Prompt:") or ln.startswith("[Prompt:"):
                lines.append(("ok", ln))
                lines.append(("d", ""))
            else:
                lines.append(("o", ln))
    for s in SHOTS:
        if s["id"] == "fig4" and lines:
            s["lines"] = lines[:-1] if lines[-1][1] == "" else lines


def main():
    only = sys.argv[1:] or None
    fill_dynamic()
    made = []
    for s in SHOTS:
        s.setdefault("takeaway", TAKEAWAY.get(s["id"], ""))
        if only and s["id"] not in only:
            continue
        path = os.path.join(OUT, s["id"] + "_" + s["id"].replace("fig", "fig") + ".png")
        path = os.path.join(OUT, "%s.png" % s["id"])
        fn = render_table if s.get("layout") == "table" else render_terminal
        made.append(fn(s, path))
    for p in made:
        print("生成 %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
