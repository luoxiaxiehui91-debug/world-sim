import type { ComponentType } from 'react';
import { WorldPanel } from '@/components/WorldPanel';
import { GrvPanel } from '@/components/GrvPanel';
import { EconomyPanel } from '@/components/EconomyPanel';
import { NewsPanel } from '@/components/NewsPanel';
import { RiskSummaryPanel } from '@/components/RiskSummaryPanel';
import { SignalStreamPanel } from '@/components/SignalStreamPanel';
import { StatusMiniPanel } from '@/components/StatusMiniPanel';
import { NuclearWatchPanel } from '@/components/NuclearWatchPanel';

/** 面板注册项（扩展标准 #2）：新增面板只加一项，布局无需改动。 */
export interface PanelRegistration {
  id: string;
  title: string;
  /** 该面板依赖的主 feed（仅用于文档/排障） */
  feed: string;
  order: number;
  visible: boolean;
  /** 栅格类名（lg 断点下的 col-span）。1.7.0 起仅作文档参考，不再是布局源。 */
  className: string;
  component: ComponentType;
  /** react-grid-layout 初始布局（1.7.0 新增）。从原 className col-span 推导。 */
  defaultLayout: {
    /** 宽度（12 栅格单位） */
    w: number;
    /** 高度（80px 行单位） */
    h: number;
    /** 最小宽度（栅格单位） */
    minW: number;
    /** 最小高度（行单位） */
    minH: number;
  };
}

/**
 * 布局设计（lg 断点 12 栅格，参照 Bloomberg Terminal / Grafana 情报面板范式）：
 *
 *  行 0-5（h=6）：主视图区
 *   ┌─────────────┬──────────────────────────────────┬──────────────┐
 *   │ 风险摘要(2) │     世界视图 3D/平面 (7)          │ 信号流 (3)  │
 *   │             │   （地图是视觉主角，高度最高）    │             │
 *   └─────────────┴──────────────────────────────────┴──────────────┘
 *
 *  行 6-9（h=4）：数据分析区
 *   ┌─────────────────────┬───────────────────────────────────────┐
 *   │   GRV 维度 (4)      │        经济面板 (8)                   │
 *   └─────────────────────┴───────────────────────────────────────┘
 *
 *  行 10-13（h=4）：次要信息区
 *   ┌──────────┬───────────────────────────────┬──────────────────┐
 *   │ 数据状态 │        新闻面板 (6)            │  核设施监视 (3)  │
 *   │   (3)    │                               │                  │
 *   └──────────┴───────────────────────────────┴──────────────────┘
 *
 * 设计原则：
 *  1. 地图面板高度(h=6)远大于其他面板(h=4)，确保视觉主角地位
 *  2. 第一行三栏：左侧KPI + 中央地图 + 右侧信号流，信息密度均衡
 *  3. 第二行：GRV雷达图(窄) + 经济时序图(宽)，宽窄互补
 *  4. 第三行：状态(小) + 新闻(中) + 核监视(小)，次要面板紧凑排列
 *  5. 总高度约 14 行 × rowHeight，1080p 屏幕基本一屏显示
 */
export const PANELS: PanelRegistration[] = [
  {
    id: 'risk-summary', title: '风险摘要', feed: 'grv', order: 1, visible: true,
    className: 'lg:col-span-2', component: RiskSummaryPanel,
    defaultLayout: { w: 2, h: 8, minW: 2, minH: 4 },
  },
  {
    id: 'world', title: '世界视图（3D/平面）', feed: 'grv', order: 2, visible: true,
    className: 'lg:col-span-7', component: WorldPanel,
    defaultLayout: { w: 7, h: 8, minW: 4, minH: 5 },
  },
  {
    id: 'signal-stream', title: '最新信号流', feed: 'news', order: 3, visible: true,
    className: 'lg:col-span-3', component: SignalStreamPanel,
    defaultLayout: { w: 3, h: 8, minW: 2, minH: 4 },
  },
  {
    id: 'grv', title: 'GRV 维度', feed: 'grv', order: 4, visible: true,
    className: 'lg:col-span-4', component: GrvPanel,
    defaultLayout: { w: 4, h: 7, minW: 2, minH: 4 },
  },
  {
    id: 'economy', title: '经济面板', feed: 'fred', order: 5, visible: true,
    className: 'lg:col-span-8', component: EconomyPanel,
    defaultLayout: { w: 8, h: 7, minW: 3, minH: 4 },
  },
  {
    id: 'status-mini', title: '数据状态', feed: 'all', order: 6, visible: true,
    className: 'lg:col-span-3', component: StatusMiniPanel,
    defaultLayout: { w: 3, h: 5, minW: 2, minH: 3 },
  },
  {
    id: 'news', title: '新闻面板', feed: 'news', order: 7, visible: true,
    className: 'lg:col-span-6', component: NewsPanel,
    defaultLayout: { w: 6, h: 5, minW: 3, minH: 3 },
  },
  {
    id: 'nuclear-watch', title: '核设施分布', feed: 'nuclearSites', order: 8, visible: true,
    className: 'lg:col-span-3', component: NuclearWatchPanel,
    defaultLayout: { w: 3, h: 5, minW: 2, minH: 3 },
  },
];
