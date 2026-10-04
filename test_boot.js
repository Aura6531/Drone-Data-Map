// 真正执行页面顶层脚本，验证它能跑完初始化。
//
// 为什么需要这个测试：check_page.js 的 `new Function(body)` 只做「语法编译」，
// 抓不到运行期错误。而「暂时性死区」正是运行期错误 —— 顶层的
// applyXxxVisibility() 调用了后面的函数，那个函数读到还没初始化的 let，
// 就抛 ReferenceError 并中断整个顶层脚本，页面只剩几个空白框。
// 这个测试把顶层脚本真的跑一遍，两种场景都必须不抛异常。
const fs = require('fs');

const HTML = process.argv[2] || '<仓库根>\\Code\\project_geojson_preview.html';
const html = fs.readFileSync(HTML, 'utf8');
const m = html.match(/<script>\s*([\s\S]*?)<\/script>/);
if (!m) throw new Error('找不到主 <script> 块');
const body = m[1];

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

// ---------- DOM 桩 ----------
function makeElement(id) {
  const classes = new Set();
  const el = {
    id,
    style: {},
    dataset: {},
    options: [],
    innerHTML: '',
    textContent: '',
    value: '',
    hidden: false,
    disabled: false,
    className: '',
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
      toggle: (c, on) => { if (on === undefined) on = !classes.has(c); on ? classes.add(c) : classes.delete(c); },
    },
    _classes: classes,
    addEventListener() {}, removeEventListener() {},
    appendChild() {}, removeChild() {}, insertAdjacentHTML() {},
    querySelector() { return null }, querySelectorAll() { return [] },
    setAttribute() {}, getAttribute() { return null }, removeAttribute() {},
    getBoundingClientRect: () => ({ width: 100, height: 100, left: 0, top: 0, right: 100, bottom: 100 }),
    closest() { return null }, scrollIntoView() {}, focus() {}, click() {},
    load() {}, pause() {}, play() { return Promise.resolve() }, remove() {},
    contains() { return false }, dispatchEvent() {},
    getContext() { return null },
  };
  return el;
}

// L 挂在 globalThis 上而不是解构进函数作用域 ——
// 这样才能模拟「Leaflet 晚到」：先以 L 不存在跑顶层，再把 L 放上去继续跑轮询。
function makeLStub(calls) {
  const mapStub = {
    setView() { return this }, on() { return this }, off() { return this },
    setMaxZoom() {}, getZoom() { return 9 }, setZoom() {}, zoomIn() {}, zoomOut() {},
    removeLayer() {}, addLayer() {}, hasLayer() { return false },
    invalidateSize() {}, fitBounds() {}, panTo() {}, getBoundsZoom() { return 12 },
    getCenter: () => ({ lat: 23, lng: 114, distanceTo: () => 0 }),
    distance: () => 0,
  };
  const layerStub = () => ({
    addTo() { return this }, on() { return this }, off() { return this },
    bringToBack() { return this }, bringToFront() { return this },
    setLatLngs() { return this }, setStyle() {}, bindPopup() { return this },
    getElement() { return null }, getLatLng() { return { lat: 23, lng: 114 } },
    setLatLng() { return this }, remove() {}, setIcon() {},
  });
  return {
    map: () => mapStub,
    tileLayer: layerStub, polyline: layerStub, polygon: layerStub,
    marker: layerStub, featureGroup: layerStub, layerGroup: layerStub,
    geoJSON: layerStub,
    divIcon: () => { calls.divIcon++; return {} },
    icon: () => ({}),
    latLng: (a, b, c) => ({ lat: a, lng: b, alt: c }),
    latLngBounds: () => ({ pad() { return this }, getCenter: () => ({ lat: 23, lng: 114 }), isValid: () => true, extend() { return this } }),
    control: { layers: () => ({ addTo() { return this } }) },
  };
}

