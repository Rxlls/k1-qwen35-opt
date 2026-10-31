#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_spotcheck.py — 生成 3 题人工抽检页（带参考要点，用于锚定 LLM 评审）

用法: python make_spotcheck.py <官方.txt> <自产.txt> <输出.html>
"""
import re
import sys
import json

# 抽检题目与判据（左右顺序沿用 quality_review.html 中的 flip 设定，保证一致）
SPOT = [
    {
        "id": "Q03",
        "flip": True,   # True => 左边是自产
        "llm": "官方 9:1",
        "llm_winner": "官方",
        "why": "LLM 评审中 10 份有 9 份判官方更好",
        "checklist": [
            "周长 = 2 × (8 + 5) = <b>26 厘米</b>",
            "面积 = 8 × 5 = <b>40 平方厘米</b>",
            "两数都给出且计算过程正确 → 更好",
            "只给出一个数、或在公式环境中途截断 → 较差",
        ],
    },
    {
        "id": "Q08",
        "flip": True,
        "llm": "自产 10:0（全票）",
        "llm_winner": "自产",
        "why": "LLM 评审 10 份全部判自产更好",
        "checklist": [
            "正确关系：<b>每秒 token 数 = 带宽 ÷ 权重大小 = 10.6 ÷ 2.5 ≈ 4.24 t/s</b>",
            "方向正确（带宽越大越快、权重越大越慢）",
            "常见的严重错误：声称「1 个 token 的权重 = 4 Bytes」、或算出 2.5×4=10GB 这类无意义结果 → 明显更差",
        ],
    },
    {
        "id": "Q20",
        "flip": False,  # False => 左边是官方
        "llm": "官方 6:4（分歧最大）",
        "llm_winner": "官方",
        "why": "LLM 评审中 6 份判官方更好、4 份判自产更好",
        "checklist": [
            "对象是完全不懂计算机的人 → 评判标准是<b>通俗</b>，不是专业",
            "有贴切的类比（如「像给图书馆管理员派活」这类）→ 好",
            "堆砌术语（RISC-V、IME、量化、KV cache）而不解释 → 差",
            "这题的分歧本身说明：开放性问题上「哪个更好」因人而异",
        ],
    },
]

def parse(path):
    txt = open(path, encoding="utf-8").read()
    parts = re.split(r"^===== (Q\d+) =====$", txt, flags=re.M)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        block = parts[i + 1].strip()
        m = re.match(r"Q:\s*(.*?)\nA:\s*(.*)", block, flags=re.S)
        if m:
            out[parts[i]] = {"q": m.group(1).strip(), "a": m.group(2).strip()}
    return out

def main():
    official = parse(sys.argv[1])
    selfmade = parse(sys.argv[2])

    items = []
    for s in SPOT:
        qid = s["id"]
        if qid not in official or qid not in selfmade:
            continue
        left = selfmade[qid] if s["flip"] else official[qid]
        right = official[qid] if s["flip"] else selfmade[qid]
        items.append({
            "id": qid,
            "q": official[qid]["q"],
            "left": left["a"],
            "right": right["a"],
            "flip": s["flip"],
            "llm": s["llm"],
            "llm_winner": s["llm_winner"],
            "why": s["why"],
            "checklist": s["checklist"],
        })

    html = TPL.replace("__DATA__", json.dumps(items, ensure_ascii=False))
    open(sys.argv[3], "w", encoding="utf-8").write(html)
    print(f"生成: {sys.argv[3]}  ({len(items)} 题)")

TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>人工抽检 · 3 题</title>
<style>
:root{--bg:#f7f7f9;--card:#fff;--bd:#e3e3e8;--tx:#1c1c1e;--mut:#8a8a90;
      --blue:#0a6cff;--green:#0f9d58;--amber:#e8a33d;--red:#d64545;--purple:#7c4dff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
     font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{background:#fff;border-bottom:1px solid var(--bd);padding:16px 24px}
h1{font-size:17px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px}
.wrap{max-width:1180px;margin:0 auto;padding:22px 24px 140px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;
      padding:20px 22px;margin-bottom:20px}
.qhead{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}
.tag{font-size:12px;font-weight:700;color:#fff;background:#5b5b63;
     border-radius:5px;padding:2px 8px;flex:none}
.qtext{font-weight:600}
.check{background:#f3f7ff;border:1px solid #d6e4ff;border-radius:9px;
       padding:12px 16px;margin-bottom:16px;font-size:14px}
.check h4{margin:0 0 8px;font-size:13px;color:var(--blue);letter-spacing:.3px}
.check ul{margin:0;padding-left:20px}
.check li{margin:4px 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.col{border:1px solid var(--bd);border-radius:9px;overflow:hidden;background:#fcfcfd}
.col h3{margin:0;padding:7px 12px;font-size:12.5px;font-weight:650;color:#555;
        background:#f2f2f5;border-bottom:1px solid var(--bd)}
.body{padding:12px 14px;white-space:pre-wrap;word-break:break-word;
      max-height:340px;overflow:auto;font-size:14px;line-height:1.7}
.acts{display:flex;gap:10px;margin-top:14px;align-items:center;flex-wrap:wrap}
button{font:inherit;cursor:pointer;border:1px solid var(--bd);background:#fff;
       border-radius:8px;padding:7px 14px;transition:.15s}
button:hover{border-color:#c8c8d0}
button.sel{background:var(--blue);color:#fff;border-color:var(--blue)}
.verdict{margin-left:auto;font-size:13px;font-weight:650}
.verdict.ok{color:var(--green)}
.verdict.no{color:var(--red)}
.foot{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--bd);
      padding:12px 24px;display:flex;gap:12px;align-items:center;justify-content:center;flex-wrap:wrap}
.stat{font-size:13px;color:var(--mut)}
.stat b{color:var(--tx)}
</style>
</head>
<body>
<header>
  <h1>人工抽检 · 3 题</h1>
  <div class="sub">用于锚定 10 个 LLM 的盲评结论。每题都给了"参考要点"，按要点判断即可，不需要专业知识。</div>
</header>
<div class="wrap" id="list"></div>
<div class="foot">
  <span class="stat">已评 <b id="n">0</b>/<b id="tot">0</b>　与 LLM 一致 <b id="agree">0</b></span>
  <button id="export">导出结果</button>
</div>
<script>
const DATA = __DATA__;
const KEY = "spotcheck_v1";
let state = JSON.parse(localStorage.getItem(KEY) || "{}");
const list = document.getElementById("list");

function esc(s){return s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}

list.innerHTML = DATA.map(it=>`
  <div class="card" id="c-${it.id}">
    <div class="qhead"><span class="tag">${it.id}</span><span class="qtext">${esc(it.q)}</span></div>
    <div class="check">
      <h4>参考要点（据此判断，不需要懂技术细节）</h4>
      <ul>${it.checklist.map(x=>`<li>${x}</li>`).join("")}</ul>
    </div>
    <div class="cols">
      <div class="col"><h3>版本 A（左）</h3><div class="body">${esc(it.left)}</div></div>
      <div class="col"><h3>版本 B（右）</h3><div class="body">${esc(it.right)}</div></div>
    </div>
    <div class="acts">
      <button data-q="${it.id}" data-v="left">左更好</button>
      <button data-q="${it.id}" data-v="tie">持平</button>
      <button data-q="${it.id}" data-v="right">右更好</button>
      <span class="verdict" id="v-${it.id}"></span>
    </div>
  </div>`).join("");

function winnerOf(it, choice){
  if(choice==="tie") return "持平";
  const side = choice==="left" ? (it.flip?"自产":"官方") : (it.flip?"官方":"自产");
  return side;
}

function refresh(){
  const n = Object.keys(state).length;
  document.getElementById("n").textContent = n;
  document.getElementById("tot").textContent = DATA.length;
  let agree = 0;
  DATA.forEach(it=>{
    const c = state[it.id];
    const el = document.getElementById("v-"+it.id);
    if(!c){ el.textContent=""; el.className="verdict"; return; }
    const w = winnerOf(it, c);
    const same = (w === it.llm_winner);
    if(same) agree++;
    el.textContent = same ? `与 LLM 评审一致（LLM: ${it.llm}）` : `与 LLM 评审不一致（LLM: ${it.llm}）`;
    el.className = "verdict " + (same ? "ok" : "no");
  });
  document.getElementById("agree").textContent = agree;
}

list.addEventListener("click", e=>{
  const b = e.target.closest("button[data-q]");
  if(!b) return;
  const q = b.dataset.q, v = b.dataset.v;
  if(state[q]===v) delete state[q]; else state[q]=v;
  localStorage.setItem(KEY, JSON.stringify(state));
  document.querySelectorAll(`button[data-q="${q}"]`).forEach(x=>x.classList.toggle("sel", x.dataset.v===state[q]));
  refresh();
});

document.getElementById("export").onclick = ()=>{
  const lines = ["人工抽检结果  " + new Date().toLocaleString(), ""];
  let agree = 0;
  DATA.forEach(it=>{
    const c = state[it.id] || "未评";
    const w = c==="未评" ? "—" : winnerOf(it, c);
    const same = (w===it.llm_winner);
    if(same && c!=="未评") agree++;
    const L = it.flip ? "自产" : "官方";
    const R = it.flip ? "官方" : "自产";
    lines.push(`${it.id}\t左=${L} 右=${R}\t我的选择=${c}\t我的结论=${w}\tLLM结论=${it.llm_winner}(${it.llm})\t${c==="未评"?"未评":(same?"一致":"不一致")}`);
  });
  lines.push("");
  lines.push(`汇总: 与 LLM 评审一致 ${agree} / ${DATA.length}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\n")], {type:"text/plain;charset=utf-8"}));
  a.download = "spotcheck_result.txt";
  a.click();
};

refresh();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
