# 第三方组件与许可说明

本项目自身代码与文档采用 [MIT 许可证](LICENSE)。以下第三方组件不包含在该许可内，各自遵循原始许可：

| 组件 | 用途 | 许可 / 来源 |
|---|---|---|
| `llama.cpp`（spacemit-com fork） | 推理运行时，主线为 Bianbu 源提供的 `llama.cpp-tools-spacemit` 0.1.1 | 见 <https://github.com/spacemit-com/llama.cpp> |
| Qwen3.5-2B / 4B 模型权重 | 被优化的基座模型 | Apache-2.0，见 <https://huggingface.co/Qwen/Qwen3.5-2B> |
| `spine-runtime`（`vendor/`） | 交叉编译 v0.2.3 量化器时使用的预编译依赖 | 版权归 SpacemiT，见 `vendor/README.md` |
| `patches/0001-tcm-dev-path.patch` | 针对上游 0.1.1 的设备节点路径修正 | 遵循上游 llama.cpp 许可 |

## 分发边界

- 上游 `llama.cpp` 源码（约 180 MB）、模型原始权重（约 13 GB）、转换中间产物与量化 GGUF（约 24 GB）**不在本仓库内**，由 `scripts/00_fetch_models.sh`、`scripts/01_convert.sh` 等脚本按需获取或重新生成。
- `vendor/` 内为第三方二进制依赖，非本项目原创代码。
- 本仓库不包含赛题原文、评分表、答辩材料或任何参赛资格类文件。