function buildSandbox(withLeaflet) {
  const els = new Map();
  const document = {
    body: makeElement('body'),
    head: makeElement('head'),
    getElementById(id) {
      if (!els.has(id)) els.set(id, makeElement(id));
      return els.get(id);
    },
    createElement(tag) { return makeElement(tag) },
    querySelector() { return null },
    querySelectorAll() { return [] },
    addEventListener() {},
  };

  const timers = [];
  const windowListeners = {};
  const calls = { divIcon: 0 };
  const sandbox = {
    document,
    els,
    calls,
    // 保存监听器，测试里可以手动触发，验证错误横幅真的会显示
    window: {
      innerWidth: 1600, innerHeight: 900, location: { search: '' },
      addEventListener(type, fn, capture) {
        // 同一个类型可能有多个监听（例如空格用捕获阶段拦截），都留着
        (windowListeners[type] ||= []).push({ fn, capture: capture === true });
      },
    },
    windowListeners,
    location: { search: '' },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    setTimeout: (fn) => { timers.push(fn); return timers.length },
    clearTimeout() {},
    setInterval: () => 0,
    clearInterval() {},
    fetch: () => Promise.reject(new Error('测试桩：不发请求')),
    alert() {},
    console,
    URLSearchParams,
    timers,
  };

  // Leaflet 通过 globalThis 提供，方便模拟「晚到」
  if (withLeaflet) globalThis.L = makeLStub(calls);
  else delete globalThis.L;

  return sandbox;
}

function runTopLevel(withLeaflet) {
  const sb = buildSandbox(withLeaflet);
  const names = Object.keys(sb).filter((k) => k !== 'els' && k !== 'timers' && k !== 'calls');
  const code = 'const {' + names.join(',') + '} = __env;\n' + body;
  try {
    new Function('__env', code)(sb);
    return { threw: null, sandbox: sb };
  } catch (e) {
    return { threw: e, sandbox: sb };
  } finally {
    // 留在 globalThis 上会污染下一个场景，但「晚到」场景需要在两段之间保留，
    // 所以由调用方自己清理
  }
}

function drainTimers(sb, max) {
  let ticks = 0;
  let err = null;
  while (sb.timers.length && ticks < (max || 500)) {
    const fn = sb.timers.shift();
    ticks++;
    try { fn(); } catch (e) { err = e; break }
  }
  return { ticks, err };
}

// ============================================================

console.log('=== 场景 1：Leaflet 正常加载（顶层脚本必须跑完）===');
const a = runTopLevel(true);
chk(!a.threw, '顶层脚本执行不抛异常',
  a.threw ? a.threw.constructor.name + ': ' + a.threw.message : '');
if (a.threw) console.log('     ' + (a.threw.stack || '').split('\n').slice(1, 4).join('\n     '));

console.log('\n=== 场景 2：Leaflet 缺失（应降级，但不能抛异常）===');
const b = runTopLevel(false);
chk(!b.threw, '没有 Leaflet 时首次执行不抛异常',
  b.threw ? b.threw.constructor.name + ': ' + b.threw.message : '');
if (b.threw) console.log('     ' + (b.threw.stack || '').split('\n').slice(1, 4).join('\n     '));

// Leaflet 缺失时不会立即启动，而是进入轮询等 CDN 兜底脚本 —— 把定时器排空，
// 模拟轮询耗尽后走降级分支
{
  const { ticks, err } = drainTimers(b.sandbox);
  chk(!err, '轮询过程中不抛异常', err ? err.constructor.name + ': ' + err.message : '');
  chk(ticks > 0, '缺失时进入轮询而不是直接放弃', ticks + ' 次');
  chk(ticks <= 61, '轮询次数有上限（不会无限转）', ticks + ' 次');
}

console.log('\n=== 场景 3：Leaflet 晚到（本地 404 -> CDN 异步到达）===');
{
  // 这正是「打开视频失败: Cannot read properties of null (reading \'createIcon\')」的成因：
  // 顶层先执行（L 还没有）-> 图标被判成 null -> L 到了之后地图能用，但图标永远补不回来。
  const c = runTopLevel(false);
  chk(!c.threw, '首跑（还没有 Leaflet）不抛异常',
    c.threw ? c.threw.constructor.name + ': ' + c.threw.message : '');

  const before = c.sandbox.calls.divIcon;
  chk(before === 0, 'Leaflet 没到时不会去建图标', String(before));

  // 模拟 CDN 脚本到达
  globalThis.L = makeLStub(c.sandbox.calls);

  const { ticks, err } = drainTimers(c.sandbox);
  chk(!err, 'Leaflet 晚到时初始化不抛异常', err ? err.constructor.name + ': ' + err.message : '');
  chk(ticks > 0, '晚到时轮询把它接住了', ticks + ' 次');
  chk(c.sandbox.calls.divIcon >= 3,
    '晚到后补建了图标（否则建 marker 时报 createIcon 为 null）',
    c.sandbox.calls.divIcon + ' 个');
  chk(c.sandbox.els.get('mapNotice').style.display !== 'block',
    '晚到时不显示「未加载」提示');
  delete globalThis.L;
}

