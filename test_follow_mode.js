// 跟随行为的测试。
//
// 为什么要测：这段逻辑是"系统替用户做主"的地方，出错的形态都是
// **看起来正常但用起来别扭** —— 不像崩溃那样显眼。具体要钉住三件事：
//   ① 跟随模式要**记住**（否则每开一个视频都退回默认跟随）
//   ② 用户点了个选点在看别处时，**当次不跟随**（但模式不变）
//   ③ 用户改跟随模式 = 明确表态，抑制立刻解除、并记住新选择

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
    classList: {
      add: (c) => classes.add(c), remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c), toggle() {},
    },
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
  const map = chain({
    on(ev, fn) { (handlers[ev] ||= []).push(fn); return map },
  });
  const L = {
    map: () => map, tileLayer: () => chain(), layerGroup: () => chain(),
    featureGroup: () => chain(), geoJSON: () => chain(), marker: () => chain(),
    polyline: () => chain(), polygon: () => chain(), imageOverlay: () => chain(),
    divIcon: () => ({}), icon: () => ({}),
    latLng: (a, b) => ({ lat: a, lng: b }),
    latLngBounds: (sw, ne) => {
      const norm = (p) => Array.isArray(p) ? { lat: p[0], lng: p[1] } : p;
      return {
        getSouthWest: () => norm(sw), getNorthEast: () => norm(ne),
        isValid: () => true, contains: () => true,
        pad() { return bounds }, extend() { return bounds },
      };
    },
    control: () => chain(), DomUtil: { create: () => makeEl('div') }, Browser: {},
    Point: (x, y) => ({ x, y }), setOptions() {}, extend() {},
  };
  return { L, handlers, container };
}

// localStorage 桩（顺便能验"有没有存"）
function makeStorage(initial) {
  const store = new Map(Object.entries(initial || {}));
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)) },
    removeItem: (k) => { store.delete(k) },
    _dump: () => Object.fromEntries(store),
  };
}

function run({ savedFollow = null } = {}) {
  const els = new Map();
  const storage = makeStorage(savedFollow ? { 'droneMap.followMode': savedFollow } : {});
  const document = {
    body: makeEl('body'), head: makeEl('head'),
    getElementById(id) {
      if (!els.has(id)) {
        const e = makeEl(id === 'followMode' ? 'select' : 'div');
        e.id = id;
        // select 的默认值：HTML 里第一项是 fit
        if (id === 'followMode') e.value = 'fit';
        els.set(id, e);
      }
      return els.get(id);
    },
    createElement: (t) => makeEl(t),
    querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
    _els: els,
  };
  const timers = [];
  const { L, handlers, container } = makeL();
  globalThis.L = L;
  const sb = {
    document, els, L,
    localStorage: storage,
    window: { innerWidth: 1600, innerHeight: 900, location: { search: '' }, addEventListener() {} },
    location: { search: '' },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    setTimeout: (fn) => { timers.push(fn); return timers.length },
    clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    fetch: () => Promise.reject(new Error('桩：不发请求')),
    alert() {}, console, URLSearchParams,
    navigator: { userAgent: 'node' },
  };
  const names = Object.keys(sb);
  const code = 'const {' + names.join(',') + '} = __env;\n' + body;
  const ret = '\n;return {followDebugState, followViewport, coverageDebugState, setProbe,' +
    ' saveFollowMode, readSavedFollowMode, followModeSelect, map};';
  let threw = null, api = null;
  try {
    api = new Function('__env', code + ret)(sb);
  } catch (e) { threw = e }
  return { threw, api, sandbox: sb, handlers, container, storage, els };
}

console.log('=== 1) 页面脚本能跑完 ===');
{
  const r = run();
  chk(!r.threw, '顶层脚本执行不抛异常',
    r.threw ? r.threw.constructor.name + ': ' + r.threw.message : '');
}

console.log('\n=== 2) 跟随模式会记住（这是"别每次都替我决定"的关键）===');
{
  const r = run({ savedFollow: 'off' });
  chk(!r.threw, '带已存偏好时也能启动',
    r.threw ? r.threw.constructor.name + ': ' + r.threw.message : '');
  chk(r.api && r.api.followDebugState().mode === 'off',
    '启动时读回上次的 No follow（不是 HTML 里写死的 fit）',
    r.api ? r.api.followDebugState().mode : '');
  chk(r.api && r.api.followDebugState().saved === 'off', '探针也看得到存的值');
}
{
  const r = run({ savedFollow: 'center' });
  chk(r.api && r.api.followDebugState().mode === 'center', 'center 也能记住',
    r.api ? r.api.followDebugState().mode : '');
}
{
  const r = run();   // 没有存过
  chk(r.api && r.api.followDebugState().mode === 'fit', '没存过就用默认 fit',
    r.api ? r.api.followDebugState().mode : '');
  chk(r.api && r.api.followDebugState().saved === null, 'saved 为空');
}

console.log('\n=== 3) 改跟随模式会被写下来 ===');
{
  const r = run();
  const sel = r.api.followModeSelect;
  sel.value = 'off';
  sel._listeners.change.forEach((fn) => fn({}));
  chk(r.storage.getItem('droneMap.followMode') === 'off',
    '选 No follow 后写进了 localStorage', JSON.stringify(r.storage._dump()));
  sel.value = 'center';
  sel._listeners.change.forEach((fn) => fn({}));
  chk(r.storage.getItem('droneMap.followMode') === 'center', '改成 center 也会更新');
}

