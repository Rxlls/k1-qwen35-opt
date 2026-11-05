#!/bin/bash
# 多轮复用演示：同一段材料连续追问，看第 2 轮起是否复用检查点
cd "$HOME/cie" || exit 1
PH=/tmp/cie_phases.log
mark() { echo "$1 $(date +%s%3N)" >> "$PH"; }

clear
printf "\n"
printf " \033[1;36m多轮对话 · 检查点复用\033[0m\n"
printf " 同一段材料，连续追问三轮\n"
printf "\n \033[2m────────────────────────────────────────────\033[0m\n\n"
sleep 5
mark BANNER_END

pkill -x llama-server 2>/dev/null; sleep 1
setsid llama-server -m models/Qwen3.5-2B-Q4_0-self.gguf -c 4096 -np 1 -t 4 -fa 1 \
  --no-mmap --jinja --port 8080 >/tmp/srv_mt.log 2>&1 &
for _ in $(seq 1 90); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health)" = "200" ] && break
  sleep 1
done
printf " 服务就绪\n\n"
mark M_START

python3 - <<'PY'
import json, time, urllib.request
P = open("/tmp/prompt512.txt", encoding="utf-8").read()
hist = [{"role": "user", "content": P + "\n问题一：主题是什么？"}]
for i in range(1, 4):
    body = json.dumps({"messages": hist, "n_predict": 24, "temperature": 0,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=1200))
    t1 = time.time()
    u = r.get("usage", {})
    ans = r["choices"][0]["message"]["content"]
    print(" 第 %d 轮  prompt %4d token   耗时 %6.1f s" % (i, u.get("prompt_tokens", 0), t1 - t0), flush=True)
    hist.append({"role": "assistant", "content": ans})
    hist.append({"role": "user", "content": "问题%d：再补充一点？" % (i + 1)})
PY

mark M_END
printf "\n \033[2m服务端日志：\033[0m\n"
grep -a "restored context checkpoint" /tmp/srv_mt.log | tail -2 | sed 's/^.*slot/ slot/' | cut -c1-72
pkill -x llama-server 2>/dev/null
sleep 10
mark END
