# vendor — 第三方预编译依赖

本目录存放**非本项目产出**的第三方二进制依赖，仅为在无法访问 GitHub 的环境中复现构建而随仓库提供。

## spine-runtime.riscv64.0.6.3.tar.gz

| 项 | 内容 |
|---|---|
| 来源 | `https://github.com/spacemit-com/spine-runtime/releases/download/0.6.3/` |
| 提供方 | 进迭时空（SpacemiT） |
| 体积 | 76 KB |
| sha256 | 见仓库根目录 `docs/VERSIONS.md` 或执行 `sha256sum vendor/spine-runtime.riscv64.0.6.3.tar.gz` |
| 用途 | **仅**用于编译 llama.cpp v0.2.3（`-DGGML_SPACEMIT=ON -DSPERT_DIR=...`） |
| 是否必需 | **否**。项目主线使用 0.1.1，其构建不依赖 SPERT（见 `docs/PATCH_TCM.md`） |

### 为什么随仓库提供

v0.2.3 的 `ggml-spacemit` 后端在 CMake 阶段会强制要求 `SPERT_DIR`，缺少该包会直接报
`SPERT_DIR is not set` 而配置失败。该 release 托管在被网络策略拦截的 `github.com` 上，
因此在受限网络下复现时随仓库提供一份，避免阻塞。

### 使用方式

```bash
tar xzf vendor/spine-runtime.riscv64.0.6.3.tar.gz -C /tmp/
export SPERT_DIR=/tmp/spine-runtime.riscv64.0.6.3
```

### 许可

该二进制由进迭时空发布，遵循其原始许可，本项目不主张任何权利。如需最新版本或源码，
请前往上游仓库获取。

---

## 说明

本项目自身产出的代码与文档均为 MIT 许可（见根目录 `LICENSE`）。本目录内容除外。
