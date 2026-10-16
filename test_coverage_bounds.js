// 热力图定位的测试。
//
// 为什么单独测：「图贴歪了」不会报错、不会崩，图还是画出来了 ——
// 只是位置不对。这类 bug 只能靠对比数字抓。
//
// 两个已踩过的坑：
//   ① 网格原点语义：是**西南角**，不是中心（按中心算整体偏半个网格）
//   ② 摘要必须取**服务端当前那份**，不能用打开面板时的快照
//      （实测差 285 m：旧网格 1730 格 vs 新 3621 格）
//
// 以及换算常数必须和 Python 侧 coverage.M_PER_DEG_* 一致。

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

function makeEl(tag) {
  const classes = new Set();
  const el = {
    tagName: (tag || 'div').toUpperCase(),
    children: [], style: {}, dataset: {}, options: [],
    innerHTML: '', textContent: '', value: '', id: '', className: '',
    title: '', type: '', src: '', disabled: false, hidden: false,
    _listeners: {}, _classes: classes, _attrs: {},
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c), toggle() {} },
    addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn) },
    removeEventListener() {},
    appendChild(c) { this.children.push(c); c.parentElement = this; return c },
    remove() {}, setAttribute(k, v) { this._attrs[k] = String(v) },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null },
    removeAttribute(k) { delete this._attrs[k] },
    querySelector() { return null }, querySelectorAll() { return [] },
    focus() {}, blur() {}, click() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 900, height: 600 }),
  };
  return el;
}

function makeL() {
  const handlers = {};
  let lastBounds = null;
  const chain = (extra = {}) => new Proxy(extra, {
    get(t, k) {
      if (k in t) return t[k];
      if (k === 'getBounds') return () => bounds;
      if (k === 'getSize') return () => ({ x: 900, y: 600 });
      if (k === 'getZoom' || k === 'getMaxZoom' || k === 'getMinZoom') return () => 15;
      if (k === 'isValid') return () => true;
      if (k === 'getContainer') return () => container;
      if (typeof k === 'string' && /^_/.test(k)) return undefined;
      return (...a) => chain(extra);
    },
  });
  const bounds = chain({
    isValid: () => true, contains: () => true,
    getSouthWest: () => ({ lat: 0, lng: 0 }),
    getNorthEast: () => ({ lat: 1, lng: 1 }),
    pad: () => bounds, extend: () => bounds,
  });
  const container = makeEl('div');
  const map = chain({ on(ev, fn) { (handlers[ev] ||= []).push(fn); return map } });
  const L = {
    map: () => map, tileLayer: () => chain(), layerGroup: () => chain(),
    featureGroup: () => chain(), geoJSON: () => chain(), marker: () => chain(),
    polyline: () => chain(), polygon: () => chain(), circle: () => chain(),
    imageOverlay: () => chain(), divIcon: () => ({}), icon: () => ({}),
    latLng: (a, b) => ({ lat: a, lng: b }),
    latLngBounds: (sw, ne) => {
      const norm = (p) => Array.isArray(p) ? { lat: p[0], lng: p[1] } : p;
      lastBounds = {
        _sw: norm(sw), _ne: norm(ne),
        getSouthWest: () => norm(sw), getNorthEast: () => norm(ne),
        isValid: () => true, contains: () => true,
        pad() { return bounds }, extend() { return bounds },
      };
      return lastBounds;
    },
    control: () => chain(), DomUtil: { create: () => makeEl('div') }, Browser: {},
    Point: (x, y) => ({ x, y }), setOptions() {}, extend() {},
    __lastBounds: () => lastBounds,
  };
  return { L, handlers, container };
}

