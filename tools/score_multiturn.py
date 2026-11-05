"""汇总两个多轮集结果：逐轮判分 + 配对比较。

判定规则：先做数字归一（去逗号/全角），能解析成数字就按数值比较（容差 2%），否则做子串匹配。
用法：python tools/score_multiturn.py eval/mt_official.json eval/mt_self.json
"""
import json
import re
import sys


def norm(s):
    return (s or "").replace(",", "").replace("，", "").replace(" ", "").strip()


def first_num(s):
    m = re.search(r"-?\d+(\.\d+)?", norm(s))
    return float(m.group()) if m else None


def hit(ans, exp):
    a, e = norm(ans), norm(exp)
    if not a:
        return False
    if e and e in a:
        return True
    ea, ee = first_num(a), first_num(e)
    if ea is not None and ee is not None:
        return abs(ea - ee) <= max(abs(ee) * 0.02, 0.01)
    return False


def load(p):
    return json.load(open(p, encoding="utf-8"))


def main():
    A, B = load(sys.argv[1]), load(sys.argv[2])
    rows = []
    for ca, cb in zip(A["items"], B["items"]):
        for ra, rb in zip(ca["rows"], cb["rows"]):
            rows.append((ca["id"], ra["turn"], hit(ra["answer"], ra["expect"]),
                         hit(rb["answer"], rb["expect"]), ra["wall"], rb["wall"]))

    n = len(rows)
    ca = sum(1 for r in rows if r[2])
    cb = sum(1 for r in rows if r[3])
    both = sum(1 for r in rows if r[2] and r[3])
    nei = sum(1 for r in rows if not r[2] and not r[3])
    only_a = sum(1 for r in rows if r[2] and not r[3])
    only_b = sum(1 for r in rows if r[3] and not r[2])
    wa = sum(r[4] for r in rows) / n
    wb = sum(r[5] for r in rows) / n

    print("%-10s %d/%d = %.1f%%   平均每轮 %.1fs" % (A["tag"], ca, n, ca / n * 100, wa))
    print("%-10s %d/%d = %.1f%%   平均每轮 %.1fs" % (B["tag"], cb, n, cb / n * 100, wb))
    print("配对：都对 %d｜都错 %d｜仅 %s 对 %d｜仅 %s 对 %d" % (both, nei, A["tag"], only_a, B["tag"], only_b))

    m = only_a + only_b
    if m == 0:
        p = 1.0
    else:
        from math import comb
        k = min(only_a, only_b)
        p = min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / (2 ** m))
    print("McNemar 精确检验 p = %.4f %s" % (p, "(无显著差异)" if p >= 0.05 else "(差异显著)"))

    print("\n逐轮正确率：")
    for t in (1, 2, 3):
        sub = [r for r in rows if r[1] == t]
        if sub:
            print("  第 %d 轮：%s %d/%d (%.0f%%)   %s %d/%d (%.0f%%)" % (
                t, A["tag"], sum(1 for r in sub if r[2]), len(sub), sum(1 for r in sub if r[2]) / len(sub) * 100,
                B["tag"], sum(1 for r in sub if r[3]), len(sub), sum(1 for r in sub if r[3]) / len(sub) * 100))

    bad = [(r[0], r[1], r[2], r[3]) for r in rows if r[2] != r[3]]
    if bad:
        print("\n不一致的轮次：")
        for x in bad:
            print("  %s 第%d轮  %s=%s  %s=%s" % (x[0], x[1], A["tag"], x[2], B["tag"], x[3]))


if __name__ == "__main__":
    main()
