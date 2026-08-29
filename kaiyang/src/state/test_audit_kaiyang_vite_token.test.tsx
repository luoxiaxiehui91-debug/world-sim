import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement, type ReactElement } from 'react';

/**
 * 审计发现 #2 (HIGH security) 回归测试 — 控制 API 令牌优先级契约。
 *
 * 背景：
 *  - controlConfig.getEnvToken() 读取 import.meta.env.VITE_CONTROL_API_TOKEN，
 *    VITE_ 前缀的 env 会被 Vite 内联进【公开可读】的客户端 bundle。
 *  - ControlContext.resolveInitialToken()（模块顶层私有函数，经 initialState.token 生效）
 *    让 env 令牌【优先】于用户 localStorage 令牌：
 *        const env = getEnvToken(); if (env) return env; return getStoredToken();
 *  - 结果：把管理员写权限令牌打进前端产物，且它静默覆盖用户自己输入的令牌。
 *
 * 安全立场（期望行为）：用户显式输入/保存的 localStorage 令牌应优先，
 * 或至少 env 令牌不得在用户已有令牌时静默生效。
 *
 * 测试策略（沿用本项目「零新依赖 + node 环境 + renderToStaticMarkup」铁律）：
 *  resolveInitialToken 未导出，且 initialState.token 在【模块加载时】即算定，
 *  因此先 stub import.meta.env 与 globalThis.localStorage，再用 vi.resetModules()
 *  + 动态 import 触发 ControlContext 重新求值，最后 renderToStaticMarkup 装配
 *  ControlProvider 并从消费者侧读回 token。
 *
 * 这是【已确认但尚未修复】的缺陷 → 用 it.fails 断言【期望的安全行为】：
 *  bug 存在时该断言失败 = it.fails 通过（CI 绿）；bug 修复后断言通过 =
 *  it.fails 反转为失败，强制有人来摘掉标记，测试转为活体守卫。
 */

const USER_TOKEN = 'user-localStorage-token';
const ENV_TOKEN = 'env-inlined-admin-token';

/** 在 node 环境安装一个最小 localStorage 桩（controlConfig / getStoredToken 依赖它）。 */
function installLocalStorage(map: Record<string, string>): void {
  (globalThis as unknown as { localStorage: Storage }).localStorage = {
    getItem: (k: string) => (k in map ? map[k] : null),
    setItem: (k: string, v: string) => {
      map[k] = String(v);
    },
    removeItem: (k: string) => {
      delete map[k];
    },
    clear: () => {
      for (const k of Object.keys(map)) delete map[k];
    },
    key: () => null,
    length: 0,
  } as unknown as Storage;
}

/**
 * 重新加载 ControlContext（令 initialState.token 用当前 env/localStorage 重新求值），
 * 装配 ControlProvider 并从 useControl() 读回解析出的 token。
 */
async function resolveProviderToken(): Promise<string | null> {
  vi.resetModules();
  const { ControlProvider, useControl } = await import('@/state/ControlContext');

  let captured: string | null = null;
  function Probe(): ReactElement | null {
    captured = useControl().token;
    return null;
  }

  // renderToStaticMarkup 同步渲染，且不执行 useEffect（因此不触碰 controlApi/localStorage 写回）
  renderToStaticMarkup(
    createElement(ControlProvider, null, createElement(Probe)),
  );
  return captured;
}

describe('ControlContext 令牌优先级 · 安全契约（审计 #2）', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    delete (globalThis as unknown as { localStorage?: Storage }).localStorage;
  });

  it.fails(
    '用户 localStorage 令牌应优先于 VITE_ env 内联令牌（当前 env 优先=安全缺陷）',
    async () => {
      installLocalStorage({ kaiyang_control_token: USER_TOKEN });
      vi.stubEnv('VITE_CONTROL_API_TOKEN', ENV_TOKEN);

      const token = await resolveProviderToken();

      // 期望：用户显式保存的令牌胜出，env 内联令牌不得静默覆盖它。
      expect(token).toBe(USER_TOKEN);
    },
  );

  // ── 绿色锚点：不涉及缺陷、恒真的行为，验证测试基础设施（stub + 重载 + 渲染）本身可靠 ──
  it('仅有 localStorage 令牌、无 env 时，解析出用户令牌', async () => {
    installLocalStorage({ kaiyang_control_token: USER_TOKEN });
    vi.stubEnv('VITE_CONTROL_API_TOKEN', '');

    const token = await resolveProviderToken();
    expect(token).toBe(USER_TOKEN);
  });
});
