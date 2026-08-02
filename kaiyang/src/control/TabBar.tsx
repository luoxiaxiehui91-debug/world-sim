/**
 * Tab 导航栏组件
 * 五 Tab：天枢 / 天璇 / 天玑 / 玉衡 / 操作日志
 */

import { useControl } from '@/state/ControlContext';
import type { ControlTab, TabConfig } from '@/types/control';

const TABS: TabConfig[] = [
  { key: 'tianshu', label: '天枢', icon: '📡' },
  // 已评：保留镜像，等待后端 P1+
  { key: 'tianxuan', label: '天璇', icon: '🧠' },
  // 已评：保留镜像，等待后端 P1+
  { key: 'tianji', label: '天玑', icon: '🔍' },
  // 已评：保留镜像，等待后端 P1+
  { key: 'yuheng', label: '玉衡', icon: '⚖️' },
  // 已评：保留镜像，等待后端 P1+
  { key: 'operation_log', label: '日志', icon: '📋' },
];

export function TabBar() {
  const { activeTab, setActiveTab } = useControl();

  return (
    <nav className="flex shrink-0 gap-1 border-b border-white/5 px-3 py-2">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.key;
        return (
          <TabButton
            key={tab.key}
            tab={tab}
            isActive={isActive}
            onClick={() => setActiveTab(tab.key)}
          />
        );
      })}
    </nav>
  );
}

/** 单个 Tab 按钮 */
function TabButton({
  tab,
  isActive,
  onClick,
}: {
  tab: TabConfig;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium
        transition-colors duration-200
        ${
          isActive
            ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/30'
            : 'text-white/45 hover:text-white/70 hover:bg-white/5 border border-transparent'
        }
      `}
      title={tab.label}
    >
      <span className="text-xs leading-none">{tab.icon}</span>
      <span className="hidden sm:inline">{tab.label}</span>
    </button>
  );
}
