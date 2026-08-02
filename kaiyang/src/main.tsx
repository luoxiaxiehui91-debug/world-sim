import 'leaflet/dist/leaflet.css';
import React, { Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

/** 全局错误边界：防止单个组件崩溃导致白屏。 */
class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: string }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: '' };
  }
  static getDerivedStateFromError(error: Error) {
    window.__KAIYANG_RUNTIME_ERROR__ = error.message + '\n' + error.stack;
    return { hasError: true, error: error.message };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, color: '#ef4444', background: '#0a0e1a', minHeight: '100vh', fontFamily: 'monospace' }}>
          <h2>⚠ 开阳 运行时错误</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{this.state.error}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

declare global {
  interface Window { __KAIYANG_RUNTIME_ERROR__?: string; }
}

const container = document.getElementById('root');
if (!container) {
  throw new Error('找不到 #root 挂载点');
}

createRoot(container).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
