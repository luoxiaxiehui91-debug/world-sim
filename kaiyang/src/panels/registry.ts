import type { ComponentType } from 'react';
import { WorldPanel } from '@/components/WorldPanel';
import { GrvPanel } from '@/components/GrvPanel';
import { EconomyPanel } from '@/components/EconomyPanel';
import { NewsPanel } from '@/components/NewsPanel';
import { RiskSummaryPanel } from '@/components/RiskSummaryPanel';
import { SignalStreamPanel } from '@/components/SignalStreamPanel';
import { StatusMiniPanel } from '@/components/StatusMiniPanel';

/** 面板注册项（扩展标准 #2）：新增面板只加一项，布局无需改动。 */
export interface PanelRegistration {
  id: string;
  title: string;
  /** 该面板依赖的主 feed（仅用于文档/排障） */
  feed: string;
  order: number;
  visible: boolean;
  /** 栅格类名（lg 断点下的 col-span） */
  className: string;
  component: ComponentType;
}

/**
 * 布局（lg 断点 12 栅格）：
 *   第一行：风险摘要(2) + 世界视图(7) + 信号流(3)
 *   第二行：GRV 维度(5) + 经济面板(7)
 *   第三行：数据状态(3) + 新闻面板(9)
 * 小屏自动降级为单列（App 的 grid-cols-1）。
 */
export const PANELS: PanelRegistration[] = [
  { id: 'risk-summary', title: '风险摘要', feed: 'grv', order: 1, visible: true, className: 'lg:col-span-2', component: RiskSummaryPanel },
  { id: 'world', title: '世界视图（3D/平面）', feed: 'grv', order: 2, visible: true, className: 'lg:col-span-7', component: WorldPanel },
  { id: 'signal-stream', title: '最新信号流', feed: 'news', order: 3, visible: true, className: 'lg:col-span-3', component: SignalStreamPanel },
  { id: 'grv', title: 'GRV 维度', feed: 'grv', order: 4, visible: true, className: 'lg:col-span-5', component: GrvPanel },
  { id: 'economy', title: '经济面板', feed: 'fred', order: 5, visible: true, className: 'lg:col-span-7', component: EconomyPanel },
  { id: 'status-mini', title: '数据状态', feed: 'all', order: 6, visible: true, className: 'lg:col-span-3', component: StatusMiniPanel },
  { id: 'news', title: '新闻面板', feed: 'news', order: 7, visible: true, className: 'lg:col-span-9', component: NewsPanel },
];
