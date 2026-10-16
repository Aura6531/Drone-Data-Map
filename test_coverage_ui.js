// 覆盖热力图的定位数学：coverageBoundsFromSummary() 算出来的经纬度范围
// 必须和后端网格的真实范围一致 —— 算错的话热力图会贴到错误位置，
// 而这是"看不见的死角"（图还是画出来了，只是位置错了）。
//
// 做法：复用 test_boot.js 的沙箱方式跑一遍页面脚本，把顶层函数从这个
// 上下文里取出来，喂真实摘要，和独立算出的期望值比。

const fs = require('fs');
const path = require('path');

const HTML = path.join(__dirname, 'Code', 'project_geojson_preview.html');
const html = fs.readFileSync(HTML, 'utf8');
const m = html.match(/<script>\s*([\s\S]*?)<\/script>/);
if (!m) throw new Error('找不到主 <script> 块');
const body = m[1];

let ok = true;
const chk = (c, label, extra = '') => {
  ok = ok && !!c;
  console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
};

// ---------- 极简 DOM / Leaflet 桩 ----------
function makeEl() {
  return {
    style: {}, dataset: {}, options: [], children: [], classList: {
      add() {}, remove() {}, contains() { return false }, toggle() {},
    },
    _listeners: {},
    addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn) },
    removeEventListener() {}, appendChild(c) { this.children.push(c); return c },
    setAttribute() {}, getAttribute() { return null }, removeAttribute() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
    querySelector() { return null }, querySelectorAll() { return [] },
    insertBefore(c) { return c }, remove() {}, focus() {}, blur() {}, click() {},
    getContext: () => null, toDataURL: () => '',
    innerHTML: '', textContent: '', value: '', id: '', className: '',
    parentNode: null, firstChild: null, hidden: false, disabled: false,
  };
}

function makeL() {
  const mk = () => {
    const o = {
      addTo() { return o }, remove() { return o }, clearLayers() {},
      setView() { return o }, fitBounds() { return o }, on() { return o },
      off() { return o }, eachLayer() {}, getBounds() { return boundsStub },
      setOpacity() { return o }, bindPopup() { return o }, setStyle() { return o },
      bringToFront() { return o }, setZIndex() { return o }, addLayer() { return o },
      removeLayer() { return o }, getLayers() { return [] }, pane: '',
      _latlngs: [], options: {},
    };
    return o;
  };
  const boundsStub = {
    isValid: () => true, getSouthWest: () => ({ lat: 0, lng: 0 }),
    getNorthEast: () => ({ lat: 1, lng: 1 }), pad() { return boundsStub },
    extend() { return boundsStub, boundsStub },
  };
  const L = {
    map: mk, tileLayer: mk, layerGroup: mk, featureGroup: mk, geoJSON: mk,
    marker: mk, polyline: mk, polygon: mk, circle: mk, circleMarker: mk,
    imageOverlay: mk, divIcon: () => ({}), icon: () => ({}), latLng: (a, b) => ({ lat: a, lng: b }),
    latLngBounds: (sw, ne) => {
      // 真实 Leaflet 接受 [lat,lng] 数组并归一成 LatLng 对象，
      // 桩也必须照做 —— 页面代码传的正是数组，不归一会得到 undefined。
      const norm = (p) => Array.isArray(p) ? { lat: p[0], lng: p[1] } : p;
      const b = {
        _sw: norm(sw), _ne: norm(ne),
        getSouthWest: () => norm(sw), getNorthEast: () => norm(ne),
        isValid: () => true, pad() { return b }, extend() { return b },
      };
      L.__lastBounds = b;
      return b;
    },
    control: mk, DomUtil: { create: () => makeEl() },
    Browser: {}, Point: (x, y) => ({ x, y }),
    setOptions() {}, extend() {},
  };
  return L;
}

