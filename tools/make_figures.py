#!/usr/bin/env python3
"""生成技术文档用的 4 张图（300 dpi PNG）。

数据全部取自 docs/技术文档.md 的实测表格，不引入任何新数字。
用法: python tools/make_figures.py
输出: docs/figs/fig{1..4}_*.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import numpy as np

# ---------- 中文字体 ----------
for cand in ["C:/Windows/Fonts/msyh.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]:
    if os.path.exists(cand):
        fm.fontManager.addfont(cand)
        plt.rcParams["font.family"] = fm.FontProperties(fname=cand).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 110
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["font.size"] = 10

C_OFF = "#8d9aa5"   # 官方
C_OWN = "#c0392b"   # 自产（提升用红）
C_WARN = "#e67e22"
GRID = dict(color="#dddddd", linewidth=0.7, linestyle="--")

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "figs")
os.makedirs(OUT, exist_ok=True)


def save(fig, name):
    p = os.path.join(OUT, name)
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  ", p)


# ---------- 图 1：核心成果 ----------
def fig1():
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    groups = ["2B (pp512)", "4B (pp512)"]
    off = [10.84, 3.80]
    own = [20.36, 8.10]
    x = np.arange(len(groups))
    w = 0.34
    b1 = ax.bar(x - w / 2, off, w, label="官方 GGUF Q4_0", color=C_OFF, edgecolor="white")
    b2 = ax.bar(x + w / 2, own, w, label="自产 Q4_0", color=C_OWN, edgecolor="white")

    for b, v in zip(b1, off):
        ax.text(b.get_x() + b.get_width() / 2, v / 2, f"{v:.2f}", ha="center", va="center",
                fontsize=9.5, color="white", weight="bold")
    for b, v in zip(b2, own):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v:.2f}", ha="center",
                fontsize=9.5, color=C_OWN, weight="bold")
    for i, (o, s) in enumerate(zip(off, own)):
        ax.text(i, max(o, s) + 3.0, f"+{100*(s/o-1):.1f}%", ha="center", fontsize=13,
                color=C_OWN, weight="bold")

    ax.set_xticks(x); ax.set_xticklabels(groups)
    ax.set_ylabel("prefill 吞吐 (tokens/s)")
    ax.set_ylim(0, 26)
    ax.grid(axis="y", **GRID); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    save(fig, "fig1_core_gain.png")


# ---------- 图 2：长上下文衰减 ----------
def fig2():
    depth = [0, 4, 8, 16]
    off_pp = [10.78, 9.00, 7.75, 6.01]
    own_pp = [20.24, 14.65, 11.76, 8.17]
    off_tg = [2.84, 2.16, 1.82, 1.30]
    own_tg = [2.81, 2.20, 1.83, 1.26]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 3.2))

    a1.plot(depth, own_pp, "o-", color=C_OWN, lw=1.8, ms=5, label="自产 Q4_0")
    a1.plot(depth, off_pp, "s--", color=C_OFF, lw=1.6, ms=5, label="官方 Q4_0")
    for i, (d, v) in enumerate(zip(depth, own_pp)):
        dx = (14, 0) if i == 0 else (0, 7)
        ha = "left" if i == 0 else "center"
        a1.annotate(f"{v:.2f}", (d, v), textcoords="offset points", xytext=dx,
                    ha=ha, fontsize=8, color=C_OWN)
    a1.set_xlabel("上下文深度 (K tokens)"); a1.set_ylabel("prefill (tokens/s)")
    a1.set_title("(a) prefill：差距随深度收窄", fontsize=10)
    a1.set_xticks(depth); a1.set_ylim(0, 24); a1.set_xlim(-1.0, 17.5)
    a1.grid(**GRID); a1.set_axisbelow(True)
    for s in ("top", "right"):
        a1.spines[s].set_visible(False)
    a1.legend(frameon=False, fontsize=8.5, loc="upper right")

    a2.plot(depth, own_tg, "o-", color=C_OWN, lw=1.8, ms=5, label="自产 Q4_0")
    a2.plot(depth, off_tg, "s--", color=C_OFF, lw=1.6, ms=5, label="官方 Q4_0")
    a2.set_xlabel("上下文深度 (K tokens)"); a2.set_ylabel("decode (tokens/s)")
    a2.set_title("(b) decode：两条曲线几乎重合", fontsize=10)
    a2.set_xticks(depth); a2.set_ylim(0, 3.6); a2.set_xlim(-1.0, 17.5)
    a2.grid(**GRID); a2.set_axisbelow(True)
    for s in ("top", "right"):
        a2.spines[s].set_visible(False)
    a2.legend(frameon=False, fontsize=8.5, loc="upper right")
    a2.text(0.5, 0.18, "衰减与量化无关（两版差异 ≤3.1%）", transform=a2.transAxes,
            fontsize=8, color="#444", ha="center",
            bbox=dict(boxstyle="round,pad=0.35", fc="#f6f6f6", ec="#cccccc"))

    save(fig, "fig2_context_decay.png")


# ---------- 图 3：IME 白名单二元判定 ----------
def fig3():
    labels = ["Q4_0", "Q4_K_M", "Q3_K_M", "KV q8_0", "Q5_K_M"]
    mins = [6.9, 10.7, 20, 31, 50]
    done = [True, True, False, False, False]
    limits = [None, None, 20, 31, 50]   # 中断时刻
    temps = ["55°C+", "55°C+", "31°C", "31°C", "32°C"]

    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    y = np.arange(len(labels))[::-1]
    for yy, m, d, lim, tp in zip(y, mins, done, limits, temps):
        color = C_OWN if d else C_WARN
        ax.barh(yy, m, height=0.6, color=color, alpha=0.9 if d else 0.55,
                hatch="" if d else "///", edgecolor="white")
        txt = f"{m:.1f} min" if d else f"> {lim} min 未完成"
        ax.text(m + 1.4, yy, txt, va="center", fontsize=9,
                color="#333" if d else C_WARN, weight="normal" if d else "bold")
        ax.text(-1.5, yy, tp, va="center", ha="right", fontsize=8,
                color="#555" if d else C_WARN)

    ax.set_yticks(y); ax.set_yticklabels(labels)
    ax.set_xlabel("同一测试任务的耗时（4B，pp512 + tg128，-r 2）\n"
                  "斜纹 = 超时中断（未跑完，非真实耗时）；左侧温度：55°C+ 走 IME 向量路径，31~32°C 走通用标量路径",
                  fontsize=8.8)
    ax.set_xlim(-9.5, 66)
    ax.grid(axis="x", **GRID); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    save(fig, "fig3_whitelist.png")


# ---------- 图 4：线程数陷阱 ----------
def fig4():
    fig, ax = plt.subplots(figsize=(5.4, 3.1))
    labels = ["pp128", "tg64 (decode)"]
    t4 = [10.40, 2.84]
    t8 = [10.40, 0.86]
    x = np.arange(2); w = 0.32
    b1 = ax.bar(x - w / 2, t4, w, label="-t 4（正确）", color=C_OWN, edgecolor="white")
    b2 = ax.bar(x + w / 2, t8, w, label="-t 8（越界）", color=C_OFF, edgecolor="white")
    for b, v in list(zip(b1, t4)) + list(zip(b2, t8)):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.22, f"{v:.2f}", ha="center", fontsize=8.5)
    ax.annotate("−70%", xy=(1 + w / 2 + 0.06, 1.05), xytext=(1.46, 2.15),
                arrowprops=dict(arrowstyle="->", color=C_WARN, lw=1.4), fontsize=11,
                color=C_WARN, weight="bold", ha="center")

    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("tokens/s"); ax.set_ylim(0, 12.5); ax.set_xlim(-0.6, 1.75)
    ax.grid(axis="y", **GRID); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    save(fig, "fig4_threads.png")


if __name__ == "__main__":
    print("生成图表 ->", OUT)
    fig1(); fig2(); fig3(); fig4()
    print("完成")
