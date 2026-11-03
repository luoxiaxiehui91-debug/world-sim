# RELEASES — world-sim 版本摘要（给人看的）

> **用途**：一眼看清「这一版变了什么、对我有什么影响」。
> **不写**根因、改动文件清单、验证命令 —— 那些在 `CHANGELOG.md`（技术视角，极详细）。
> **维护约定**：每次发版在下方加一条，每条 **3–5 行**，只写用户/运维能感知的变化；不回溯更早历史。
> **最后更新**：2026-11-03

---

## 当前状态（as-of 2026-11-03 16:35 CST）

| 组件 | 版本 | 角色 |
|---|---|---|
| macro-scan（天枢） | **3.8.91** | 观测采集层 |
| macro-sim（天璇） | **v2.0.55** | 仿真层（20 Agent） |
| macro-ji（天玑） | **v1.0.13** | 验证评估层 |
| kaiyang（开阳） | **1.11.52** | 可视化面板（:8080） |

**LLM 模型栈**（2026-11-03 起）：

- 主分析（晨报/日报/宏观）→ `mimo-v2.6-pro`（小米 MiMo；429 限流时自动降级）
- 兜底 / 叙事 / 编年史 / 验证 → `deepseek-ai/DeepSeek-V4.1-Flash`（硅基流动）
- 标题翻译 → `tencent/Hunyuan-MT-7B`（免费）
- RAG 嵌入 → `BAAI/bge-m3`（免费）
- 天璇 MC 内核 → `THUDM/GLM-Z1-9B-0414`

---

## 2026-11-03 · macro-scan v3.8.91

- 降级链文档勘误：`MiMo v2.5-pro` → `MiMo v2.6-pro`（实际一直在跑 v2.6-pro，只是文档没跟上）。
- 纯注释修正，无行为变化。

## 2026-11-03 · macro-scan v3.8.90

- **模型换代**：DeepSeek 从 `V4-Flash` 升到 **`V4.1-Flash`**（5 个使用点全部切换）。
- **反而更省钱**：输入 −33%、输出 −11%、缓存 −87%（2–8 点低档更便宜，晨报/扫描正好落在该档）。
- 配置热生效，**不需要重启容器**；下一个定时任务自动用新模型。
- 顺带清理了一处已失效的 compose 示例配置（`SILICONFLOW_MODEL=`）。

---

> 更早的版本变化：`macro-scan/CHANGELOG.md`、`macro-sim/CHANGELOG.md`、`macro-ji/CHANGELOG.md`、`kaiyang/CHANGELOG.md`
> 系统架构与运行方式：`macro-scan/世界推演系统_人类说明文档.md`
> 实时交接（新 session 第一入口）：`STATUS.md`