// 服务端清单响应（可切换"新旧"）
function listResponse(grid, origin, areaHa, npz, srt) {
  return {
    ok: true, project: 'P1', has_numpy: true,
    items: [{
      srt, srt_name: srt.split('\\').pop(), video_name: 'V', folder: 'X',
      built: true, stale: false, old_format: false, npz, size_kb: 1,
      summary: {
        covered: true, cell_m: 1.0, grid, origin, half_m: 100,
        half_x_m: 100, half_y_m: 100, area_ha: areaHa,
        count: { p50: 1, p95: 2, max: 3 },
        gsd_best_m_per_px: { p50: 0.1 },
      },
    }],
  };
}

function run({ listReplies }) {
  const els = new Map();
  const document = {
    body: makeEl('body'), head: makeEl('head'),
    getElementById(id) {
      if (!els.has(id)) {
        const e = makeEl(id === 'followMode' || id === 'coveragePick' ? 'select' : 'div');
        e.id = id;
        if (id === 'followMode') e.value = 'fit';
        els.set(id, e);
      }
      return els.get(id);
    },
    createElement: (t) => makeEl(t),
    querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
    _els: els,
  };
  const { L, handlers } = makeL();
  globalThis.L = L;

  let call = 0;
  const fetchLog = [];
  const sb = {
    document, els, L,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { innerWidth: 1600, innerHeight: 900, location: { search: '' }, addEventListener() {} },
    location: { search: '' },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    fetch: (url) => {
      fetchLog.push(String(url));
      if (/coverage\/list/.test(String(url))) {
        const r = listReplies[Math.min(call, listReplies.length - 1)];
        call++;
        return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(r)) });
      }
      // 其它接口（heatmap / export / frames）给个够用的空壳
      return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve('{"ok":true,"hits":[]}') });
    },
    alert() {}, console, URLSearchParams, navigator: { userAgent: 'node' },
  };
  const names = Object.keys(sb);
  const code = 'const {' + names.join(',') + '} = __env;\n' + body;
  const ret = '\n;return {coverageBoundsFromSummary, COV_M_PER_DEG_LAT, COV_M_PER_DEG_LNG,' +
    ' coverageToggle, coverageLoadList, coverageShow, coverageCurrentItem, coverageItems,' +
    ' projectSelect, frameGalleryDebug};';
  let threw = null, api = null;
  try {
    api = new Function('__env', code + ret)(sb);
  } catch (e) { threw = e }
  delete globalThis.L;
  return { threw, api, sandbox: sb, handlers, L };
}

const tick = () => new Promise((res) => setImmediate(res));

