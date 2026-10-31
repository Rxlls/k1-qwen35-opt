#!/usr/bin/env python3
"""极简 GGUF 头部解析：只提取张量名/类型/维度，跳过词表内容。

用途：对比两个 GGUF 的张量类型分布，定位性能差异的来源。
不依赖 gguf 库（其默认 Reader 会解析 24.8 万条 tokenizer 字符串，在 K1 上需十几分钟）。
本脚本用 mmap + 偏移跳转，只做长度算术，秒级完成。

用法:
  python3 gguf_types.py <文件1.gguf> [文件2.gguf ...]
  python3 gguf_types.py --group <文件.gguf>    # 按「张量后缀 × 类型」分组统计

--group 模式用于回答「某类型到底落在哪些张量上」这类问题，例如区分
Q8_0 的 36 个张量是 ssm_alpha/beta（18层×2）还是注意力权重（6层×6）——
两者数量恰好相同，不能靠算术推断。
"""
import sys
import mmap
import struct
import collections

TYPE_NAMES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1",
    8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K",
    14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS", 18: "IQ3_XXS",
    19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S", 23: "IQ4_XS",
    24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64", 29: "IQ1_M",
    30: "BF16",
}

SCALAR_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
ARRAY = 9
STRING = 8

# 白名单：SpacemiT 文档列出的 IME 加速量化类型
IME_WHITELIST = {"Q4_K_M", "Q4_0", "Q4_1", "Q2_K", "Q3_K"}
# 实际按块类型判断（K-quants 的 M/S 变体共用同一块类型）
IME_BLOCK_OK = {"Q4_0", "Q4_1", "Q2_K", "Q3_K", "Q4_K"}

INTEREST = [
    "token_embd.weight",
    "blk.0.ssm_alpha.weight",
    "blk.0.ssm_beta.weight",
    "blk.0.ssm_conv1d.weight",
    "blk.0.ssm_norm.weight",
    "blk.0.ssm_out.weight",
    "blk.0.ssm_a",
    "blk.0.attn_norm.weight",
    "blk.0.attn_q.weight",
    "blk.3.attn_q.weight",
    "blk.0.ffn_down.weight",
    "blk.0.ffn_up.weight",
]


def parse(path):
    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        if mm[:4] != b"GGUF":
            raise SystemExit("%s: 不是 GGUF 文件" % path)
        off = 4
        ver, = struct.unpack_from("<I", mm, off); off += 4
        n_tensor, n_kv = struct.unpack_from("<QQ", mm, off); off += 16

        for _ in range(n_kv):
            slen, = struct.unpack_from("<Q", mm, off); off += 8 + slen
            vtype, = struct.unpack_from("<I", mm, off); off += 4
            if vtype == ARRAY:
                etype, = struct.unpack_from("<I", mm, off); off += 4
                count, = struct.unpack_from("<Q", mm, off); off += 8
                if etype == STRING:
                    for _ in range(count):
                        ln, = struct.unpack_from("<Q", mm, off); off += 8 + ln
                else:
                    off += count * SCALAR_SIZE[etype]
            elif vtype == STRING:
                ln, = struct.unpack_from("<Q", mm, off); off += 8 + ln
            else:
                off += SCALAR_SIZE[vtype]

        tensors = []
        for _ in range(n_tensor):
            slen, = struct.unpack_from("<Q", mm, off); off += 8
            name = mm[off:off + slen].decode("utf-8", "replace"); off += slen
            ndim, = struct.unpack_from("<I", mm, off); off += 4
            dims = struct.unpack_from("<%dQ" % ndim, mm, off); off += 8 * ndim
            ttype, = struct.unpack_from("<I", mm, off); off += 4
            off += 8  # data offset
            tensors.append((name, ttype, dims))
        mm.close()
        return ver, tensors


def suffix_of(name):
    """把 blk.N.xxx 归一化为 xxx，便于按张量角色聚合。"""
    if name.startswith("blk."):
        parts = name.split(".", 2)
        return parts[2] if len(parts) > 2 else name
    return name


def main(paths, group=False):
    for p in paths:
        ver, tensors = parse(p)
        hist = collections.Counter(TYPE_NAMES.get(t, str(t)) for _, t, _ in tensors)
        print("=== %s" % p.split("/")[-1])
        print("    GGUF v%d, %d 张量, 类型分布: %s" % (ver, len(tensors), dict(hist)))

        # 白名单判定（只统计二维以上的权重张量；一维 norm/偏置为 F32 属正常）
        n_off = 0
        off_types = collections.Counter()
        for name, t, dims in tensors:
            tn = TYPE_NAMES.get(t, str(t))
            if tn == "F32" or len(dims) < 2:
                continue
            if tn not in IME_BLOCK_OK:
                n_off += 1
                off_types[tn] += 1
        total_w = sum(1 for _, t, d in tensors
                      if len(d) >= 2 and TYPE_NAMES.get(t, "") != "F32")
        print("    二维权重张量 %d 个；不在 IME 白名单内 %d 个 %s"
              % (total_w, n_off, dict(off_types) if off_types else ""))

        if group:
            g = collections.Counter((suffix_of(n), TYPE_NAMES.get(t, str(t)))
                                    for n, t, _ in tensors)
            print("    --- 按张量角色分组（Top 15）---")
            for (suf, tn), c in g.most_common(15):
                print("      %-30s %-6s x%d" % (suf, tn, c))
        else:
            d = {n: (t, dims) for n, t, dims in tensors}
            for name in INTEREST:
                if name in d:
                    t, dims = d[name]
                    print("      %-26s %-6s %s" % (name, TYPE_NAMES.get(t, t), dims))
        print()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    grp = "--group" in args
    files = [a for a in args if a != "--group"]
    main(files, group=grp)
