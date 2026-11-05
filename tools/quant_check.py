#!/usr/bin/env python3
"""quant_check.py — 量化文件的「部署合规门禁」

把 §8.4 的分析固化成可执行检查：给定一个 GGUF 与目标设备的加速策略，
判定这份权重是否真的会走进 IME 快路径。退出码非 0 表示不合规。

为什么需要它
------------
「Q4_0 比官方 Q4_0 快 87.8%」这个结论的根因是**张量类型**，不是体积：
官方文件混了 55 个 Q5_K/Q8_0/Q6_K 张量，全部掉出白名单。这类问题肉眼看不见
——文件名写着 Q4_0，里面却可能有 29% 的权重不是 Q4_0。本脚本用一条策略
把它变成可判定的门禁，接力棒交给 CI 或打包脚本。

用法
----
  python3 quant_check.py <model.gguf> [--policy k1] [--json] [--verbose]
  python3 quant_check.py --selftest        # 无需 GGUF，验证策略逻辑

依赖 tools/gguf_types.py 的 mmap 头部解析（秒级，不解析词表）。
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gguf_types import parse, TYPE_NAMES, suffix_of  # noqa: E402

# 每种类型每元素占用的字节（含 block 头均摊），用于算「字节覆盖率」
BPP = {
    "F32": 4.0, "F16": 2.0, "BF16": 2.0, "F64": 8.0,
    "Q4_0": 18 / 32, "Q4_1": 20 / 32, "Q5_0": 22 / 32, "Q5_1": 24 / 32,
    "Q8_0": 34 / 32, "Q8_1": 36 / 32,
    "Q2_K": 84 / 256, "Q3_K": 110 / 256, "Q4_K": 144 / 256,
    "Q5_K": 176 / 256, "Q6_K": 210 / 256, "Q8_K": 292 / 256,
    "IQ2_XXS": 66 / 256, "IQ2_XS": 74 / 256, "IQ3_XXS": 98 / 256,
    "IQ1_S": 50 / 256, "IQ4_NL": 18 / 32, "IQ3_S": 110 / 256,
    "IQ2_S": 82 / 256, "IQ4_XS": 136 / 256, "IQ1_M": 56 / 256,
}

# 设备策略：键为「后端/芯片」，值为该组合下真正加速的块类型。
# 依据见技术文档 §8.4：IME kernel 只有 i8i4（4-bit，IME1/IME2）与
# i8i5（5-bit，仅 IME2）；X60(a03c) 的 use_ime2=0，所以 5-bit 在此无通路。
POLICIES = {
    "k1": {
        "desc": "SpacemiT K1 / X60 (a03c) + llama.cpp 0.1.1，仅 IME1（i8i4）",
        "matmul_ok": {"Q4_0", "Q4_1", "Q2_K", "Q3_K", "Q4_K"},
        "lookup_ok": {"Q8_0", "Q6_K", "F16", "F32"},
        # 查表类张量不参与矩阵乘，可与权重用不同类型
        "lookup_suffix": {"token_embd.weight"},
        "warn_1d": {"F32", "F16"},
    },
    "k1-ime2": {
        "desc": "假设设备具备 IME2（i8i5 可用）——仅用于对照，本机不适用",
        "matmul_ok": {"Q4_0", "Q4_1", "Q2_K", "Q3_K", "Q4_K", "Q5_K", "Q5_0", "Q5_1"},
        "lookup_ok": {"Q8_0", "Q6_K", "F16", "F32"},
        "lookup_suffix": {"token_embd.weight"},
        "warn_1d": {"F32", "F16"},
    },
    "any": {
        "desc": "不设白名单：只检查类型是否可被 GGML 加载",
        "matmul_ok": set(BPP) | {"I8", "I16", "I32", "I64"},
        "lookup_ok": set(BPP) | {"I8", "I16", "I32", "I64"},
        "lookup_suffix": {"token_embd.weight"},
        "warn_1d": set(BPP),
    },
}


def classify(name, dims, policy):
    """返回 'matmul' / 'lookup' / 'vector'。"""
    if len(dims) < 2:
        return "vector"
    return "lookup" if suffix_of(name) in policy["lookup_suffix"] else "matmul"


def evaluate(tensors, policy):
    """对张量列表执行策略，返回结果字典（不打印）。"""
    matmul_total = matmul_bad = lookup_bad = vec_unusual = 0
    ok_bytes = all_bytes = 0
    bad = []
    lookup_types = collections.Counter()
    type_hist = collections.Counter()

    for name, t, dims in tensors:
        tn = TYPE_NAMES.get(t, str(t))
        type_hist[tn] += 1
        n_elem = 1
        for d in dims:
            n_elem *= int(d)
        nbytes = n_elem * BPP.get(tn, 1.0)
        kind = classify(name, dims, policy)

        if kind == "vector":
            if tn not in policy["warn_1d"]:
                vec_unusual += 1
                bad.append((name, tn, "一维张量类型非 F32/F16（通常无害，仅提示）", "warn"))
            continue

        all_bytes += nbytes
        if kind == "lookup":
            lookup_types[tn] += 1
            if tn in policy["lookup_ok"]:
                ok_bytes += nbytes
            else:
                lookup_bad += 1
                bad.append((name, tn, "查表张量不在允许集内", "fail"))
        else:
            matmul_total += 1
            if tn in policy["matmul_ok"]:
                ok_bytes += nbytes
            else:
                matmul_bad += 1
                bad.append((name, tn, "矩阵乘张量掉出加速白名单", "fail"))

    return {
        "matmul_total": matmul_total,
        "matmul_bad": matmul_bad,
        "lookup_bad": lookup_bad,
        "vec_unusual": vec_unusual,
        "coverage": (ok_bytes / all_bytes * 100) if all_bytes else 0.0,
        "violations": bad,
        "lookup_types": dict(lookup_types),
        "type_hist": dict(type_hist),
        "pass": matmul_bad == 0 and lookup_bad == 0,
    }


def report(path, res, policy, policy_name, verbose=False):
    print("== %s" % os.path.basename(path))
    print("   策略 %s：%s" % (policy_name, policy["desc"]))
    print("   二维权重 %d 个，命中白名单 %d 个（字节覆盖率 %.1f%%）"
          % (res["matmul_total"], res["matmul_total"] - res["matmul_bad"], res["coverage"]))
    if res["lookup_types"]:
        print("   查表张量：%s" % ", ".join("%s x%d" % (k, v) for k, v in res["lookup_types"].items()))
    fails = [v for v in res["violations"] if v[3] == "fail"]
    warns = [v for v in res["violations"] if v[3] == "warn"]
    if fails:
        shown = fails if verbose else fails[:8]
        print("   ✗ 不合规 %d 项：" % len(fails))
        for name, tn, why, _ in shown:
            print("       %-34s %-6s %s" % (name, tn, why))
        if len(fails) > len(shown):
            print("       ... 另有 %d 项，--verbose 查看全部" % (len(fails) - len(shown)))
    if warns:
        print("   ! 提示 %d 项（一维张量类型）" % len(warns))
    print("   ⇒ %s" % ("PASS：全部矩阵乘权重命中加速白名单" if res["pass"] else "FAIL：存在非白名单权重"))
    print()


def selftest():
    """用合成张量验证策略判定，不依赖任何 GGUF。"""
    P = POLICIES["k1"]
    W = (4096, 1024)
    cases = [
        ("全 Q4_0 + token_embd Q8_0", [
            ("blk.0.ssm_out.weight", 2, W),
            ("blk.0.ffn_down.weight", 2, W),
            ("token_embd.weight", 8, (151936, 1024)),
            ("blk.0.attn_norm.weight", 0, (1024,)),
        ], True),
        ("混入 Q5_K（官方文件的情形）", [
            ("blk.0.ssm_out.weight", 13, W),
            ("blk.0.ffn_down.weight", 2, W),
            ("token_embd.weight", 8, (151936, 1024)),
        ], False),
        ("混入 Q8_0 矩阵乘张量", [
            ("blk.0.ssm_alpha.weight", 8, (16, 1024)),
            ("blk.0.ffn_down.weight", 2, W),
        ], False),
        ("token_embd 用 Q6_K（允许）", [
            ("blk.0.ffn_down.weight", 2, W),
            ("token_embd.weight", 14, (151936, 1024)),
        ], True),
        ("Q4_1 与 Q2_K（均在白名单）", [
            ("blk.0.ffn_down.weight", 3, W),
            ("blk.0.ffn_gate.weight", 10, W),
        ], True),
    ]
    ok = True
    for label, tensors, expect in cases:
        res = evaluate(tensors, P)
        got = res["pass"]
        flag = "✓" if got == expect else "✗"
        if got != expect:
            ok = False
        print("%s %-30s 期望 %s 实得 %s（失败 %d，覆盖率 %.1f%%）"
              % (flag, label, "PASS" if expect else "FAIL", "PASS" if got else "FAIL",
                 res["matmul_bad"] + res["lookup_bad"], res["coverage"]))
    print("\n自检%s" % ("通过" if ok else "失败"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="量化文件部署合规门禁")
    ap.add_argument("gguf", nargs="?", help="待检查的 GGUF 文件")
    ap.add_argument("--policy", default="k1", choices=sorted(POLICIES), help="目标设备策略")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 CI 解析）")
    ap.add_argument("--verbose", action="store_true", help="打印全部违规项")
    ap.add_argument("--selftest", action="store_true", help="只跑策略逻辑自检")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.gguf:
        ap.print_help()
        return 2
    if not os.path.exists(a.gguf):
        print("文件不存在: %s" % a.gguf, file=sys.stderr)
        return 2

    policy = POLICIES[a.policy]
    _, tensors = parse(a.gguf)
    res = evaluate(tensors, policy)

    if a.json:
        print(json.dumps({
            "file": a.gguf, "policy": a.policy, "pass": res["pass"],
            "matmul_total": res["matmul_total"], "matmul_bad": res["matmul_bad"],
            "lookup_bad": res["lookup_bad"], "coverage_pct": round(res["coverage"], 2),
            "violations": [{"tensor": n, "type": t, "reason": w} for n, t, w, _ in res["violations"]],
        }, ensure_ascii=False, indent=1))
    else:
        report(a.gguf, res, policy, a.policy, a.verbose)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
