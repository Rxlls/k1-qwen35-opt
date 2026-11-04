"""C-Eval 子集配对评测：同一批题、两个量化文件各答一次，比较准确率与差异显著性。

用法（在 K1 上，先起 llama-server 再跑）：
    python3 tools/eval_ceval.py run  --tag official --out eval/result_official.json
    python3 tools/eval_ceval.py compare eval/result_official.json eval/result_self.json
"""
import argparse
import json
import re
import sys
import urllib.request

URL = "http://127.0.0.1:8080/v1/chat/completions"
PROMPT = (
    "以下是中国关于「{subject}」的单项选择题，请直接回答正确选项的字母，不要解释。\n\n"
    "{question}\nA. {A}\nB. {B}\nC. {C}\nD. {D}\n\n只回答一个字母。"
)


def ask(prompt, timeout=300):
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "n_predict": 8,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"].strip()


def parse_choice(text):
    m = re.search(r"[ABCD]", (text or "").upper())
    return m.group(0) if m else "?"


def run(tag, out):
    qs = json.load(open("eval/ceval_sample.json", encoding="utf-8"))
    items, ok = [], 0
    for i, q in enumerate(qs, 1):
        prompt = PROMPT.format(**q)
        try:
            raw = ask(prompt)
        except Exception as e:
            raw = "ERR:%s" % e
        pred = parse_choice(raw)
        hit = (pred == q["answer"].strip().upper())
        ok += hit
        items.append({"subject": q["subject"], "answer": q["answer"], "pred": pred,
                      "raw": raw[:40], "correct": hit})
        print("[%3d/%d] %-30s 答 %s 对 %s %s" % (i, len(qs), q["subject"], pred,
                                                q["answer"], "✓" if hit else "✗"), flush=True)
    acc = ok / len(qs) * 100
    json.dump({"tag": tag, "acc": acc, "n": len(qs), "items": items},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n%s: %d/%d = %.1f%% → %s" % (tag, ok, len(qs), acc, out))


def compare(fa, fb):
    A, B = json.load(open(fa, encoding="utf-8")), json.load(open(fb, encoding="utf-8"))
    assert A["n"] == B["n"], "题数不一致，无法配对"
    b = c = both = neither = 0
    for x, y in zip(A["items"], B["items"]):
        if x["correct"] and not y["correct"]:
            b += 1
        elif y["correct"] and not x["correct"]:
            c += 1
        elif x["correct"] and y["correct"]:
            both += 1
        else:
            neither += 1
    # McNemar 精确二项检验（双侧）
    n = b + c
    if n == 0:
        p = 1.0
    else:
        from math import comb
        k = min(b, c)
        p = 2 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
        p = min(p, 1.0)
    print("题数 %d" % A["n"])
    print("  %-10s %.1f%%" % (A["tag"], A["acc"]))
    print("  %-10s %.1f%%" % (B["tag"], B["acc"]))
    print("  配对：都对 %d｜都错 %d｜仅 %s 对 %d｜仅 %s 对 %d" % (both, neither, A["tag"], b, B["tag"], c))
    print("  McNemar 精确检验 p = %.4f %s" % (p, "（无显著差异）" if p >= 0.05 else "（差异显著）"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "compare"])
    ap.add_argument("--tag", default="run")
    ap.add_argument("--out", default="eval/result.json")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    if a.mode == "run":
        run(a.tag, a.out)
    else:
        compare(a.files[0], a.files[1])
