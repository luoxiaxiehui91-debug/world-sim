"""
web_server.py — 世界推演系统 Web 对话界面（Phase 3A）

提供比 ntfy 更好的 Q&A 体验：浏览器访问，支持自由提问和历史查询。

端口：8899（局域网访问：http://<部署主机>:8899）
依赖：pip install fastapi uvicorn（容器内按需安装）

启动方式（entrypoint.sh 追加）：
  python3 /app/web_server.py >> /var/log/macro-scan/web.log 2>&1 &
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    import uvicorn
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False
    print("[web_server] fastapi/uvicorn 未安装，请运行: pip install fastapi uvicorn")
    sys.exit(0)

try:
    from optim_config import DATA_DIR, WORKSPACE
except ImportError:
    WORKSPACE = Path(__file__).parent.parent
    DATA_DIR  = str(Path(WORKSPACE) / "data")

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

app = FastAPI(title="世界推演系统", docs_url=None, redoc_url=None)

# ── HTML 前端 ─────────────────────────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>世界推演系统</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0d1117; color: #e6edf3; height: 100vh; display: flex; flex-direction: column; }
  header { padding: 12px 20px; background: #161b22; border-bottom: 1px solid #30363d;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 16px; font-weight: 600; color: #58a6ff; }
  header .status { font-size: 12px; color: #8b949e; margin-left: auto; }
  .tabs { display: flex; gap: 4px; padding: 8px 16px; background: #161b22;
          border-bottom: 1px solid #30363d; }
  .tab { padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
         color: #8b949e; border: none; background: none; }
  .tab.active { background: #21262d; color: #e6edf3; }
  .panel { display: none; flex: 1; overflow: hidden; }
  .panel.active { display: flex; flex-direction: column; }
  /* Chat panel */
  #chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.6; }
  .msg.user { background: #1f6feb; color: #fff; align-self: flex-end; border-radius: 10px 10px 2px 10px; }
  .msg.bot  { background: #21262d; color: #e6edf3; align-self: flex-start; border-radius: 10px 10px 10px 2px; white-space: pre-wrap; }
  .msg.loading { color: #8b949e; font-style: italic; }
  #chat-input-row { display: flex; gap: 8px; padding: 12px 16px; background: #161b22; border-top: 1px solid #30363d; }
  #chat-input { flex: 1; padding: 10px 14px; background: #21262d; border: 1px solid #30363d;
                border-radius: 8px; color: #e6edf3; font-size: 14px; resize: none; }
  #chat-input:focus { outline: none; border-color: #58a6ff; }
  #chat-send { padding: 10px 18px; background: #238636; border: none; border-radius: 8px;
               color: #fff; cursor: pointer; font-size: 14px; }
  #chat-send:hover { background: #2ea043; }
  /* Status panel */
  #status-panel { flex: 1; overflow-y: auto; padding: 16px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 14px; margin-bottom: 12px; }
  .card h3 { font-size: 13px; color: #58a6ff; margin-bottom: 10px; }
  .card table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .card td { padding: 4px 8px; color: #c9d1d9; }
  .card td:first-child { color: #8b949e; width: 40%; }
  /* Situations panel */
  #situations-panel { flex: 1; overflow-y: auto; padding: 16px; }
  .situation-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
                    padding: 12px 14px; margin-bottom: 8px; }
  .situation-card .name { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
  .situation-card .meta { font-size: 12px; color: #8b949e; }
  .situation-card .signals { font-size: 12px; color: #7c8491; margin-top: 6px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 8px; }
  .badge.escalating { background: #3d1f1f; color: #f85149; }
  .badge.watching   { background: #1f2d3d; color: #58a6ff; }
  .badge.de-escalating { background: #1f3d2d; color: #3fb950; }
  .badge.calm       { background: #21262d; color: #8b949e; }
  /* Quick actions */
  .quick-btns { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 16px 0; }
  .quick-btn { padding: 5px 12px; background: #21262d; border: 1px solid #30363d;
               border-radius: 16px; color: #8b949e; cursor: pointer; font-size: 12px; }
  .quick-btn:hover { border-color: #58a6ff; color: #58a6ff; }
</style>
</head>
<body>
<header>
  <h1>📡 世界推演系统</h1>
  <span class="status" id="server-status">连接中…</span>
</header>
<div class="tabs">
  <button class="tab active" onclick="switchTab('chat')">💬 问答</button>
  <button class="tab" onclick="switchTab('situations')">🗺 事件追踪</button>
  <button class="tab" onclick="switchTab('grv')">📈 GRV 趋势</button>
  <button class="tab" onclick="switchTab('status')">📊 系统状态</button>
</div>

<!-- 快速提问按钮 -->
<div class="quick-btns" id="quick-btns">
  <span class="quick-btn" onclick="quickAsk('现在最值得担心的3件事？')">最值得担心的事</span>
  <span class="quick-btn" onclick="quickAsk('台海最近有什么新动向？')">台海动向</span>
  <span class="quick-btn" onclick="quickAsk('美联储下次会议预期如何？')">美联储预期</span>
  <span class="quick-btn" onclick="quickAsk('中国经济当前状态？')">中国经济</span>
  <span class="quick-btn" onclick="quickAsk('今日世界摘要')">今日摘要</span>
</div>

<div class="panel active" id="panel-chat">
  <div id="chat-messages"></div>
  <div id="chat-input-row">
    <textarea id="chat-input" rows="2" placeholder="输入问题，按 Enter 发送（Shift+Enter 换行）…"></textarea>
    <button id="chat-send" onclick="sendChat()">发送</button>
  </div>
</div>

<div class="panel" id="panel-situations">
  <div id="situations-panel"><p style="color:#8b949e;padding:20px">加载中…</p></div>
</div>

<div class="panel" id="panel-grv">
  <div id="grv-panel" style="padding:16px">
    <p style="color:#8b949e;font-size:13px;margin-bottom:12px">过去7天地缘风险向量（GRV）变化趋势</p>
    <canvas id="grv-chart" height="280" style="width:100%;max-width:800px"></canvas>
    <div id="grv-current" style="margin-top:16px;font-size:13px;color:#8b949e"></div>
  </div>
</div>

<div class="panel" id="panel-status">
  <div id="status-panel"><p style="color:#8b949e;padding:20px">加载中…</p></div>
</div>

<script>
const msgs = document.getElementById('chat-messages');

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('panel-' + name).classList.add('active');
  document.getElementById('quick-btns').style.display = name === 'chat' ? 'flex' : 'none';
  if (name === 'status') loadStatus();
  if (name === 'situations') loadSituations();
  if (name === 'grv') loadGRV();
}

function addMsg(role, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  d.textContent = text;
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
  return d;
}

function quickAsk(q) {
  document.getElementById('chat-input').value = q;
  sendChat();
}

async function sendChat() {
  const inp = document.getElementById('chat-input');
  const q = inp.value.trim();
  if (!q) return;
  inp.value = '';
  addMsg('user', q);
  const loading = addMsg('bot loading', '思考中…');
  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q})
    });
    const data = await res.json();
    loading.className = 'msg bot';
    loading.textContent = data.answer || data.error || '无响应';
  } catch(e) {
    loading.className = 'msg bot';
    loading.textContent = '请求失败：' + e;
  }
}

document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

async function loadStatus() {
  const panel = document.getElementById('status-panel');
  panel.innerHTML = '<p style="color:#8b949e;padding:20px">加载中…</p>';
  try {
    const res = await fetch('/status');
    const d = await res.json();
    panel.innerHTML = `
      <div class="card"><h3>系统状态</h3><table>
        <tr><td>GRV 台海</td><td>${d.grv?.taiwan_strait ?? 'N/A'}</td></tr>
        <tr><td>GRV 中美</td><td>${d.grv?.us_china_strategic ?? 'N/A'}</td></tr>
        <tr><td>GRV 俄欧</td><td>${d.grv?.russia_europe ?? 'N/A'}</td></tr>
        <tr><td>GRV 中东能源</td><td>${d.grv?.middle_east_energy ?? 'N/A'}</td></tr>
        <tr><td>GRV 来源质量</td><td>${d.grv?.source_quality ?? 'N/A'}</td></tr>
      </table></div>
      <div class="card"><h3>最新报告</h3><table>
        ${(d.recent_reports || []).slice(0,5).map(r =>
          `<tr><td>${r.date}</td><td>${r.name}</td></tr>`).join('')}
      </table></div>
      <div class="card"><h3>数据状态</h3><table>
        <tr><td>新闻库文章数</td><td>${d.news_count ?? 'N/A'}</td></tr>
        <tr><td>最后扫描</td><td>${d.last_scan ?? 'N/A'}</td></tr>
        <tr><td>GRV 更新时间</td><td>${d.grv_updated ?? 'N/A'}</td></tr>
        <tr><td>气候风险</td><td>${d.climate_risk ?? 'N/A'}</td></tr>
      </table></div>`;
  } catch(e) {
    panel.innerHTML = '<p style="color:#f85149;padding:20px">加载失败：' + e + '</p>';
  }
}

async function loadSituations() {
  const panel = document.getElementById('situations-panel');
  panel.innerHTML = '<p style="color:#8b949e;padding:20px">加载中…</p>';
  try {
    const res = await fetch('/situations');
    const situations = await res.json();
    const badges = {escalating:'escalating',watching:'watching','de-escalating':'de-escalating',calm:'calm'};
    const labels = {escalating:'🔴 升级中',watching:'🔵 观察中','de-escalating':'🟡 缓和中',calm:'⚪ 平静'};
    panel.innerHTML = situations.map(s => `
      <div class="situation-card">
        <div class="name">${s.name}<span class="badge ${badges[s.status]||'watching'}">${labels[s.status]||s.status}</span></div>
        <div class="meta">类别：${s.category} · 开始：${s.started} · 更新：${s.last_updated}</div>
        ${s.notes ? `<div class="meta" style="margin-top:4px">${s.notes}</div>` : ''}
        ${(s.recent_signals||[]).length > 0 ?
          `<div class="signals">📰 ${s.recent_signals[0].slice(0,80)}…</div>` : ''}
      </div>`).join('') || '<p style="color:#8b949e;padding:20px">暂无追踪事件</p>';
  } catch(e) {
    panel.innerHTML = '<p style="color:#f85149;padding:20px">加载失败：' + e + '</p>';
  }
}

async function loadGRV() {
  try {
    const res = await fetch('/grv-history');
    const data = await res.json();
    const keys = ['taiwan_strait','us_china_strategic','russia_europe','middle_east_energy'];
    const labels = {'taiwan_strait':'台海','us_china_strategic':'中美','russia_europe':'俄欧','middle_east_energy':'中东能源'};
    const colors = ['#58a6ff','#3fb950','#d29922','#f85149'];

    const canvas = document.getElementById('grv-chart');
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth || 700;
    const W = canvas.width, H = 280;
    ctx.clearRect(0,0,W,H);

    // 背景
    ctx.fillStyle = '#161b22';
    ctx.fillRect(0,0,W,H);

    const history = data.history || [];
    if (!history.length) {
      ctx.fillStyle = '#8b949e'; ctx.font = '14px sans-serif';
      ctx.fillText('暂无历史数据（需积累7天GDELT数据）', 20, H/2);
      return;
    }

    const pad = {t:20, r:20, b:40, l:45};
    const cW = W - pad.l - pad.r, cH = H - pad.t - pad.b;
    const n = history.length;
    const allVals = history.flatMap(d => keys.map(k => d[k]).filter(v=>v!=null));
    const minV = Math.max(0, Math.min(...allVals) - 5);
    const maxV = Math.min(100, Math.max(...allVals) + 5);

    // 网格
    ctx.strokeStyle = '#30363d'; ctx.lineWidth = 0.5;
    for (let g = 0; g <= 4; g++) {
      const y = pad.t + (g/4)*cH;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l+cW, y); ctx.stroke();
      const val = Math.round(maxV - (g/4)*(maxV-minV));
      ctx.fillStyle = '#8b949e'; ctx.font = '11px sans-serif';
      ctx.textAlign = 'right'; ctx.fillText(val, pad.l-4, y+4);
    }

    // 折线
    keys.forEach((k, ki) => {
      ctx.beginPath(); ctx.strokeStyle = colors[ki]; ctx.lineWidth = 2;
      history.forEach((d, i) => {
        const v = d[k];
        if (v == null) return;
        const x = pad.l + (i/(n-1))*cW;
        const y = pad.t + (1-(v-minV)/(maxV-minV))*cH;
        i === 0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
      });
      ctx.stroke();
      // 图例
      const lx = pad.l + ki * (cW/4);
      ctx.fillStyle = colors[ki]; ctx.font = '11px sans-serif'; ctx.textAlign = 'left';
      ctx.fillRect(lx, H-28, 12, 3);
      ctx.fillText(labels[k], lx+16, H-22);
    });

    // X轴日期
    const step = Math.ceil(n/5);
    ctx.fillStyle = '#8b949e'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
    history.forEach((d, i) => {
      if (i % step === 0 || i === n-1) {
        const x = pad.l + (i/(n-1||1))*cW;
        ctx.fillText((d.date||'').slice(5), x, H-8);
      }
    });

    // 当前值
    const cur = data.current || {};
    const curDiv = document.getElementById('grv-current');
    curDiv.innerHTML = keys.map((k,i) =>
      `<span style="color:${colors[i]};margin-right:16px">${labels[k]}: <strong>${cur[k]??'N/A'}</strong></span>`
    ).join('');
  } catch(e) {
    document.getElementById('grv-panel').innerHTML += '<p style="color:#f85149">加载失败：'+e+'</p>';
  }
}

// 健康检查
fetch('/health').then(r => r.json()).then(d => {
  document.getElementById('server-status').textContent = '● 在线 ' + d.time;
}).catch(() => {
  document.getElementById('server-status').textContent = '● 离线';
});
</script>
</body>
</html>"""


