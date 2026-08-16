/**
 * 安全 UUID 生成（H01 修复, 2026-08-16）。
 * LAN HTTP（非安全上下文）下 `crypto.randomUUID()` 不可用（抛 TypeError）→
 * 控制面板 showToast / addLog / 批量重跑 idempotencyKey 调用处点按钮即崩。
 * 此工具优先用原生 API，不可用时 fallback 到 RFC4122 v4 拼装。
 */
export function safeUuid(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    /* 非安全上下文：crypto.randomUUID 不可用，走 fallback */
  }
  // RFC4122 v4 fallback（不依赖 crypto.getRandomValues——LAN HTTP 下同样可能受限）
  const seg = (len: number): string => {
    let s = '';
    for (let i = 0; i < len; i++) {
      s += Math.floor(Math.random() * 16).toString(16);
    }
    return s;
  };
  return `${seg(8)}-${seg(4)}-4${seg(3)}-${(8 + Math.floor(Math.random() * 4)).toString(16)}${seg(3)}-${seg(12)}`;
}
