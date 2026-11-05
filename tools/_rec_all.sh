#!/bin/bash
# 依次重录五段：14pt 全屏终端，保留 shell 外框（标签栏 + 任务栏）
set -u
cd /tmp
for job in "demo_deploy.sh seg1_deploy 120" \
           "demo_ab2.sh    seg2_2b     360" \
           "demo_4b.sh     seg3_4b     800" \
           "demo_mt.sh     seg4_mt     600" \
           "demo_32k.sh    seg5_32k    240"; do
  set -- $job
  echo "===== $(date +%T) 录制 $2 ====="
  bash /tmp/rec_seg.sh "/tmp/$1" "/tmp/$2.mp4" 0.4 "$3"
  echo "----- rc=$? 完成 $(date +%T) -----"
done
echo "ALL_DONE $(date +%T)"
