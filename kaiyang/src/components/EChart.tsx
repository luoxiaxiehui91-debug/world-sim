import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { CSSProperties } from 'react';

/** 轻量 ECharts 封装：自适应容器尺寸，option 变化时整体重绘。 */
export function EChart({
  option,
  className,
  style,
}: {
  option: echarts.EChartsOption;
  className?: string;
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener('resize', onResize);
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      window.removeEventListener('resize', onResize);
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} className={className} style={style} />;
}
