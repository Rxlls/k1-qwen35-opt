cd ~/cie
OUT=results/tune_confirm.txt
: > $OUT
echo "===== 复验：4K 深度 ub=256 vs 512（各 2 次）=====" >> $OUT
for R in 1 2; do
 for UB in 256 512; do
  echo "--- run$R ub=$UB ---" >> $OUT
  timeout 900 llama-bench -m models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -p 512 -n 0 -d 4096 -ub $UB -b $UB -fa 1 -mmp 0 -r 1 >> $OUT 2>&1
 done
done
echo "===== d0 上 ub 的影响 =====" >> $OUT
for UB in 256 512; do
  echo "--- d0 ub=$UB ---" >> $OUT
  timeout 600 llama-bench -m models/Qwen3.5-2B-Q4_0-self.gguf -t 4 -p 512 -n 64 -ub $UB -b $UB -fa 1 -mmp 0 -r 1 >> $OUT 2>&1
done
echo "===== 并发吞吐（batched-bench, npl=1/2/4）=====" >> $OUT
timeout 1200 llama-batched-bench -m models/Qwen3.5-2B-Q4_0-self.gguf -c 8192 -b 2048 -ub 512 -npp 512 -ntg 64 -npl 1,2,4 -t 4 -fa 1 >> $OUT 2>&1
touch /tmp/tune2.done
