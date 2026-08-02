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
 * 布局（lg 断点 12 栅格）：
 *   第一行：风险摘要(2) + 世界视图(7) + 信号流(3)    → y=0
 *   第二行：GRV 维度(5) + 经济面板(7)                → y=4
 *   第三行：数据状态(3) + 新闻面板(9)                → y=8
 *   第四行：核设施监视(4)                            → y=12
 * 小屏自动降级为单列（react-grid-layout cols={{ lg: 12, md: 1, sm: 1 }}）。
 *
 * ⚠ 交错编辑约定（Wave2）：新增面板一律**追加到数组末尾**并使用新的 order，
 * 不重排、不改写既有项的 order/className/defaultLayout，避免与并行改动冲突。
 */
export const PANELS: PanelRegistration[] = [
  {
    id: 'risk-summary', title: '风险摘要', feed: 'grv', order: 1, visible: true,
    className: 'lg:col-span-2', component: RiskSummaryPanel,
    defaultLayout: { w: 2, h: 4, minW: 2, minH: 2 },
  },
  {
    id: 'world', title: '世界视图（3D/平面）', feed: 'grv', order: 2, visible: true,
    className: 'lg:col-span-7', component: WorldPanel,
    defaultLayout: { w: 7, h: 5, minW: 2, minH: 2 },
  },
  {
    id: 'signal-stream', title: '最新信号流', feed: 'news', order: 3, visible: true,
    className: 'lg:col-span-3', component: SignalStreamPanel,
    defaultLayout: { w: 3, h: 4, minW: 2, minH: 2 },
  },
  {
    id: 'grv', title: 'GRV 维度', feed: 'grv', order: 4, visible: true,
    className: 'lg:col-span-5', component: GrvPanel,
    defaultLayout: { w: 5, h: 4, minW: 2, minH: 2 },
  },
  {
    id: 'economy', title: '经济面板', feed: 'fred', order: 5, visible: true,
    className: 'lg:col-span-7', component: EconomyPanel,
    defaultLayout: { w: 7, h: 4, minW: 2, minH: 2 },
  },
  {
    id: 'status-mini', title: '数据状态', feed: 'all', order: 6, visible: true,
    className: 'lg:col-span-3', component: StatusMiniPanel,
    defaultLayout: { w: 3, h: 4, minW: 2, minH: 2 },
  },
  {
    id: 'news', title: '新闻面板', feed: 'news', order: 7, visible: true,
    className: 'lg:col-span-9', component: NewsPanel,
    defaultLayout: { w: 9, h: 4, minW: 2, minH: 2 },
  },
  {
    id: 'nuclear-watch', title: '核设施监视', feed: 'nuclearSites', order: 8, visible: true,
    className: 'lg:col-span-4', component: NuclearWatchPanel,
    defaultLayout: { w: 4, h: 4, minW: 2, minH: 2 },
  },
];