console.log('\n=== 初始化真的执行到了吗（不是静默跳过）===');
{
  const sb = a.sandbox;
  // boot() 里会调用各 applyXxxVisibility()，它们会设置开关按钮的 off 类
  const cross = sb.els.get('crosshairToggle');
  const foot = sb.els.get('footprintToggle');
  const pip = sb.els.get('mapPipToggle');

  chk(!!cross && !!foot && !!pip, '三个开关按钮都被访问到（说明 boot 跑到了）');
  chk(cross && !cross._classes.has('off'), '准星默认「开」（不带 off 类）');
  chk(foot && !foot._classes.has('off'), '视场默认「开」');
  // 小地图与红外改成默认关（按需打开）—— 按钮状态用底色表示，初始应是 off
  chk(pip && pip._classes.has('off'), '小地图默认「关」（带 off 类）');
  chk(sb.els.get('mapNotice') && sb.els.get('mapNotice').style.display !== 'block',
    'Leaflet 正常时不应显示「未加载」提示');
  chk(b.sandbox.els.get('mapNotice') && b.sandbox.els.get('mapNotice').style.display === 'block',
    'Leaflet 缺失（轮询耗尽）时显示了明确提示，而不是静默空白');
  {
    const fatal = b.sandbox.els.get('fatalNotice');
    chk(!fatal || fatal.style.display !== 'block',
      '降级路径不应触发「脚本出错」横幅（那是真出错的信号）');
  }
}

console.log('\n=== 错误横幅真的会显示吗（手动触发 window error）===');
{
  // 同一类型可能注册了多个监听（空格用捕获阶段拦截），所以按数组取
  const pick = (type) => {
    const list = a.sandbox.windowListeners[type] || [];
    const hit = list.find((x) => x && typeof x.fn === 'function');
    return hit ? hit.fn : null;
  };

  const handler = pick('error');
  chk(typeof handler === 'function', 'error 监听已注册');
  if (typeof handler === 'function') {
    handler({ message: '模拟的脚本错误', filename: 'http://x/y.js', lineno: 42 });
    const box = a.sandbox.els.get('fatalNotice');
    chk(box && box.style.display === 'block', '触发后横幅显示出来');
    chk(box && /模拟的脚本错误/.test(box.textContent), '横幅里带上了错误信息',
      box ? String(box.textContent).slice(0, 40) : '');
    chk(box && /y\.js:42/.test(box.textContent), '横幅里带上了出错位置');
  }
  const rej = pick('unhandledrejection');
  chk(typeof rej === 'function', 'unhandledrejection 监听已注册');
  if (typeof rej === 'function') {
    const box2 = a.sandbox.els.get('fatalNotice');
    if (box2) box2.style.display = 'none';
    rej({ reason: new Error('模拟的异步错误') });
    chk(box2 && box2.style.display === 'block' && /模拟的异步错误/.test(box2.textContent),
      '未处理的 Promise 错误也会显示');
  }
}

console.log('\n=== 状态变量都在顶层声明（防再次踩暂时性死区）===');
{
  // 顶层会调用 applyXxxVisibility()，它们读这些开关；必须声明在调用之前
  const topCallIdx = Math.min(
    ...['applyCrosshairVisibility();', 'applyFootprintVisibility();', 'applyMapPipVisibility();']
      .map((s) => { const i = body.indexOf('\n' + s); return i < 0 ? Infinity : i; })
  );
  const declIdx = body.indexOf('let mapPipOn=');
  chk(topCallIdx === Infinity, '顶层不再直接调用 applyXxxVisibility()（已移入 boot）',
    topCallIdx === Infinity ? '' : '仍在 ' + topCallIdx);
  chk(declIdx >= 0 && declIdx < body.indexOf('function boot('),
    '开关变量声明在 boot() 之前', 'let mapPipOn @' + declIdx);
  for (const flag of ['crosshairOn', 'footprintOn', 'thermalOn', 'mapPipOn']) {
    const n = (body.match(new RegExp('let ' + flag + '=', 'g')) || []).length;
    chk(n === 1, `开关 ${flag} 只声明一次`, String(n) + ' 次');
  }
}

console.log('\n=== 脚本级错误横幅 ===');
chk(/id="fatalNotice"/.test(html), '页面里有错误横幅元素');
chk(/window\.addEventListener\('error'/.test(body), '注册了 window error 监听');
chk(/window\.addEventListener\('unhandledrejection'/.test(body), '注册了未处理 Promise 监听');
chk(body.indexOf("window.addEventListener('error'") < body.indexOf('const projectSelect='),
  '监听注册在脚本最前面（后续任何异常都能捕获）');

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
