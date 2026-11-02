#!/usr/bin/env python3
"""生成提交包：git archive 导出 → 自检六项交付物 → 生成 MANIFEST → zip。

用法
----
    python tools/package.py                 # 输出到项目上级目录
    python tools/package.py --out D:/提交    # 指定输出目录

只导出 git 跟踪的文件，因此 `.git/`、`models/`（3.9 GB 权重）不会进包。
"""
import argparse
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

NAME = "24计春本1班潘荣轩"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 六项交付物：缺任何一项都不应打包
REQUIRED = {
    "1 可运行代码": ["patches/0001-tcm-dev-path.patch", "tools/gguf_types.py", "configs/tuned_2b.yaml"],
    "2 一键部署脚本": ["scripts/deploy.sh"],
    "3 转换与量化脚本": ["scripts/00_fetch_models.sh", "scripts/01_convert.sh",
                        "scripts/02_strip_mtp.sh", "scripts/03_quantize.sh",
                        "scripts/04_build_quantizer.sh"],
    "4 模型转换与部署说明": ["docs/DEPLOY.md"],
    "5 性能测试报告": ["docs/技术文档.docx", "docs/技术文档.md"],
    "6 框架改造设计说明": ["docs/PATCH_TCM.md"],
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.dirname(ROOT))
    args = ap.parse_args()

    # 1) 导出版本库跟踪的文件
    stage = os.path.join(tempfile.mkdtemp(prefix="cie_pkg_"), NAME)
    os.makedirs(stage)
    try:
        tar_bytes = subprocess.check_output(["git", "archive", "HEAD"], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
            try:
                tf.extractall(stage, filter="data")   # Python 3.12+
            except TypeError:
                tf.extractall(stage)

        # 2) 自检六项交付物
        print("== 六项交付物自检 ==")
        missing = []
        for item, files in REQUIRED.items():
            ok = all(os.path.exists(os.path.join(stage, f)) for f in files)
            print("  %-22s %s" % (item, "OK" if ok else "缺失: " + ", ".join(
                f for f in files if not os.path.exists(os.path.join(stage, f)))))
            if not ok:
                missing.extend(f for f in files if not os.path.exists(os.path.join(stage, f)))
        if missing:
            print("\n打包中止：缺 %d 个必需文件" % len(missing))
            return 1

        # 3) MANIFEST
        rows = []
        for dp, dn, fn in os.walk(stage):
            dn.sort()
            for f in sorted(fn):
                p = os.path.join(dp, f)
                rows.append((os.path.relpath(p, stage).replace(os.sep, "/"),
                             os.path.getsize(p), sha256_of(p)))
        rows.sort()
        total = sum(r[1] for r in rows)

        man = ["提交包清单",
               "生成时间: %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
               "作品: 基于 K1 AI CPU 的 Qwen3.5 本地部署与性能优化",
               "作者: 潘荣轩 2024112005 24计春本1班",
               "文件数: %d    总大小: %.2f MB" % (len(rows) + 1, (total + 1) / 1024 / 1024),
               "",
               "%-62s %12s  %s" % ("路径", "字节", "sha256"),
               "-" * 62 + " " + "-" * 12 + "  " + "-" * 64]
        for rel, size, h in rows:
            man.append("%-62s %12d  %s" % (rel, size, h))
        with open(os.path.join(stage, "MANIFEST.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(man) + "\n")
        print("\nMANIFEST: %d 个文件，%.2f MB" % (len(rows) + 1, (total + 1) / 1024 / 1024))

        # 4) 打包
        os.makedirs(args.out, exist_ok=True)
        zip_path = os.path.join(args.out, NAME + ".zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for rel, _, _ in rows + [("MANIFEST.txt", 0, "")]:
                p = os.path.join(stage, rel)
                info = zipfile.ZipInfo.from_file(p, arcname="%s/%s" % (NAME, rel))
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(p, "rb") as src:
                    z.writestr(info, src.read())

        print("输出: %s（%.2f MB）" % (zip_path, os.path.getsize(zip_path) / 1024 / 1024))
        return 0
    finally:
        import shutil
        shutil.rmtree(os.path.dirname(stage), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
