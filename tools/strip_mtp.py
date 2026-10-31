#!/usr/bin/env python3
"""剥离 Qwen3.5 GGUF 中的 MTP(nextn) 层，使元数据与真实层数一致。

背景：spacemit llama.cpp v0.2.3 的转换器会把 MTP 模块写成额外一层
(blk.N)，并同时写入：
    <arch>.block_count          = N+1
    <arch>.nextn_predict_layers = 1
    <arch>.attention.recurrent_layers = [.., N+1 个元素]
旧版运行时（0.1.1）不认识 MTP，加载器按 block_count + nextn_predict_layers
去数张量，于是报 `wrong number of tensors` 或 `missing tensor 'blk.N.ssm_conv1d.weight'`。

本脚本删除 blk.N.* 张量，并把上述三个键修正为 24 层 / 0 个 nextn。

用法: python3 strip_mtp.py <输入.gguf> <输出.gguf>
"""
import sys
import gguf


def main(src: str, dst: str) -> int:
    r = gguf.GGUFReader(src)
    arch = r.get_field("general.architecture").contents()
    bc_key = f"{arch}.block_count"
    nk_key = f"{arch}.nextn_predict_layers"
    rl_key = f"{arch}.attention.recurrent_layers"

    n_block = int(r.get_field(bc_key).contents())
    last = n_block - 1
    prefix = f"blk.{last}."

    keep = [t for t in r.tensors if not t.name.startswith(prefix)]
    dropped = len(r.tensors) - len(keep)

    print(f"源文件   : {src}")
    print(f"架构     : {arch}")
    print(f"原层数   : {n_block} (含 nextn) -> 修正为 {last}")
    print(f"张量     : {len(r.tensors)} -> 保留 {len(keep)}，删除 {dropped} 个 {prefix}*")
    if nk_key in r.fields:
        print(f"nextn    : {int(r.fields[nk_key].contents())} -> 0")

    w = gguf.GGUFWriter(dst, arch)
    managed = {bc_key, nk_key, rl_key, "general.architecture"}

    for name, field in r.fields.items():
        if name in managed or name.startswith("GGUF."):
            continue
        vtype = field.types[0]
        val = field.contents()
        if vtype == gguf.GGUFValueType.ARRAY:
            w.add_key_value(name, val, vtype, field.types[1])
        else:
            w.add_key_value(name, val, vtype)

    w.add_key_value(bc_key, last, gguf.GGUFValueType.UINT32)
    if nk_key in r.fields:
        w.add_key_value(nk_key, 0, gguf.GGUFValueType.UINT32)
    if rl_key in r.fields:
        rl = list(r.fields[rl_key].contents())
        if len(rl) == n_block:
            rl = rl[:last]
            print(f"recurrent_layers: {n_block} 项 -> {len(rl)} 项")
        w.add_key_value(rl_key, rl, gguf.GGUFValueType.ARRAY,
                        gguf.GGUFValueType.BOOL)

    for t in keep:
        # GGUFWriter 的 raw_shape 期望 numpy 顺序（维数与 ggml 相反），
        # 而 ReaderTensor.shape 是 ggml 顺序，因此需显式反转，否则二维张量会被转置。
        w.add_tensor(t.name, t.data, raw_shape=tuple(reversed(t.shape)), raw_dtype=t.tensor_type)

    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()

    chk = gguf.GGUFReader(dst)
    bc = int(chk.get_field(bc_key).contents())
    nk = int(chk.get_field(nk_key).contents()) if nk_key in chk.fields else None
    rl = len(chk.get_field(rl_key).contents()) if rl_key in chk.fields else None
    mtp = sum(1 for t in chk.tensors if t.name.startswith(prefix))
    print(f"输出文件 : {dst}")
    print(f"校验     : block_count={bc}, nextn={nk}, recurrent_layers={rl}, "
          f"tensors={len(chk.tensors)}, 残留MTP={mtp}")
    ok = (bc == last and nk in (0, None) and mtp == 0)
    print("结果     : " + ("OK" if ok else "异常，请检查"))
    return 0 if ok else 2


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2]))