# ── API 路由 ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().strftime("%H:%M")}


@app.post("/ask")
async def ask(request: Request):
    """自由提问：注入当前快照 context，调用 LLM 回答。"""
    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "问题不能为空"}, status_code=400)

    try:
        context_parts = []

        # GRV
        grv_path = os.path.join(DATA_DIR, "grv_latest.json")
        if os.path.exists(grv_path):
            with open(grv_path, encoding="utf-8") as f:
                grv = json.load(f)
            grv_lines = ["[地缘风险 GRV]"]
            for k, label in [("taiwan_strait","台海"),("us_china_strategic","中美"),
                              ("russia_europe","俄欧"),("middle_east_energy","中东能源")]:
                v = grv.get(k)
                if v is not None:
                    grv_lines.append(f"  {label}: {v:.1f}")
            context_parts.append("\n".join(grv_lines))

        # 情境事件
        try:
            from situation_tracker import get_context as _gc
            ctx = _gc(max_events=5)
            if ctx:
                context_parts.append(ctx)
        except Exception:
            pass

        # 最新弱信号
        sig_path = os.path.join(DATA_DIR, "weak_signal_log.json")
        if os.path.exists(sig_path):
            with open(sig_path, encoding="utf-8") as f:
                log = json.load(f)
            recent = (log if isinstance(log, list) else [])[-5:]
            if recent:
                sig_lines = ["[近期弱信号]"]
                for s in recent:
                    sig_lines.append(f"  {s.get('indicator_name','')} {s.get('level','')} {s.get('value','')}")
                context_parts.append("\n".join(sig_lines))

        # 气候信号
        climate_path = os.path.join(DATA_DIR, "climate_signals.json")
        if os.path.exists(climate_path):
            try:
                from fetch_climate_signals import get_context as _cc
                cc = _cc()
                if cc:
                    context_parts.append(cc)
            except Exception:
                pass

        # 自然灾害信号
        disaster_path = os.path.join(DATA_DIR, "disaster_signals.json")
        if os.path.exists(disaster_path):
            try:
                from fetch_disaster_signals import get_context as _ddc
                ddc = _ddc()
                if ddc:
                    context_parts.append(ddc)
            except Exception:
                pass

        context = "\n\n".join(context_parts) if context_parts else "（当前无缓存数据）"
        prompt = (
            f"用户问题：{question}\n\n"
            f"当前系统数据快照：\n{context}\n\n"
            "请根据以上数据直接回答用户问题，用中文，简洁准确，250字以内。"
            "如果数据不足以回答，明确说明缺少哪方面的数据，不要猜测。"
        )

        from hybrid_llm import reason
        system = "你是宏观世界分析助手，回答基于提供的数据快照，言简意赅，区分已知事实和推断。"
        answer = reason(prompt, system=system, mode="auto", max_tokens=500)
        return {"answer": answer.strip()}

    except Exception as e:
        return JSONResponse({"error": f"处理失败：{str(e)}"}, status_code=500)