async function main() {
  console.log('=== 1) 页面脚本能跑完 ===');
  // grid 顺序是 [行数(ny), 列数(nx)]
  // OLD：旧版方形网格 1730×1730，203 公顷
  // NEW：按真实航线重建后 3122 行 × 3621 列，590 公顷
  const OLD = listResponse([1730, 1730], [23.0409, 114.0864], 203.478, 'old.npz', 'X\\V.srt');
  const NEW = listResponse([3122, 3621], [23.040891, 114.086400], 590.517, 'new.npz', 'X\\V.srt');
  const r = run({ listReplies: [NEW] });
  chk(!r.threw, '顶层脚本不抛异常',
    r.threw ? r.threw.constructor.name + ': ' + r.threw.message : '');
  if (!r.api) { console.log('\n结果: 有失败项'); return 1 }

  console.log('\n=== 2) 换算常数与 Python 侧一致 ===');
  chk(r.api.COV_M_PER_DEG_LAT === 110540, 'M_PER_DEG_LAT = 110540',
    String(r.api.COV_M_PER_DEG_LAT));
  chk(r.api.COV_M_PER_DEG_LNG === 111320, 'M_PER_DEG_LNG = 111320',
    String(r.api.COV_M_PER_DEG_LNG));

  console.log('\n=== 3) 范围 = 西南角 + 尺寸（原点不是中心）===');
  {
    // 注意 grid 的顺序是 [行数(ny), 列数(nx)] —— 南北 = ny、东西 = nx
    const b = r.api.coverageBoundsFromSummary({
      cell_m: 1.0, grid: [3122, 3621], origin: [23.040891, 114.086400],
    });
    const sw = b.getSouthWest(), ne = b.getNorthEast();
    const mLat = 110540, mLng = 111320 * Math.cos(23.040891 * Math.PI / 180);
    chk(Math.abs(sw.lat - 23.040891) < 1e-9, '南界 = origin 纬度', sw.lat.toFixed(7));
    chk(Math.abs(sw.lng - 114.086400) < 1e-9, '西界 = origin 经度', sw.lng.toFixed(7));
    const spanN = (ne.lat - sw.lat) * mLat, spanE = (ne.lng - sw.lng) * mLng;
    chk(Math.abs(spanN - 3122) < 1, '南北跨度 = 行数 3122 m', spanN.toFixed(1));
    chk(Math.abs(spanE - 3621) < 1, '东西跨度 = 列数 3621 m', spanE.toFixed(1));
    chk(Math.abs(spanE - spanN) > 400, '两轴确实不同（矩形网格不是方形）',
      `${spanN.toFixed(0)} x ${spanE.toFixed(0)}`);
  }

  console.log('\n=== 4) 显示图层前必须重取摘要（不能用打开面板时的快照）===');
  {
    // 第一次 list 给旧网格 —— 模拟"面板打开时网格还是旧的"
    const rr = run({ listReplies: [OLD, NEW] });
    rr.api.projectSelect.value = 'P1';
    await rr.api.coverageLoadList();
    const it = rr.api.coverageCurrentItem();
    chk(it && it.summary.grid[0] === 1730, '面板打开时拿到的是旧摘要',
      it ? String(it.summary.grid) : '');

    // 现在点 Show：应当再问一次服务端，并把摘要换成新的
    await rr.api.coverageShow();
    const it2 = rr.api.coverageCurrentItem();
    chk(it2 && it2.summary.grid[0] === 3122,
      'Show 之后用的是**服务端当前**的摘要',
      it2 ? String(it2.summary.grid) : '');
    const lb = rr.L.__lastBounds();
    chk(!!lb, 'imageOverlay 拿到了范围');
    if (lb) {
      const sw = lb.getSouthWest(), ne = lb.getNorthEast();
      const mLng = 111320 * Math.cos(23.040891 * Math.PI / 180);
      const mLat = 110540;
      const spanE = (ne.lng - sw.lng) * mLng;
      const spanN = (ne.lat - sw.lat) * mLat;
      chk(Math.abs(spanE - 3621) < 5,
        '叠加范围用的是**新**网格宽度（旧的只有 1730）', spanE.toFixed(0) + ' m');
      chk(Math.abs(spanN - 3122) < 5, '南北也换成新的 3122 m', spanN.toFixed(0) + ' m');
    }
    const lists = rr.sandbox ? null : null;
  }

  console.log('\n=== 5) 取不到服务端摘要时不能把图弄没 ===');
  {
    const rr = run({ listReplies: [OLD] });
    rr.api.projectSelect.value = 'P1';
    await rr.api.coverageLoadList();
    // 把 fetch 打坏
    const orig = rr.sandbox.fetch;
    rr.sandbox.fetch = () => Promise.reject(new Error('网络挂了'));
    let threw = null;
    try { await rr.api.coverageShow() } catch (e) { threw = e }
    chk(!threw, '取不到摘要时不抛异常', threw ? threw.message : '');
    const it = rr.api.coverageCurrentItem();
    chk(it && it.summary && it.summary.grid[0] === 1730,
      '退回用旧快照（至少还能画出图来）', it && it.summary ? String(it.summary.grid) : '');
    rr.sandbox.fetch = orig;
  }

  console.log('\n结果:', ok ? '全部通过' : '有失败项');
  return ok ? 0 : 1;
}

main().then((c) => process.exit(c)).catch((e) => {
  console.error('测试本身出错:', e);
  process.exit(1);
});
