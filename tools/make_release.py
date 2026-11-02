#!/usr/bin/env python3
"""生成提交包（zip）与 MANIFEST.txt。

只打包 git 跟踪的文件——models/、gguf/、上游源码、镜像等已被 .gitignore 排除，
不会误把 GB 级文件塞进去。

用法
----
    python tools/make_release.py                      # → dist/k1-qwen35-opt.zip
    python tools/make_release.py -o D:/k1-opt.zip     # 指定输出
    python tools/make_release.py --no-manifest        # 不生成清单（调试用）

包内结构 = 仓库根目录结构 + MANIFEST.txt。文件名按 UTF-8 写入 zip。
"""
import argparse
import datetime
import hashlib
import os
import subprocess
import sys
import time
import zipfile

PROJECT = "k1-qwen35-opt"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args) -> str:
    return subprocess.check_output(["git"] + list(args), cwd=ROOT).decode("utf-8", "ignore").strip()


def tracked_files():
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(f for f in out.decode("utf-8").split("\0") if f)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(files, commit, out_path):
    rows, total = [], 0
    for f in files:
        full = os.path.join(ROOT, f)
        size = os.path.getsize(full)
        total += size
        rows.append((sha256(full), size, f))

    lines = [
        "# %s —— 提交包文件清单" % PROJECT,
        "",
        "赛题：进迭时空 —— 基于 K1 AI CPU 的 Qwen3.5 本地部署与性能优化",
        "生成时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "源码版本：commit %s" % commit,
        "文件数：%d（不含本清单）" % len(rows),
        "总大小：%.2f MB" % (total / 1048576),
        "",
        "模型文件不在包内（合计约 3.9 GB），获取与校验见 docs/DEPLOY.md §2、docs/hashes.txt。",
        "",
        "校验方式（包根目录执行）：",
        "    sha256sum -c MANIFEST.sha256     # 或按下方清单逐项核对",
        "",
        "## 清单（sha256 | 字节 | 路径）",
        "",
        "```",
        "%-64s %12s  %s" % ("sha256", "bytes", "path"),
    ]
    for h, s, f in rows:
        lines.append("%-64s %12d  %s" % (h, s, f))
    lines.append("```")
    lines.append("")

    with open(out_path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(lines))

    # 附带一份可直接 sha256sum -c 的校验文件
    with open(os.path.join(ROOT, "MANIFEST.sha256"), "w", encoding="utf-8", newline="\n") as fp:
        for h, _s, f in rows:
            fp.write("%s  %s\n" % (h, f))

    return len(rows), total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "dist", "%s.zip" % PROJECT))
    ap.add_argument("--no-manifest", action="store_true")
    args = ap.parse_args()

    os.chdir(ROOT)
    files = tracked_files()
    if not files:
        print("git 中没有跟踪文件？")
        return 1

    commit = git("rev-parse", "--short", "HEAD")
    dirty = git("status", "--porcelain")
    if dirty:
        print("警告：工作区有未提交改动，包里将是提交版内容 + 当前文件内容，二者可能不一致。")

    payload = list(files)
    if not args.no_manifest:
        n, total = build_manifest(files, commit, os.path.join(ROOT, "MANIFEST.txt"))
        print("清单：%d 个文件，%.2f MB" % (n, total / 1048576))
        payload += ["MANIFEST.txt", "MANIFEST.sha256"]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    crlf_fixed = []
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in payload:
            full = os.path.join(ROOT, rel)
            zi = zipfile.ZipInfo(rel, date_time=time.localtime(os.path.getmtime(full))[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            # 关键：显式声明文件名是 UTF-8。否则解压端会按本地编码猜，
            # 中文名（00_提交说明.md、docs/技术文档.docx）会变成乱码，sha256 -c 直接读不到文件。
            zi.flag_bits |= 0x800
            # 保留权限位：脚本 755，其余 644
            mode = 0o755 if rel.endswith((".sh", ".py")) else 0o644
            zi.external_attr = mode << 16
            with open(full, "rb") as fp:
                data = fp.read()
            # 文本脚本强制 LF：Windows 工作区出现 CRLF 时，包里若照搬，
            # 在 Linux 上执行会报 $'\r': command not found。改内存不改磁盘。
            if rel.endswith((".sh", ".py")) and b"\r\n" in data:
                crlf_fixed.append((rel, data.count(b"\r\n")))
                data = data.replace(b"\r\n", b"\n")
            z.writestr(zi, data, compresslevel=9)

    size = os.path.getsize(args.out)
    with zipfile.ZipFile(args.out) as z:
        bad = z.testzip()
        names = z.namelist()

    print("输出：%s" % args.out)
    print("内容：%d 个文件，压缩后 %.2f MB" % (len(names), size / 1048576))
    if bad:
        print("完整性校验失败：%s" % bad)
        return 1
    print("完整性：OK（zip 自检通过）")
    if crlf_fixed:
        print("已自动转为 LF（仅包内，未改磁盘）：")
        for rel, n in crlf_fixed:
            print("  %-30s %d 行" % (rel, n))

    # 清理临时生成的清单（它们已进包；是否入库由使用者决定）
    for f in ("MANIFEST.txt", "MANIFEST.sha256"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
