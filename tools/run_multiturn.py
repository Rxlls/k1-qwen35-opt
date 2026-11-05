"""在设备上跑固定多轮集：每段对话 3 轮，历史累积，记录回答与耗时。

用法：python3 tools/run_multiturn.py --tag official --out eval/mt_official.json
"""
import argparse
import json
import time
import urllib.request

URL = "http://127.0.0.1:8080/v1/chat/completions"


def ask(messages, n_predict=48):
    body = json.dumps({
        "messages": messages,
        "n_predict": n_predict,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.load(r)
    dt = time.time() - t0
    return d["choices"][0]["message"]["content"].strip(), dt, d.get("usage", {}).get("prompt_tokens")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run")
    ap.add_argument("--out", default="eval/mt_result.json")
    a = ap.parse_args()

    data = json.load(open("eval/multiturn_set.json", encoding="utf-8"))
    results = []
    for conv in data:
        msgs = []
        rows = []
        for i, turn in enumerate(conv["turns"], 1):
            msgs.append({"role": "user", "content": turn["user"]})
            ans, dt, pt = ask(msgs)
            msgs.append({"role": "assistant", "content": ans})
            rows.append({"turn": i, "answer": ans, "expect": turn["expect"],
                         "prompt_tokens": pt, "wall": round(dt, 1)})
            print("%s-t%d  %5.1fs  prompt=%s  ans=%r" % (conv["id"], i, dt, pt, ans[:24]), flush=True)
        results.append({"id": conv["id"], "topic": conv["topic"], "rows": rows})

    json.dump({"tag": a.tag, "items": results}, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n%s 完成 → %s" % (a.tag, a.out))


if __name__ == "__main__":
    main()