console.log('\n=== 4) localStorage 不可用时不能把页面搞崩 ===');
{
  // 注意：不能在建好沙箱之后换 sandbox.localStorage —— 页面里的
  // readSavedFollowMode 是从沙箱**解构**出来的，闭包已经绑到原来那个对象上，
  // 换属性对它无效（我第一次就是这么写的，验了个假）。
  // 改成：验正常路径 + 直接读源码确认异常被吞掉。
  const r = run();
  let threw = null, v = 'x';
  try {
    r.api.saveFollowMode('off');
    v = r.api.readSavedFollowMode();
  } catch (e) { threw = e }
  chk(!threw && v === 'off', '正常路径能存能读', `${v}`);
  chk(r.api.readSavedFollowMode() === null || r.api.readSavedFollowMode() === 'off',
    '再读仍然稳定');

  const grab = (name, span) => {
    const i = body.indexOf('function ' + name);
    return i < 0 ? '' : body.slice(i, i + span);
  };
  const readFn = grab('readSavedFollowMode', 200);
  const saveFn = grab('saveFollowMode', 160);
  chk(/try\s*\{/.test(readFn) && /catch\s*\(\s*e\s*\)\s*\{\s*return null\s*\}/.test(readFn),
    'readSavedFollowMode：异常吞掉并返回 null', readFn.replace(/\s+/g, ' ').slice(0, 90));
  chk(/try\s*\{/.test(saveFn) && /catch\s*\(\s*e\s*\)\s*\{\s*\}/.test(saveFn),
    'saveFollowMode：异常吞掉', saveFn.replace(/\s+/g, ' ').slice(0, 90));

  const r2 = run();
  chk(r2.api.readSavedFollowMode() === null, '没存过返回 null');
}

console.log('\n=== 5) 点选点 -> 当次不跟随（但模式不变）===');
{
  const r = run();
  const clickFns = r.handlers.click || [];
  chk(clickFns.length > 0, '地图 click 已注册', String(clickFns.length));
  const before = r.api.followDebugState();
  chk(before.suppressed === false, '初始没有抑制');
  chk(before.mode === 'fit', '初始模式 fit');
  // 像用户那样点地图
  clickFns.forEach((fn) => fn({ latlng: { lat: 23.05, lng: 114.11 } }));
  const after = r.api.followDebugState();
  chk(after.suppressed === true, '点完之后置位「本次不跟随」');
  chk(after.mode === 'fit', '模式没被改掉（还是 fit）', after.mode);
  chk(after.saved === null, '也没有偷偷写偏好', String(after.saved));
}

console.log('\n=== 6) 抑制期间 followViewport 不动地图 ===');
{
  const r = run();
  // 先造一个"视频开着"的状态：直接给 clip 赋值不方便（闭包变量），
  // 所以用真链路 —— openVideoFromPopup 需要 telemetry 等一堆，代价太大。
  // 这里改成验**判断顺序**：抑制标记必须排在「没有 clip 就返回」之后、
  // 「按模式跟随」之前，否则要么不生效、要么把 mode=off 也一起挡了。
  chk(/function followViewport\(\)\{[\s\S]{0,200}if\(followSuppressedByProbe\)/
      .test(body.replace(/\r/g, '')),
    'followViewport 一开始就检查抑制标记');
  const iSupp = body.indexOf('if(followSuppressedByProbe)');
  const iOff = body.indexOf("if(mode==='off')return", iSupp);
  chk(iSupp > 0 && iOff > iSupp, '抑制检查在「按模式分支」之前（先让位再判断模式）',
    `suppress@${iSupp} off@${iOff}`);
  chk(/Map follow is paused for this selection/.test(body),
    '抑制时给出说明，不让用户以为跟随坏了');
}

console.log('\n=== 7) 改跟随模式 = 明确表态，抑制立刻解除 ===');
{
  const r = run();
  (r.handlers.click || []).forEach((fn) => fn({ latlng: { lat: 23.05, lng: 114.11 } }));
  chk(r.api.followDebugState().suppressed === true, '先处于抑制状态');
  const sel = r.api.followModeSelect;
  sel.value = 'center';
  sel._listeners.change.forEach((fn) => fn({}));
  chk(r.api.followDebugState().suppressed === false, '改模式后抑制解除');
  chk(r.storage.getItem('droneMap.followMode') === 'center', '同时记住了新选择');
}

console.log('\n=== 8) 用户拖地图 = 解除抑制（他已在主动掌控）===');
{
  const r = run();
  (r.handlers.click || []).forEach((fn) => fn({ latlng: { lat: 23.05, lng: 114.11 } }));
  chk(r.api.followDebugState().suppressed === true, '先处于抑制状态');
  // dragstart 就是"用户动手"的信号（mark() 挂在它上面）
  (r.handlers.dragstart || []).forEach((fn) => fn({}));
  chk(r.api.followDebugState().suppressed === false, '拖动后抑制解除');
}

console.log('\n=== 9) URL 参数优先于记忆（便于分享固定视角）===');
{
  const i0 = body.indexOf('(function initFollowMode()');
  const fn = body.slice(i0, i0 + 700);
  // 页面里用的是双引号 get("follow")，两种引号都要认
  const iUrl = Math.min(...['get("follow")', "get('follow')"]
    .map((s) => fn.indexOf(s)).filter((x) => x >= 0));
  const iSaved = fn.indexOf('readSavedFollowMode()');
  chk(/get\(["']follow["']\)/.test(fn), '仍然支持 ?follow= 参数');
  chk(iUrl >= 0 && iSaved > iUrl, 'URL 参数先判、记忆后判（URL 优先）',
    `url@${iUrl} saved@${iSaved}`);
  chk(/else\s*\{[\s\S]{0,220}readSavedFollowMode\(\)/.test(fn),
    '只有在没有 URL 参数时才用记忆');
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