function run() {
  const els = new Map();
  const document = {
    body: makeEl(), head: makeEl(),
    getElementById(id) { if (!els.has(id)) { const e = makeEl(); e.id = id; els.set(id, e) } return els.get(id) },
    createElement: () => makeEl(),
    querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
  };
  const sb = {
    document, els,
    window: { innerWidth: 1600, innerHeight: 900, location: { search: '' }, addEventListener() {} },
    location: { search: '' },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    fetch: () => Promise.reject(new Error('桩：不发请求')),
    alert() {}, console, URLSearchParams,
    navigator: { userAgent: 'node' },
  };
  globalThis.L = makeL();
  sb.L = globalThis.L;
  const names = Object.keys(sb);
  const code = 'const {' + names.join(',') + '} = __env;\n' + body;
  let threw = null;
  try {
    const fn = new Function('__env', code +
      '\n;return {coverageBoundsFromSummary, coverageMetric, COVERAGE_BANDS, COVERAGE_NONE_COLOR};');
    return { threw: null, api: fn(sb), sandbox: sb };
  } catch (e) {
    threw = e;
    return { threw: e, api: null, sandbox: sb };
  } finally {
    delete globalThis.L;
  }
}

console.log('=== 取出页面的 coverageBoundsFromSummary ===');
const r = run();
chk(!r.threw, '页面脚本执行不抛异常',
  r.threw ? r.threw.constructor.name + ': ' + r.threw.message : '');
if (!r.api || typeof r.api.coverageBoundsFromSummary !== 'function') {
  chk(false, 'coverageBoundsFromSummary 是函数（顶层声明，boot 之前就该在）');
  console.log('\n结果: 有失败项');
  process.exit(1);
}
chk(true, 'coverageBoundsFromSummary 是函数');

const f = r.api.coverageBoundsFromSummary;

console.log('\n=== 与真实网格摘要对照（司空 2 样本，1 m 网格）===');
// 后端真实产出的摘要形态。注意 **origin 是网格的西南角**（不是中心）——
// 曾经把原点当中心、半宽取"12×最高高度"，结果航线超出网格被切掉。
const summary = {
  cell_m: 1.0,
  grid: [2641, 2641],
  origin: [22.963657, 113.770619],
  half_m: 1377.2,
  half_x_m: 1377.2,
  half_y_m: 1377.2,
};
const b = f(summary);
chk(b && b.getSouthWest && b.getNorthEast, '返回一个 latLngBounds');

const [lat0, lng0] = summary.origin;
const [ny, nx] = summary.grid;
const cell = summary.cell_m;
const mLat = 110540, mLng = 111320 * Math.cos(lat0 * Math.PI / 180);
// 原点就是西南角，所以南界/西界应当**正好等于** origin
const expS = lat0;
const expW = lng0;
const expN = lat0 + (ny * cell) / mLat;
const expE = lng0 + (nx * cell) / mLng;

const sw = b.getSouthWest(), ne = b.getNorthEast();
const tol = 1e-6;
chk(Math.abs(sw.lat - expS) < tol, '南界 = origin 纬度（原点是西南角）',
  `${sw.lat.toFixed(7)} vs ${expS.toFixed(7)}`);
chk(Math.abs(sw.lng - expW) < tol, '西界 = origin 经度（原点是西南角）',
  `${sw.lng.toFixed(7)} vs ${expW.toFixed(7)}`);
chk(Math.abs(ne.lat - expN) < tol, '北界 = origin + 行数×格宽',
  `${ne.lat.toFixed(7)} vs ${expN.toFixed(7)}`);
chk(Math.abs(ne.lng - expE) < tol, '东界 = origin + 列数×格宽',
  `${ne.lng.toFixed(7)} vs ${expE.toFixed(7)}`);

console.log('\n=== 南北方向不能搞反（搞反了图会上下颠倒）===');
chk(sw.lat < ne.lat, '南界 < 北界', `${sw.lat.toFixed(5)} < ${ne.lat.toFixed(5)}`);
chk(sw.lng < ne.lng, '西界 < 东界');

console.log('\n=== 网格边长应与 half_m × 2 吻合 ===');
const spanM = (ne.lat - sw.lat) * mLat;
chk(Math.abs(spanM - ny * cell) / (ny * cell) < 1e-6,
  '南北跨度 = 行数 × 格宽', `${spanM.toFixed(1)} m vs ${(ny * cell).toFixed(1)} m`);
