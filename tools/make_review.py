#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_review.py — 生成质量盲评页面（左右随机、评完揭晓）

用法: python make_review.py <官方.txt> <自产.txt> <输出.html>
"""
import re
import sys
import json
import random

def parse(path):
    txt = open(path, encoding="utf-8").read()
    parts = re.split(r"^===== (Q\d+) =====$", txt, flags=re.M)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        qid = parts[i]
        block = parts[i + 1].strip()
        m = re.match(r"Q:\s*(.*?)\nA:\s*(.*)", block, flags=re.S)
        if m:
            out[qid] = {"q": m.group(1).strip(), "a": m.group(2).strip()}
    return out

def main():
    if len(sys.argv) != 4:
        print("用法: python make_review.py <官方.txt> <自产.txt> <输出.html>")
        sys.exit(1)

    official = parse(sys.argv[1])
    selfmade = parse(sys.argv[2])

    random.seed(20261101)  # 固定种子，保证每次生成顺序一致
    items = []
    for qid in sorted(official):
        if qid not in selfmade:
            continue
        flip = random.random() < 0.5   # True => 左边是自产
        left = selfmade[qid] if flip else official[qid]
        right = official[qid] if flip else selfmade[qid]
        items.append({
            "id": qid,
            "q": official[qid]["q"],
            "left": left["a"],
            "right": right["a"],
            "flip": flip,
        })

    data = json.dumps(items, ensure_ascii=False)

    tpl = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>质量盲评 · Qwen3.5-2B Q4_0 官方 vs 自产</title>
<style>
:root{--bg:#f7f7f9;--card:#fff;--bd:#e3e3e8;--tx:#1c1c1e;--mut:#8a8a90;
      --blue:#0a6cff;--green:#0f9d58;--amber:#e8a33d;--red:#d64545;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
     font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#fff;border-bottom:1px solid var(--bd);
       padding:14px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:650}
.bar{flex:1;min-width:160px;height:8px;background:#ececf0;border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:var(--blue);transition:width .25s}
.stat{font-size:13px;color:var(--mut)}
.stat b{color:var(--tx)}
button{font:inherit;cursor:pointer;border:1px solid var(--bd);background:#fff;
       border-radius:8px;padding:7px 14px;transition:.15s}
button:hover{border-color:#c8c8d0}
.wrap{max-width:1180px;margin:0 auto;padding:22px 24px 120px}
.item{background:var(--card);border:1px solid var(--bd);border-radius:12px;
      padding:18px 20px;margin-bottom:18px}
.item.done{border-color:#bfe3cd;background:#fbfffc}
.qhead{display:flex;align-items:baseline;gap:10px;margin-bottom:14px}
.tag{font-size:12px;font-weight:700;color:#fff;background:#5b5b63;
     border-radius:5px;padding:2px 8px;flex:none}
.qtext{font-weight:600}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.col{border:1px solid var(--bd);border-radius:9px;overflow:hidden;background:#fcfcfd}
.col h3{margin:0;padding:7px 12px;font-size:12.5px;font-weight:650;color:#555;
        background:#f2f2f5;border-bottom:1px solid var(--bd);letter-spacing:.3px}
.body{padding:12px 14px;white-space:pre-wrap;word-break:break-word;
      max-height:340px;overflow:auto;font-size:14px;line-height:1.7}
.acts{display:flex;gap:10px;margin-top:14px;align-items:center;flex-wrap:wrap}
.acts button.sel{background:var(--blue);color:#fff;border-color:var(--blue)}
.reveal{margin-left:auto;font-size:12.5px;color:var(--mut)}
.foot{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--bd);
      padding:12px 24px;display:flex;gap:12px;align-items:center;justify-content:center;flex-wrap:wrap}
.pill{font-size:12.5px;padding:3px 10px;border-radius:99px;background:#f0f0f4;color:#555}
.pill.win{background:#e7f4ec;color:#0f7a45}
.pill.eq{background:#fdf3e3;color:#9a6a12}
</style>
</head>
<body>
<header>
  <h1>质量盲评 · 20 题</h1>
  <div class="bar"><i id="prog"></i></div>
  <div class="stat">已评 <b id="nDone">0</b>/<b id="nAll">0</b></div>
  <button id="btnToggle">揭晓版本</button>
  <button id="btnReset">重置</button>
  <button id="btnExport">导出结果</button>
</header>
<div class="wrap" id="list"></div>
<div class="foot">
  <span class="pill" id="pA">左优 0</span>
  <span class="pill eq" id="pB">持平 0</span>
  <span class="pill" id="pC">右优 0</span>
  <span class="stat" id="summary">提示：左右两栏内容已随机打乱，建议先读再点选</span>
</div>
<script>
const DATA = __DATA__;
const KEY = "qreview_v1";
let state = JSON.parse(localStorage.getItem(KEY) || "{}");
let revealed = false;

const list = document.getElementById("list");
const nAll = document.getElementById("nAll");
const nDone = document.getElementById("nDone");
const prog = document.getElementById("prog");

function esc(s){return s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}

function build(){
  nAll.textContent = DATA.length;
  list.innerHTML = DATA.map(it=>{
    const s = state[it.id];
    return `<div class="item ${s?'done':''}" id="i-${it.id}">
      <div class="qhead"><span class="tag">${it.id}</span><span class="qtext">${esc(it.q)}</span></div>
      <div class="cols">
        <div class="col"><h3>版本 A（左）</h3><div class="body">${esc(it.left)}</div></div>
        <div class="col"><h3>版本 B（右）</h3><div class="body">${esc(it.right)}</div></div>
      </div>
      <div class="acts">
        <button data-q="${it.id}" data-v="left"  class="${s==='left'?'sel':''}">左更好</button>
        <button data-q="${it.id}" data-v="tie"   class="${s==='tie'?'sel':''}">持平</button>
        <button data-q="${it.id}" data-v="right" class="${s==='right'?'sel':''}">右更好</button>
        <span class="reveal" id="r-${it.id}"></span>
      </div>
    </div>`;
  }).join("");
  refresh();
}

function refresh(){
  const d = Object.keys(state).length;
  nDone.textContent = d;
  prog.style.width = (d/DATA.length*100)+"%";
  let a=0,b=0,c=0;
  for(const k in state){
    if(state[k]==="left")a++; else if(state[k]==="tie")b++; else c++;
  }
  document.getElementById("pA").textContent = "左优 "+a;
  document.getElementById("pB").textContent = "持平 "+b;
  document.getElementById("pC").textContent = "右优 "+c;
  if(revealed) revealAll();
}

function revealAll(){
  DATA.forEach(it=>{
    const el = document.getElementById("r-"+it.id);
    if(!el) return;
    const L = it.flip ? "自产" : "官方";
    const R = it.flip ? "官方" : "自产";
    el.textContent = `左=${L}　右=${R}`;
  });
}

list.addEventListener("click", e=>{
  const btn = e.target.closest("button[data-q]");
  if(!btn) return;
  const q = btn.dataset.q, v = btn.dataset.v;
  if(state[q] === v) delete state[q]; else state[q] = v;
  localStorage.setItem(KEY, JSON.stringify(state));
  const box = document.getElementById("i-"+q);
  box.classList.toggle("done", !!state[q]);
  box.querySelectorAll("button[data-q]").forEach(b=>b.classList.toggle("sel", b.dataset.v===state[q]));
  refresh();
});

document.getElementById("btnToggle").onclick = e=>{
  revealed = !revealed;
  e.target.textContent = revealed ? "隐藏版本" : "揭晓版本";
  if(revealed) revealAll();
  else DATA.forEach(it=>{const el=document.getElementById("r-"+it.id); if(el) el.textContent="";});
};

document.getElementById("btnReset").onclick = ()=>{
  if(!confirm("清空全部评分？")) return;
  state = {}; localStorage.removeItem(KEY); build();
};

document.getElementById("btnExport").onclick = ()=>{
  let winSelf=0, winOff=0, tie=0, missing=[];
  const lines = [`质量盲评结果  ${new Date().toLocaleString()}`,
                 "题号\t选择\t左版本\t右版本\t结论"];
  DATA.forEach(it=>{
    const s = state[it.id] || "未评";
    if(s==="未评") missing.push(it.id);
    const L = it.flip ? "自产" : "官方";
    const R = it.flip ? "官方" : "自产";
    let concl = "—";
    if(s==="tie"){ concl="持平"; tie++; }
    else if(s==="left"){ concl = (L==="自产"?"自产优":"官方优"); L==="自产"?winSelf++:winOff++; }
    else if(s==="right"){ concl = (R==="自产"?"自产优":"官方优"); R==="自产"?winSelf++:winOff++; }
    lines.push(`${it.id}\t${s}\t${L}\t${R}\t${concl}`);
  });
  lines.push("");
  lines.push(`汇总: 自产优 ${winSelf} / 官方优 ${winOff} / 持平 ${tie} / 未评 ${missing.length}`);
  if(missing.length) lines.push("未评: " + missing.join(","));
  const txt = lines.join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], {type:"text/plain;charset=utf-8"}));
  a.download = "quality_review_result.txt";
  a.click();
};

build();
</script>
</body>
</html>
"""

    html = tpl.replace("__DATA__", data)
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        f.write(html)
    print(f"生成成功: {sys.argv[3]}")
    print(f"题目数: {len(items)}")
    print(f"左侧为自产的题数: {sum(1 for it in items if it['flip'])}")

if __name__ == "__main__":
    main()
