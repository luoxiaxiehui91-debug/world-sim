# 文档全面检查与整理实录（2026-08-10）

> 文档类别：实录（RECORD）
> 范围：WorkBuddy 工作区（C:\Users\luoxi\WorkBuddy\世界推演系统\）+ repo（/vol2/1000/software/world-sim/）
> 触发：用户"检查并整理所有文档"（承接 08-10 漂移审计 + 日志补救后）

---

## 检查结果

### 一、已同步一致（md5 双端相等）✅
| 文档 | 位置 |
|------|------|
| STATUS.md / 项目导航.md | repo 根 |
| worldsim-review-synthesis.md | docs/archive/（07-31 快照 + 时效指针） |
| calib-*.md ×9 | docs/calib/ |

### 二、同名双端文档（定位不同，非漂移，本次补分治声明）⚠️→已整理
| 文档 | 工作区版 | repo 版 | 处置 |
|------|----------|---------|------|
| README.md | 工作区摘要（1.6KB） | Monorepo 权威入口（4KB） | 工作区版头部加分治声明 |
| AGENTS.md | 工作区精简（1.5KB） | NAS AI 入口权威（5.5KB） | 同上 |
| ROADMAP.md | R4 摘要（1.6KB） | 权威 todo 完整版（14KB） | 同上 |

### 三、repo 侧信息过时（本次已更新）⚠️→已整理
| 文档 | 过时点 | 更新 |
|------|--------|------|
| AGENTS.md | macro-sim v2.0.25（实为 v2.0.40）；macro-scan v3.8.15（实为 v3.8.16）；缺 R4 红线/soul 坑；交接指向 HANDOVER | 版本 3 处 + 约束补 3 行 + 阅读路径补 STATUS + 导航改指向 STATUS/calib/operations |
| ROADMAP.md | 缺 R4 系列状态（08-07 后未更新） | 补 R4 系列状态节（v2.0.37→v2.0.40 + silence 挂起）+ 头部声明 |
| HANDOVER.md | 停在 08-07（规则"每次维护后必须更新"断点） | 追加 08-10 状态块（append-only），声明实时交接职责移交 STATUS.md |

### 四、散落文档归档（本次归档入 repo）📦
| 来源 | 文件 | 去向 |
|------|------|------|
| 工作区根 | docs-audit-漂移清单-2026-08-05.md / docs-audit-交叉对比-2026-08-06.md（历史审计实录） | docs/archive/ |
| C:\tmp\r4h_data\ | R4H_QA 验收清单×3 / RoleVerdict×3 / 执行Runbook / 交叉参考×2 / EASE补采快照（R4h 验收实录 9 份） | docs/calib/ |

### 五、维持现状（有意不动）
- C:\tmp 大量 build stdout/探针脚本：临时区，非文档权威区，不动
- repo docs/archive/ 21 份历史归档：实录，保留
- 未跟踪 docs/archive/nas-deploy-prompt-v3.8.6.md ×2：内容不确定（08-06 裁决不处理）

---

## 处置记录

- commit：e8fc907（08-10 日志补救 1）+ d1427ee（日志补救 2）+ 本次整理 commit（见 git log）
- 双端文档关系新约定：**工作区 = 摘要/工作视角；repo = 权威完整版**；同名的 README/AGENTS/ROADMAP 以 repo 为权威，工作区版头部声明指向
- 实时交接职责：HANDOVER.md（08-07 起停更）→ STATUS.md（repo 根，08-10 同步）接替；AGENTS.md 阅读路径已改指向
- 后续维护：任何 session 动 repo 根 6 个 md 时，若内容属于"权威完整版"范畴，同步考虑工作区摘要版是否需跟新（反之亦然）

---

## 遗留（下次整理关注）
1. HANDOVER.md 头部规则"每次维护后必须更新本文件"与 STATUS.md 职责重叠——下次维护时改规则为"STATUS.md 为实时交接，HANDOVER 仅记录重大里程碑快照"
2. repo 根 README 子系统版本行（macro-scan v3.8.15 等 as-of 08-06）仍偏旧——版本权威在各 CHANGELOG，导航行按需更新
3. docs/archive/ 21 份历史归档可考虑建索引（INDEX.md）便于检索
