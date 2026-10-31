#!/usr/bin/env bash
# gen_run_report.sh — 生成/刷新 ~/cie/run.txt（运行结果汇总）
# 用法: bash ~/cie/tools/gen_run_report.sh
# 说明: 可重复执行，每次覆盖写入；运行中的阶段会显示"进行中"

set -u
CIE="${CIE_HOME:-$HOME/cie}"
R="$CIE/results"
OUT="$CIE/run.txt"

cd "$R" 2>/dev/null || { echo "结果目录不存在: $R"; exit 1; }

{
echo "================================================================"
echo " K1 Qwen3.5 推理优化 · 运行结果汇总"
echo " 生成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 主机: $(hostname) | 架构: $(uname -m) | 内核: $(uname -r)"
echo " 运行时: llama.cpp 0.1.1 (apt, legacy IME1) | 口径: -t 4 -fa 1 -mmp 0"
echo "================================================================"
echo
echo "## 一、流水线阶段状态"
for s in 1 2 3; do
  if [ -f "stage${s}.done" ]; then echo "  stage${s}: 完成"; else echo "  stage${s}: 未完成(进行中或未启动)"; fi
done
echo
echo "## 二、4B 各版本基准 (-r 2)"
grep -E "bench |pp64|pp512|tg128|完成 耗时|FAIL" stage_4b.log 2>/dev/null | sed 's/  */ /g' || echo "  无数据"
echo
echo "## 三、KV cache 对比 (2B, f16 vs q8_0)"
tail -30 stage_kv.log 2>/dev/null | sed 's/  */ /g' || echo "  未开始"
echo
echo "## 四、TTFT / 多轮 (llama-server)"
tail -30 stage_server.log 2>/dev/null | sed 's/  */ /g' || echo "  未开始"
echo
echo "## 五、质量测试"
if ls q2_*.txt >/dev/null 2>&1; then
  echo "  [有效] v2 口径：套 chat 模板 + 预填空 think（关闭思考）"
  for f in q2_*.txt; do echo "  $f: $(grep -c '^===== Q' "$f" 2>/dev/null) 条"; done
fi
if ls quality_*.txt >/dev/null 2>&1; then
  echo "  [已废弃] v1 口径：裸 prompt，模型输出思考过程占满 token 预算"
  for f in quality_*.txt; do echo "  $f: $(grep -c '^===== Q' "$f" 2>/dev/null) 条"; done
fi
echo
echo "## 六、失败项"
grep -h "FAIL" stage_*.log 2>/dev/null | tail -10 || echo "  无"
echo
echo "## 七、关键发现：IME 白名单实测（温度可作判据）"
cat <<'FINDING'
  类型      体积     pp512   tg128   耗时        满载温度   判定
  Q4_0      2.50G    8.10    1.43    6.9min      55C+       白名单内
  Q4_K_M    2.66G    4.37    1.28    10.7min     55C+       白名单内
  Q5_K_M    3.08G    --      --      50min中断   32C        白名单外
  Q3_K_M    2.30G    --      --      20min中断   31C        白名单外

  判据: 4核满载执行向量指令时 SoC 温度达 55C 以上;
        走通用标量路径时仅 31~32C（CPU 占用 390%+ 但每周期运算量极低）。
  结论: SpacemiT 文档所列"支持类型列表"与实际支持情况不一致,
        同一量化族内只有部分变体命中 IME 加速路径, 必须以实测温度/耗时为准。
  工程含义: 在 K1 上选量化格式, 正确顺序是先测温度(30秒)而非先测吞吐(数十分钟);
            温度 ~32C 即可判定该格式未命中加速路径, 无需等待完整基准跑完。
FINDING
echo
echo "## 八、模型产物清单"
ls -1sh "$CIE"/models/*.gguf 2>/dev/null | tail -14 || echo "  无"
echo
echo "================================================================"
echo " 数据源: $R/stage_*.log 与 bench_*.txt"
echo " 说明: 本次共 2 项基准因命中非加速路径被主动中断(见第六节)"
echo "================================================================"
} > "$OUT"

echo "已生成: $OUT"
echo "行数: $(wc -l < "$OUT")  大小: $(du -h "$OUT" | cut -f1)"
