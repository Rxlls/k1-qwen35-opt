#!/usr/bin/env python3
"""make_submission.py — 按平台四个提交位生成压缩包

平台字段：技术文档 / 相关证明材料 / 其他材料附件 / 项目演示视频
（视频需先录制，本脚本只在存在成片时打包）

输出：提交/ 目录下三个 zip，命名统一为「项目名-字段.zip」。
项目名含全角冒号不能进文件名，故压缩包名中去掉冒号，与表单填写名保持一致的前缀。
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "把权重压进IME-K1上的Qwen3.5加速"
OUT = os.path.join(ROOT, "提交")

README_TECH = """本包对应平台「技术文档」字段。

1. 技术文档.docx —— 12 章，79 张数据表、4 张图。含 baseline 与优化版对比、
   长上下文五点衰减曲线、内存预算模型、质量四证据、复现步骤与局限说明。
2. 方案书.docx   —— 项目陈述：背景、核心思路、关键取舍、开发计划、应用价值、边界认知。

建议阅读顺序：方案书 → 技术文档 §8（性能）→ §9（长上下文）→ §10（质量）。

若中文文件名显示异常，请改用支持 UTF-8 的解压工具（Windows 资源管理器、7-Zip 正常；
部分 Linux 的 unzip 需加 -O UTF-8）。
"""

README_CODE = """本包对应平台「其他材料附件」字段，内容为完整源码包。

1. k1-qwen35-opt.zip    —— 源码、脚本、文档、原始记录，附 MANIFEST.sha256 逐文件哈希。
2. k1-qwen35-opt.tar.gz —— 同一内容的 tar 版本（Linux 下解压中文名不会乱码，推荐）。

快速验证（在 K1 上，约 3 分钟）：
    tar xzf k1-qwen35-opt.tar.gz && cd k1-qwen35-opt
    export CIE_HOME=$PWD && ln -s ~/cie/models models
    bash scripts/deploy.sh check
    bash scripts/deploy.sh smoke

预期：check 末尾输出「结果: 通过 11 项，失败 0 项」。
"""

README_PROOF = """本包对应平台「相关证明材料」字段：结果可核查性材料（不是资格类证明）。

00  参赛信息与材料说明.docx —— 先读这份，含四个提交位的对应关系与复现步骤
01  产物哈希清单.txt        —— 最终交付的 GGUF 产物 sha256
02  权重哈希清单.txt        —— 上游原始权重逐文件 sha256
03  部署自检记录.txt        —— 在 K1 上对交付包执行 deploy.sh check / models 的真实输出
04_原始记录/results/        —— 全部 bench 原始输出、RSS 采样曲线、质量评测原始结果
04_原始记录/eval/           —— C-Eval 抽样题库与两文件配对结果、多轮集与结果

说明：负结果（KV 量化、前缀复用、slot 持久化、投机解码等）同样在原始记录中，未做删改。
"""


def add_dir(zf, src_dir, arc_prefix):
    n = 0
    for dirpath, _dirnames, filenames in os.walk(src_dir):
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src_dir)
            zf.write(full, os.path.join(arc_prefix, rel).replace("\\", "/"))
            n += 1
    return n


def readme(zf, text, arcname="README.txt"):
    zf.writestr(arcname, text)


def build(fname, builder):
    path = os.path.join(OUT, fname)
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        count = builder(zf)
    size = os.path.getsize(path)
    # 回读校验：条目数、名字可解码
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = zf.testzip()
    print("  %-46s %2d 条目  %6.2f MB  校验:%s"
          % (fname, len(names), size / 1048576, "OK" if bad is None else "损坏"))
    return path, len(names), size, count


def main():
    os.makedirs(OUT, exist_ok=True)
    required = [
        "docs/技术文档.docx", "docs/方案书.docx",
        "dist/k1-qwen35-opt.zip", "dist/k1-qwen35-opt.tar.gz",
        "docs/参赛信息与材料说明.docx", "docs/hashes.txt", "docs/weights.sha256",
        "docs/deploy_check_2026-11-06.txt", "results", "eval",
    ]
    missing = [p for p in required if not os.path.exists(os.path.join(ROOT, p))]
    if missing:
        print("缺少文件：", missing)
        return 1

    def tech(zf):
        for p in ["docs/技术文档.docx", "docs/方案书.docx"]:
            zf.write(os.path.join(ROOT, p), os.path.basename(p))
        readme(zf, README_TECH)
        return 2

    def code(zf):
        for p in ["dist/k1-qwen35-opt.zip", "dist/k1-qwen35-opt.tar.gz"]:
            zf.write(os.path.join(ROOT, p), os.path.basename(p))
        readme(zf, README_CODE)
        return 2

    def proof(zf):
        zf.write(os.path.join(ROOT, "docs/参赛信息与材料说明.docx"), "00_参赛信息与材料说明.docx")
        zf.write(os.path.join(ROOT, "docs/hashes.txt"), "01_产物哈希清单.txt")
        zf.write(os.path.join(ROOT, "docs/weights.sha256"), "02_权重哈希清单.txt")
        zf.write(os.path.join(ROOT, "docs/deploy_check_2026-11-06.txt"), "03_部署自检记录.txt")
        a = add_dir(zf, os.path.join(ROOT, "results"), "04_原始记录/results")
        b = add_dir(zf, os.path.join(ROOT, "eval"), "04_原始记录/eval")
        readme(zf, README_PROOF)
        return a + b

    print("生成提交包 → %s" % OUT)
    build("%s-技术文档.zip" % NAME, tech)
    build("%s-其他材料.zip" % NAME, code)
    build("%s-证明材料.zip" % NAME, proof)
    print("\n完成。视频成片就绪后，把 mp4 放进 提交/ 再执行本脚本的 video 段（或在打包脚本中补一行）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
