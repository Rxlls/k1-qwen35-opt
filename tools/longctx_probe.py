"""构造"长上下文取针"探针：把 3 个事实埋在文档的 5% / 50% / 95% 位置。

用法（在 K1 上）：
    python3 tools/longctx_probe.py --chars 9000 --out /tmp/needle.txt
输出文件内容 = 长文档 + 末尾提问，可直接喂给 llama-cli -f。
"""
import argparse

# 填充用的技术文本（与项目相关，避免模型靠常识猜答案）
FILLER = (
    "本地大语言模型在边缘设备上的部署，受限于内存带宽与算子实现两条主线。"
    "权重量化通过降低每个参数的比特数来压缩模型体积，但不同量化格式的 block 布局不同，"
    "在特定加速器上可能命中、也可能不命中硬件通路。命中时矩阵乘由定点单元完成，"
    "未命中时退化为通用向量实现，二者的吞吐差距可达数倍。"
    "长上下文场景还受注意力计算随序列长度线性增长的影响，深度越深，"
    "权重侧的优化被稀释得越明显。这些因素共同决定了端侧推理的可用边界。"
)

FACTS = [
    ("TCM 的容量", "512 KiB", 0.05),
    ("第几次复跑", "第 7 次", 0.50),
    ("GDN 层的数量", "24 层", 0.95),
]

QUESTION = (
    "\n\n请只根据上面的材料回答三个问题，每个问题一行，格式为「问题：答案」，不要解释：\n"
    "1. 材料中提到的 TCM 容量是多少？\n"
    "2. 材料中提到的复跑是第几次？\n"
    "3. 材料中提到的 GDN 层有多少层？\n"
)


def build(target_chars):
    """先铺满填充文本，再从后往前插入事实（保持位置索引有效）。"""
    s = (FILLER * (target_chars // len(FILLER) + 2))[:target_chars]
    for name, val, frac in sorted(FACTS, key=lambda x: -x[2]):
        pos = int(len(s) * frac)
        sentence = "补充记录：本项目的%s为 %s。" % (name, val)
        s = s[:pos] + sentence + s[pos:]
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chars", type=int, default=9000)
    ap.add_argument("--out", default="/tmp/needle.txt")
    a = ap.parse_args()
    doc = build(a.chars)
    text = doc + QUESTION
    with open(a.out, "w", encoding="utf-8") as fp:
        fp.write(text)
    print("字符数 %d，事实 3 个（5%%/50%%/95%%），已写入 %s" % (len(text), a.out))