@app.get("/status")
async def status():
    """返回系统状态 JSON：GRV + 最新报告 + 数据统计。"""
    result = {}

    # GRV
    grv_path = os.path.join(DATA_DIR, "grv_latest.json")
    if os.path.exists(grv_path):
        with open(grv_path, encoding="utf-8") as f:
            grv_data = json.load(f)
        result["grv"] = grv_data
        result["grv_updated"] = grv_data.get("updated", "N/A")
    else:
        result["grv"] = {}

    # 最新报告
    report_dir = Path(WORKSPACE) / "docs" / "分析报告"
    reports = []
    if report_dir.exists():
        for p in sorted(report_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            reports.append({"name": p.stem[:40], "date": datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")})
    result["recent_reports"] = reports

    # news.db → PG（E0-C）
    try:
        import pg_read as _pg
        conn = _pg.connect()
        if conn is not None:
            result["news_count"] = conn.execute("SELECT COUNT(*) FROM news.articles").fetchone()[0]
            last = conn.execute("SELECT MAX(ingested_at) FROM news.articles").fetchone()[0]
            result["last_scan"] = (last or "N/A")[:16]
            conn.close()
    except Exception:
        result["news_count"] = "N/A"

    # 气候
    climate_path = os.path.join(DATA_DIR, "climate_signals.json")
    if os.path.exists(climate_path):
        with open(climate_path, encoding="utf-8") as f:
            cl = json.load(f)
        result["climate_risk"] = f"{cl.get('risk_level','N/A')}（{cl.get('climate_risk_score',0):.0f}/100）"

    # 自然灾害
    disaster_path = os.path.join(DATA_DIR, "disaster_signals.json")
    if os.path.exists(disaster_path):
        with open(disaster_path, encoding="utf-8") as f:
            dis = json.load(f)
        level = dis.get("risk_level", "low")
        score = dis.get("disaster_risk_score", 0)
        alerts = dis.get("alerts", [])
        result["disaster_risk"] = f"{level}（{score:.0f}/100）"
        if alerts:
            result["disaster_alerts"] = alerts[:2]

    return result


@app.get("/situations")
async def situations():
    """返回当前追踪事件列表。"""
    try:
        from situation_tracker import list_situations
        return list_situations()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/grv")
async def grv():
    """返回 GRV 向量当前值。"""
    grv_path = os.path.join(DATA_DIR, "grv_latest.json")
    if not os.path.exists(grv_path):
        return JSONResponse({"error": "GRV 数据不存在"}, status_code=404)
    with open(grv_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/grv-history")
async def grv_history():
    """返回过去7天 GRV 历史（从 gdelt_history.jsonl 读取）+ 当前值。"""
    current = {}
    grv_path = os.path.join(DATA_DIR, "grv_latest.json")
    if os.path.exists(grv_path):
        with open(grv_path, encoding="utf-8") as f:
            current = json.load(f)

    history = []
    hist_path = os.path.join(DATA_DIR, "gdelt_history.jsonl")
    if os.path.exists(hist_path):
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            with open(hist_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("date", "") >= cutoff:
                            scores = entry.get("scores", {})
                            history.append({
                                "date":               entry.get("date", ""),
                                "taiwan_strait":      scores.get("military", {}).get("TWN"),
                                "us_china_strategic": scores.get("military", {}).get("CHN"),
                                "russia_europe":      scores.get("military", {}).get("RUS"),
                                "middle_east_energy": scores.get("military", {}).get("IRN"),
                            })
                    except Exception:
                        pass
        except Exception:
            pass

    # 补入当前 GRV 值（更准确的合成值）
    if current:
        history.append({
            "date":               (current.get("updated", "") or "")[:10],
            "taiwan_strait":      current.get("taiwan_strait"),
            "us_china_strategic": current.get("us_china_strategic"),
            "russia_europe":      current.get("russia_europe"),
            "middle_east_energy": current.get("middle_east_energy"),
        })

    return {"history": history, "current": current}


@app.get("/narrative")
async def narrative():
    """立即生成今日摘要（不推送）。"""
    try:
        from daily_narrative import generate
        text = generate()
        return {"narrative": text, "date": datetime.now().strftime("%Y-%m-%d")}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── 启动 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("WEB_PORT", "8899"))
    print(f"[web_server] 启动在 http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