const spanE = (ne.lng - sw.lng) * mLng;
chk(Math.abs(spanE - nx * cell) / (nx * cell) < 1e-6,
  '东西跨度 = 列数 × 格宽', `${spanE.toFixed(1)} m vs ${(nx * cell).toFixed(1)} m`);

console.log('\n=== 缺字段时应返回 null 而不是编一个范围出来 ===');
chk(f(null) === null, '传 null -> null');
chk(f({}) === null, '传空对象 -> null');
chk(f({ origin: [1, 2] }) === null, '缺 grid -> null');
chk(f({ origin: null, grid: [1, 1] }) === null, 'origin 为空 -> null');

console.log('\n=== 矩形网格：两个轴必须分别算（用错一个轴会让热力图贴歪）===');
{
  // 造一个明显不是正方形的网格：东西 2000 m、南北 4000 m
  const rect = { cell_m: 1.0, grid: [4000, 2000], origin: [23.0, 113.0] };
  const rb = f(rect);
  const swr = rb.getSouthWest(), ner = rb.getNorthEast();
  const mLat = 110540, mLng = 111320 * Math.cos(23.0 * Math.PI / 180);
  const spanN = (ner.lat - swr.lat) * mLat;
  const spanE = (ner.lng - swr.lng) * mLng;
  chk(Math.abs(spanN - 4000) < 1, '南北跨度 = 4000 m', spanN.toFixed(1));
  chk(Math.abs(spanE - 2000) < 1, '东西跨度 = 2000 m', spanE.toFixed(1));
  chk(Math.abs(spanN - spanE) > 1000, '两个轴确实不同（不是被当成正方形）');
}

