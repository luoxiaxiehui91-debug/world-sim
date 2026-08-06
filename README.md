# world-sim — 世界推演系统 Monorepo

本仓库整合了两个宏观分析系统，统一管理源码与部署。

> **系统总览**：见 [`docs/overview.md`](docs/overview.md)（功能/使用/运维一页通）。  
> **AI 工作入口**：见 [`AGENTS.md`](AGENTS.md)（系统定位、阅读路径、操作约束）。  
> **GitHub**：[luoxiaxiehui91-debug/world-sim](https://github.com/luoxiaxiehui91-debug/world-sim)（private）

## 目录结构

```
world-sim/
├── macro-scan/              宏观信号观测系统（天枢）
├── macro-sim/               宏观演化仿真系统（天璇）
├── kaiyang/                 可视化操作面板（开阳）v1.9.0
├── macro-ji/                天玑（验证层）macro-ji v1.0.0（独立容器）
├── docs/
│   ├── overview.md          系统总览（功能/架构/运维一页通）
│   └── tianji-design.md     天玑（验证层）设计文档 v1.0
├── deploy.sh                统一部署脚本
├── ROADMAP.md               项目内权威 todo（时间门控任务 + 天玑路线图）
├── AGENTS.md                AI 工作入口
└── README.md                本文件
```

## 子系统说明

### macro-scan — 宏观信号观测系统
- 功能：实时抓取宏观经济指标、新闻、地缘风险信号，进行综合评估和报告生成
- NAS 运行路径：`/vol2/1000/software/macro-scan`
- 版本：v3.8.15（镜像 macro-scan:v7）
- 详见 [macro-scan/README.md](macro-scan/README.md)

### macro-sim — 宏观演化仿真系统
- 功能：基于当前宏观状态进行多智能体仿真，压力测试宏观假设路径
- NAS 运行路径：`/vol2/1000/software/macro-sim`
- 版本：v2.0.23
- 详见 [macro-sim/README.md](macro-sim/README.md)

### kaiyang — 可视化操作面板（开阳）
- 功能：只读展示天枢产出数据，3D地球 + 经济面板 + 控制抽屉（MOCK_ENABLED=false，A3a 控制 API 已接入，HTTP REST :8900）
- NAS 访问：`http://192.168.31.108:8080`
- 版本：v1.9.0
- 详见 [kaiyang/README.md](kaiyang/README.md)

### macro-ji — 天玑（验证层）
- 功能：对天枢/天璇产出的预测做事后验证与校准（narrative_chunks / predictions / forecasts）
- NAS 运行路径：`/vol2/1000/software/world-sim/macro-ji`（源码仓库，构建源；容器 = macro-tianji:latest 镜像 COPY，无独立运行区）
- 版本：macro-ji v1.0.0，独立容器 `macro-scan-tianji-1`（healthy，08-04 22:37 上线，代码 ≡ 仓库）
- 与天璇共享 `forecast_tracker.db`（两容器共用同一数据目录）

## 部署

```bash
# 部署全部
bash deploy.sh

# 仅部署 macro-scan
bash deploy.sh macro-scan

# 仅部署 macro-sim
bash deploy.sh macro-sim
```

## 开发说明

- 源码工作目录：`S:\world-sim\`（本地 NAS 挂载）
- NAS 生产目录保持不变，deploy.sh 直接 rsync 推送
- 两个子系统的接口变更在同一 PR 中同步修改，避免断链

## 迁移说明

本仓库由以下两个独立仓库合并而来：
- `luoxiaxiehui91-debug/macro-scan` → `world-sim/macro-scan/`
- `luoxiaxiehui91-debug/macro-sim` → `world-sim/macro-sim/`
