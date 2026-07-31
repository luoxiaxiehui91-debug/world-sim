// 将 dist-standalone 转为「真·单文件」预览：双击 index.html 即可打开，无需服务器、无外部文件。
//  - JS/CSS 已由 vite-plugin-singlefile 内联
//  - 本脚本：
//    1) 把 3 张纹理(jpg/png) 内联为 data URI，替换 bundle 里的字面量路径（Image 加载，不经过 fetch）
//    2) 注入 fetch shim，把所有运行时 fetch 的文件内嵌为 JS 字符串，file:// 下 fetch 不再被拦截：
//       data/*（GRV/新闻/FRED/trigger）+ assets/countries-110m.json（国界拓扑）
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const SRC = path.join(ROOT, 'dist-standalone');
const OUT = path.join(ROOT, 'kaiyang-standalone');
fs.mkdirSync(OUT, { recursive: true });

// 1) 内联纹理资源（base64 data URI，由 Image 元素加载，不经过 fetch）
const assetMap = {
  './assets/earth-blue-marble.jpg': ['assets/earth-blue-marble.jpg', 'image/jpeg'],
  'assets/earth-blue-marble.jpg': ['assets/earth-blue-marble.jpg', 'image/jpeg'],
  './assets/earth-topology.png': ['assets/earth-topology.png', 'image/png'],
  'assets/earth-topology.png': ['assets/earth-topology.png', 'image/png'],
  './assets/night-sky.png': ['assets/night-sky.png', 'image/png'],
  'assets/night-sky.png': ['assets/night-sky.png', 'image/png'],
};
const dataUriReplacements = {};
for (const [lit, [rel, mime]] of Object.entries(assetMap)) {
  const full = path.join(SRC, rel);
  if (!fs.existsSync(full)) { console.warn('MISSING asset', rel); continue; }
  const b64 = fs.readFileSync(full).toString('base64');
  dataUriReplacements[lit] = `data:${mime};base64,${b64}`;
}

// 2) 收集 data/ 下文件内嵌为 fetch shim 字符串
function walk(dir, base, acc) {
  if (!fs.existsSync(dir)) return acc;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    const rel = path.posix.join(base, e.name);
    if (e.isDirectory()) walk(full, rel, acc);
    else acc[rel] = full;
  }
  return acc;
}
const dataFiles = {};
walk(path.join(SRC, 'data'), 'data', dataFiles);
const embed = {};
for (const [rel, full] of Object.entries(dataFiles)) {
  embed[rel] = fs.readFileSync(full, 'utf8');
}
// 国界拓扑（FlatMapPanel 用 fetch 加载，不在 data URI 覆盖范围）
const countriesJson = path.join(SRC, 'assets', 'countries-110m.json');
if (fs.existsSync(countriesJson)) {
  embed['assets/countries-110m.json'] = fs.readFileSync(countriesJson, 'utf8');
}

const shim = `<script>
(function(){
  const EMBED = ${JSON.stringify(embed)};
  function lookup(u){
    let p = (typeof u === 'string') ? u : (u && u.url) || '';
    try { p = new URL(p, self.location.href).pathname; } catch(e){}
    p = decodeURIComponent(p).replace(/^\\/+/, '');
    for (const k of Object.keys(EMBED)) {
      if (p === k || p.endsWith('/' + k)) return EMBED[k];
    }
    return null;
  }
  const orig = self.fetch ? self.fetch.bind(self) : null;
  self.fetch = function(u, o){
    const v = lookup(u);
    if (v !== null) return Promise.resolve(new Response(v, {status:200, headers:{'Content-Type':'text/plain'}}));
    return orig ? orig(u, o) : Promise.reject(new Error('no fetch'));
  };
})();
</script>`;

// 3) 组装单文件 HTML
let html = fs.readFileSync(path.join(SRC, 'index.html'), 'utf8');
for (const [lit, uri] of Object.entries(dataUriReplacements)) {
  html = html.split(lit).join(uri);
}
html = html.replace(/<head[^>]*>/, (m) => m + '\n' + shim);

fs.writeFileSync(path.join(OUT, 'index.html'), html);
console.log('standalone SINGLE-FILE ->', path.join(OUT, 'index.html'));
console.log('  size:', (fs.statSync(path.join(OUT, 'index.html')).size / 1024 / 1024).toFixed(2), 'MB');
console.log('  embedded data files:', Object.keys(embed).length);
console.log('  inlined assets (data URI):', Object.keys(dataUriReplacements).length / 2);