console.log('\n=== 前端色带必须与后端 coverage_api._BANDS 对齐 ===');
// 色值对不上会出现「图例说这个颜色代表很多、图上却是别的意思」，
// 而且看起来还挺正常 —— 所以用断言钉住。
{
  const py = process.env.PYTHON_COV || 'python';
  const { execFileSync } = require('child_process');
  const probe =
    'import sys;sys.path.insert(0,r"' + path.join(__dirname, 'Code').replace(/\\/g, '\\\\') + '");'
    + 'import coverage_api as a;'
    + 'print(",".join("#%02x%02x%02x" % c for _,c in a._BANDS))';
  let back = null, err = null;
  try {
    back = execFileSync(py, ['-B', '-c', probe], { encoding: 'utf8' }).trim().split(',');
  } catch (e) { err = e; }

  if (err || !back) {
    console.log('  [SKIP] 取不到后端色带（这个解释器没有 numpy 或没装 python）');
  } else {
    const front = r.api.COVERAGE_BANDS.map((b) => b.c);
    const none = r.api.COVERAGE_NONE_COLOR;
    chk(back.length === front.length + 1,
      '档数 = 后端档数 − 1（后端的第 0 档是"无覆盖"底色）',
      `后端 ${back.length} 档 / 前端 ${front.length} 档`);
    chk(none && none.toLowerCase() === (back[0] || '').toLowerCase(),
      '前端"无覆盖"色 = 后端 _BANDS[0]', `${none} vs ${back[0]}`);
    const same = front.every((c, i) => c.toLowerCase() === (back[i + 1] || '').toLowerCase());
    chk(same, '五档渐深色逐一对应',
      same ? front.join(' ') : `前端 ${front.join(' ')} / 后端 ${back.slice(1).join(' ')}`);
    chk(/^#[0-9a-f]{6}$/i.test(none || ''), '无覆盖色是合法十六进制');
  }
}

console.log('\n=== 三个图例框合成一个（加载哪个就显示哪个）===');
{
  // 用户 2026-10-13：「这3个图例框的内容，全部做到一个框里面，集成起来，
  // 加载哪个就显示哪个」。
  // 原来三块：航迹色卡（左下）/ 覆盖色带（右下）/ 选中点结论（左下），
  // 各自一套容器、各自维护。现在只有一个 .map-legend。
  chk(/id="mapLegend"/.test(html), '有统一的图例容器 mapLegend');
  chk(!/id="coverageLegend"/.test(html), '旧的 coverageLegend 容器已移除');
  chk(!/id="coverageHit"/.test(html), '旧的 coverageHit 容器已移除');
  // 旧的 .legend 元素也没了（那个用 innerHTML+= 累加）
  chk(!/id="legend"/.test(html), '旧的航迹图例元素已移除');
  chk(!/legend\.innerHTML/.test(html.replace(/\/\/[^\n]*/g, '')),
    '代码里不再有 legend.innerHTML（累加式写法，会导致重复条目）');

  const m = html.match(/\.map-legend\{([^}]*)\}/);
  chk(!!m, '有 .map-legend 规则');
  if (m) {
    const css = m[1].replace(/\s+/g, ' ');
    chk(/position:\s*absolute/.test(css), '绝对定位（浮在地图上）');
    chk(/backdrop-filter:\s*blur\(/.test(css), '毛玻璃');
    chk(/-webkit-backdrop-filter/.test(css), '带 -webkit- 前缀');
    chk(/saturate\(/.test(css), '带 saturate');
    chk(/border-radius:\s*9px/.test(css), '圆角 9px');
    chk(/overflow:\s*auto/.test(css), '内容多了能滚动');
  }
  chk(/\.map-legend:empty\{display:none\}/.test(html),
    '空的时候不占位（没加载任何层就整个隐藏）');

  // 统一渲染入口必须是**幂等**的（整体重建，不是累加）
  chk(/function rebuildLegend\(\)/.test(html), '有唯一渲染入口 rebuildLegend');
  {
    const i = html.indexOf('function rebuildLegend()');
    const body = html.slice(i, html.indexOf('\n}', i));
    chk(/box\.innerHTML=html/.test(body), '是整体赋值（幂等）而不是 += 累加');
    chk(/loadedTracks\.length/.test(body), '按"有没有加载航迹"决定显示那一段');
    chk(/coverageLegendHtml\(\)/.test(body), '按"覆盖图层开没开"决定显示那一段');
    chk(/coverageHitHtml\(\)/.test(body), '按"选没选点"决定显示那一段');
  }
  // 三段各自都要有独立的 launcher 函数（返回字符串）
  chk(/function coverageLegendHtml\(\)/.test(html), '覆盖那一段抽成了函数');
  chk(/function coverageHitHtml\(\)/.test(html), '结论那一段也抽成了函数');
  // 结论段没选点时返回空串（而不是自己删容器）
  chk(/if\(!h\)\{[\s\S]{0,120}?return '';/.test(html), '没选点时结论段返回空串');
  // 段与段之间有分隔
  chk(/\.map-legend \.lg-sec \+ \.lg-sec\{/.test(html), '段与段之间有分隔线');
  // 换了项目 / 清空选点都要重建图例
  chk(/rebuildLegend\(\);stats\.innerHTML=''/.test(html), '换项目时重建图例');
  chk(/updateTargetMarker\(\);\s*\n\s*\/\/ 图例框里/.test(html) ||
      /rebuildLegend\(\);\s*\n\s*refreshMapSizeSoon\(\);/.test(html),
    '清空选点时重建图例');
}

console.log('\n=== 结论段：叠在地图上、小字、每项独占一行、标签加粗 ===');
{
  // 用户三条要求：① 底版透明小字叠加在地图上；② 分行正常、关键词加粗；
  // ③ 字体颜色统一。这些现在都在 .map-legend 的 .kv 规则里。
  chk(/\.map-legend \.kv b\{[^}]*text-shadow/.test(html),
    '标签带文字阴影（透明底上的可读性保障）');
  chk(/\.map-legend \.kv span\{[^}]*text-shadow/.test(html), '值也带文字阴影');

  // 它在 DOM 里必须落在 map-stack 之内（那层是 position:relative，
  // 落在外面就会相对整页定位而不是相对地图）
  const iStack = html.indexOf('class="map-stack"');
  const iLeg = html.indexOf('id="mapLegend"');
  chk(iStack > 0 && iLeg > iStack, 'mapLegend 在 map-stack 之后',
    `stack@${iStack} legend@${iLeg}`);
  chk(/\.map-stack\{[^}]*position:\s*relative/.test(html),
    'map-stack 是 position:relative（叠加层的定位基准）');

  // 不再落在地图下面那一段里
  const iBelow = html.indexOf('class="below-map"');
  const iBelowEnd = html.indexOf('id="colRight"');
  const mid = html.slice(iBelow, iBelowEnd);
  chk(mid.indexOf('mapLegend') < 0, '地图下面那一段里没有它');
}

console.log('\n=== 每项独占一行、标签加粗、值左对齐 ===');
{
  // 用户 2026-10-13：「分行要做正常点，关键词加粗，Observed 及其信息排在单独一行，
  // 后续内容也是一样。关键词字体加粗。」
  // 之前是 flex 流式排列 —— "Observed 830 frames / 83" 会断在行尾、"passes" 掉下一行。
  // 现在改成**一个栅格**：标签列 max-content + nowrap，每项严格一行。
  const m = html.match(/\.map-legend \.kv\{([^}]*)\}/);
  chk(!!m, '有 .kv 栅格规则');
  if (m) {
    const css = m[1].replace(/\s+/g, ' ');
    chk(/display:\s*grid/.test(css), '是栅格（不是 flex 流式换行）');
    chk(/grid-template-columns:\s*max-content/.test(css),
      '标签列 max-content（取最宽标签，值列才对得齐）', css.slice(0, 70));
  }
  chk(/\.map-legend \.kv b\{[^}]*font-weight:\s*700/.test(html),
    '标签字体加粗到 700');
  chk(/\.map-legend \.kv b\{[^}]*white-space:\s*nowrap/.test(html),
    '标签不换行（"Observed" 不会被拆开）');
  // 所有行必须在**同一个** .kv 里（分成两个栅格值列会错开 —— 实测 493 vs 485）。
  // 锚点要选得够 specific：两个分支开头都是 `<div class="lg-sec"><div class="kv">`，
  // 所以用"带 Coverage + badge 那个标题行"来定界（踩过一次，切到了短分支）。
  const iKv = html.indexOf('+`<div class="hd">Coverage<span class="badge');
  const iEnd = html.indexOf('`</div></div>`;', iKv);
  // 往前退到这一段的开头
  const iStart = html.lastIndexOf('return `<div class="lg-sec"><div class="kv">`', iKv);
  const block = iStart < 0 ? '' : html.slice(iStart, iEnd + 20);
  chk((block.match(/class="kv"/g) || []).length === 1,
    '所有 KV 行在同一个栅格里（分两个会让值列错开）',
    `切到 ${block.length} 字符, kv 数 ${(block.match(/class="kv"/g) || []).length}`);
  for (const label of ['Confidence', 'Observed', 'Best', 'Sharpest', 'Boundary']) {
    chk(new RegExp(`<b[^>]*>${label}</b>`).test(block), `有独立一行：${label}`);
  }
  chk(/<div class="hd">Coverage/.test(block), '标题行也在这个栅格里（占满一行）');
}

console.log('\n=== 准确度说明改成 i 图标（只留图标，悬停/点击才显示）===');
{
  chk(/id="coverageAccuracy"/.test(html), '有 i 图标元素');
  chk(/class="cov-info"/.test(html), '用的是 .cov-info 样式');
  const m = html.match(/\.cov-info\{([^}]*)\}/);
  chk(!!m, '有 .cov-info 规则');
  if (m) {
    const css = m[1].replace(/\s+/g, ' ');
    chk(/border-radius:\s*50%/.test(css), '是圆形（"带 i 的圆圈"）');
    chk(/width:\s*16px/.test(css) && /height:\s*16px/.test(css),
      '小小的（16px）');
    chk(/cursor:\s*help/.test(css), '指针是 help（提示这是说明）');
  }
  // 全文要写到 title 里，并且**渲染时**写（内容是随点变化的）
  chk(/acc\.title\s*=\s*q\.accuracy_note/.test(html),
    '说明全文写到图标的 title 里（渲染时按该点更新）');
  // 那段长说明不能还留在页面上当正文
  chk(!/class="note">\$\{esc\(q\.accuracy_note/.test(html),
    '长说明不再作为正文渲染在页面块里');
  chk(!/\.coverage-hit \.note\{display:none\}/.test(html),
    '旧的 .coverage-hit 样式块已整个移除');
}

console.log('\n=== 地图上的浮层都用同一套毛玻璃（一块透一块不透会像两套界面）===');
{
  // 用户 2026-10-13：先要求"底板的透明度大幅增强，可以用轻微的毛玻璃特效"，
  // 看过之后说「可以，挺好的，右边这个框也照样做」，
  // 最后又要求三块合成一个。
  // 现在地图上就两块浮层：统一的图例框、搜索+操作卡 —— 它们必须同一套观感。
  const grab = (sel) => {
    const m = html.match(new RegExp('\\.' + sel + '\\{([^}]*)\\}'));
    return m ? m[1].replace(/\s+/g, ' ') : '';
  };
  const legend = grab('map-legend');
  const bar = grab('action-bar');
  chk(!!legend && !!bar, '两块都有规则');
  for (const [name, css] of [['图例框', legend], ['搜索+操作卡', bar]]) {
    chk(/backdrop-filter:\s*blur\(\d/.test(css), `${name} 有毛玻璃 blur`);
    chk(/-webkit-backdrop-filter/.test(css), `${name} 带 -webkit- 前缀`);
    chk(/saturate\(/.test(css), `${name} 带 saturate`);
    chk(/border-radius:\s*9px/.test(css), `${name} 圆角一致（9px）`);
    chk(/border:\s*1px solid rgba\(148,\s*163,\s*184,\s*\.34\)/.test(css),
      `${name} 边框一致（rgba(148,163,184,.34)）`);
  }
  // 两块的不透明度可以略有差别（图例里的色带要看得清），但都得是"大幅透明"
  for (const [name, css] of [['图例框', legend], ['搜索+操作卡', bar]]) {
    // 抓 rgba(...,A) 里的 A：A 可能写成 `.55`（点后没有 0），正则要把那个点吃进去
    const a = Number((css.match(/rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(\.?\d+(?:\.\d+)?)\s*\)/) || [])[1]);
    chk(Number.isFinite(a) && a > 0 && a <= 0.65,
      `${name} 大幅透明（不透明度 <= 0.65）`, String(a));
  }
}

console.log('\n=== 搜索+主要操作悬浮在地图里（地图高度大幅扩张）===');
{
  // 用户 2026-10-13：「把搜索框和我们最大的几个按钮做进地图里面，成为悬浮按钮，
  // 这样地图的面积就能大幅扩张」。
  // 实测：挪进去之前地图只有 311px 高（上方被搜索行 36px + 操作块 176px 吃掉），
  // 挪进去之后 654px。所以这里钉住"它们在 map-stack 之内"。
  const iStack = html.indexOf('class="map-stack"');
  const iStackEnd = html.indexOf('id="tileHint"');
  const inside = html.slice(iStack, iStackEnd > iStack ? iStackEnd : iStack + 3000);
  chk(/id="probePanel"/.test(inside), '搜索+操作卡在 map-stack 之内');
  chk(/id="placeInput"/.test(inside), '搜索框也在地图里');
  chk(/id="searchNearbyBtn"/.test(inside), '「Find flights at this position」在地图里');
  chk(/id="findFramesBtn"/.test(inside), '「Frames of this spot」在地图里');
  // 不能再留在地图上方（那一段是 poiList 到 map-stack 之间）
  {
    const iAbove = html.indexOf('id="poiList"');
    const above = html.slice(iAbove, iStack);
    chk(!/id="placeInput"/.test(above) && !/id="searchNearbyBtn"/.test(above),
      '地图上方已经没有它们了');
  }
  // 必须是绝对定位的悬浮卡（不然放进去也会把地图撑走）
  const m = html.match(/\.action-bar\{([^}]*)\}/);
  chk(!!m, '有 .action-bar 规则');
  if (m) {
    const css = m[1].replace(/\s+/g, ' ');
    chk(/position:\s*absolute/.test(css), '绝对定位（悬浮，不撑地图）');
    chk(/backdrop-filter:\s*blur\(/.test(css),
      '毛玻璃底（和另外两块浮层同一套观感）');
  }
  // 可折叠：选完点之后能收起来看地图
  chk(/id="probeFoldBtn"/.test(inside), '有折叠按钮');
  chk(/function setProbeFold/.test(html), '有 setProbeFold');
  chk(/\.action-bar\.folded \.action-row\{display:none\}/.test(html),
    '折叠时收掉按钮行');
  chk(!/\.action-bar\.folded \.search-bar\{display:none\}/.test(html),
    '折叠后**搜索框仍然可用**（否则等于把搜索藏了）');
  // clearProbe 不能把整条卡藏掉（那样搜索也没了）
  chk(/function clearProbe\(\)\{[\s\S]{0,400}?setProbeFold\(false\)/.test(html),
    'clearProbe 只收按钮、不藏整卡');
  chk(!/probePanel\.style\.display='none'/.test(html),
    '代码里不再有"把整条卡 display:none"的写法');
  // Leaflet 的 zoom 键默认也在左上角，必须让开
  chk(/\.leaflet-top\.leaflet-left\{top:\d+px\}/.test(html),
    'Zoom 键往下让开，不被悬浮卡盖住');
}

console.log('\n=== 覆盖面板也悬浮进地图（左下角，图例之上）===');
{
  // 用户 2026-10-14：「这些也要做进地图里面悬浮按钮」。
  // 原来它在地图上方占 140px（Flight/Build/Show/Opacity/Show/Export 那一块）。
  const iStack = html.indexOf('class="map-stack"');
  const iStackEnd = html.indexOf('id="tileHint"');
  const inside = html.slice(iStack, iStackEnd > iStack ? iStackEnd : iStack + 4000);
  chk(/id="coveragePanel"/.test(inside), '覆盖面板在 map-stack 之内');
  // 地图上方（poiList 到 map-stack 之间）不能再有它
  {
    const iAbove = html.indexOf('id="poiList"');
    chk(html.slice(iAbove, iStack).indexOf('id="coveragePanel"') < 0,
      '地图上方已经没有它了');
  }
  const m = html.match(/\.coverage-panel\.cov-float\{([^}]*)\}/);
  chk(!!m, '有 .cov-float 规则（悬浮版）');
  if (m) {
    const css = m[1].replace(/\s+/g, ' ');
    chk(/position:\s*absolute/.test(css), '绝对定位（悬浮，不撑地图）');
    chk(/backdrop-filter:\s*blur\(/.test(css), '毛玻璃（和另两块浮层同一套）');
    chk(/-webkit-backdrop-filter/.test(css), '带 -webkit- 前缀');
    chk(/left:\s*10px/.test(css) && /right:\s*10px/.test(css),
      '左右各让 10px（铺满地图宽度；控件多，窄了会换行反而更高）');
  }
  // 可折叠：折叠后只剩一条，且要有标签说明这是什么
  chk(/id="coverageFoldBtn"/.test(inside), '有折叠按钮');
  chk(/class="cov-mini"/.test(inside), '折叠时有「Coverage controls」标签');
  chk(/\.coverage-panel\.cov-float\.folded \.coverage-row\{display:none\}/.test(html),
    '折叠时收掉控件行');
  chk(/\.coverage-panel\.cov-float\.folded \.cov-mini\{display:block\}/.test(html),
    '折叠时才显示那个标签');
  chk(/function setCoverageFold/.test(html), '有 setCoverageFold');
  chk(/function initCoverageFloat/.test(html), '有 initCoverageFloat（挂钮 + 观察高度）');
  chk(/new ResizeObserver\(adjustLegendBottom\)/.test(html),
    '用 ResizeObserver 盯着面板高度变化');
  // 图例要让开面板高度，否则两块叠在一起
  chk(/function adjustLegendBottom/.test(html), '有 adjustLegendBottom');
  chk(/cp\.offsetHeight/.test(html),
    '按面板**实际高度**算图例的 bottom（不写死）');
  {
    const iTog = html.indexOf('async function coverageToggle()');
    chk(iTog > 0 && /adjustLegendBottom\(\)/.test(html.slice(iTog, iTog + 700)),
      '开/关面板时也跟着调整图例位置');
  }
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
