#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_review.py — 汇总多份盲评结果，输出逐题票数与一致性

用法: python analyze_review.py <目录> [--out 结果.md]
"""
import os
import re
import sys
import glob
from collections import Counter, OrderedDict

def parse(path):
    """返回 {qid: 结论} 与 汇总行"""
    res = OrderedDict()
    summary = ""
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("汇总:"):
            summary = line
            continue
        m = re.match(r"^(Q\d+)\t(\w+)\t(\S+)\t(\S+)\t(\S+)$", line)
        if m:
            qid, choice, left, right, concl = m.groups()
            res[qid] = {"choice": choice, "left": left, "right": right, "concl": concl}
    return res, summary

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    files = sorted(glob.glob(os.path.join(d, "quality_review_result_*.txt")))
    if not files:
        print("未找到评分文件"); sys.exit(1)

    reviews = []
    for f in files:
        data, summ = parse(f)
        if data:
            tag = os.path.basename(f).replace("quality_review_result_", "").replace(".txt", "")
            reviews.append({"tag": tag, "data": data, "summary": summ, "file": f})

    n = len(reviews)
    print(f"评审份数: {n}")
    print(f"题目数: {len(reviews[0]['data'])}")
    print()

    # 每份评审的汇总
    print("== 各评审汇总 ==")
    print(f"{'评审':<16}{'自产优':>7}{'官方优':>8}{'持平':>7}")
    tot_self = tot_off = tot_tie = 0
    for r in reviews:
        c = Counter(x["concl"] for x in r["data"].values())
        s, o, t = c.get("自产优", 0), c.get("官方优", 0), c.get("持平", 0)
        tot_self += s; tot_off += o; tot_tie += t
        print(f"{r['tag']:<16}{s:>7}{o:>8}{t:>7}")
    print("-" * 38)
    total = tot_self + tot_off + tot_tie
    print(f"{'合计':<16}{tot_self:>7}{tot_off:>8}{tot_tie:>7}   共 {total} 个判断")
    print(f"{'占比':<16}{tot_self/total*100:>6.1f}%{tot_off/total*100:>7.1f}%{tot_tie/total*100:>6.1f}%")
    print()

    # 逐题票数
    print("== 逐题票数 ==")
    print(f"{'题号':<6}{'自产优':>7}{'官方优':>8}{'持平':>7}   分布")
    unanimous = 0
    rows = []
    for qid in reviews[0]["data"]:
        c = Counter(r["data"].get(qid, {}).get("concl", "?") for r in reviews)
        s, o, t = c.get("自产优", 0), c.get("官方优", 0), c.get("持平", 0)
        # 多数结论
        maj = max([("自产优", s), ("官方优", o), ("持平", t)], key=lambda x: x[1])[0]
        allsame = (len([k for k in (s, o, t) if k > 0]) == 1)
        if allsame:
            unanimous += 1
        rows.append((qid, s, o, t, maj, allsame))
        bar = "自" * s + "官" * o + "平" * t
        print(f"{qid:<6}{s:>7}{o:>8}{t:>7}   {bar}")
    print()
    print(f"全票一致的题: {unanimous} / {len(rows)}  ({unanimous/len(rows)*100:.0f}%)")
    print()

    # 多数票结论统计
    print("== 按多数票（逐题胜者）==")
    mc = Counter(r[4] for r in rows)
    for k in ("自产优", "官方优", "持平"):
        print(f"  {k}: {mc.get(k,0)} 题")

    # 可选：输出 markdown
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"| 评审 | 自产优 | 官方优 | 持平 |\n|---|---|---|---|\n")
            for r in reviews:
                c = Counter(x["concl"] for x in r["data"].values())
                f.write(f"| {r['tag']} | {c.get('自产优',0)} | {c.get('官方优',0)} | {c.get('持平',0)} |\n")
            f.write(f"| **合计** | **{tot_self}** | **{tot_off}** | **{tot_tie}** |\n\n")
            f.write("| 题号 | 自产优 | 官方优 | 持平 | 多数结论 |\n|---|---|---|---|---|\n")
            for qid, s, o, t, maj, _ in rows:
                f.write(f"| {qid} | {s} | {o} | {t} | {maj} |\n")
        print(f"\n已写出: {out}")

if __name__ == "__main__":
    main()
