// 真正执行页面顶层脚本，验证它能跑完初始化。
//
// 为什么需要这个测试：check_page.js 的 `new Function(body)` 只做「语法编译」，
// 抓不到运行期错误。而「暂时性死区」正是运行期错误 —— 顶层的
// applyXxxVisibility() 调用了后面的函数，那个函数读到还没初始化的 let，
// 就抛 ReferenceError 并中断整个顶层脚本，页面只剩几个空白框。
// 这个测试把顶层脚本真的跑一遍，两种场景都必须不抛异常。
const fs = require('fs');
const path = require('path');

// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');
const html = fs.readFileSync(HTML, 'utf8');
const m = html.match(/<script>\s*([\s\S]*?)<\/script>/);
if (!m) throw new Error('找不到主 <script> 块');
const body = m[1];

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

// ---------- DOM 桩 ----------
function makeElement(id, tag) {
  const classes = new Set();
  const el = {
    id,
    tagName: tag || 'div',
    children: [],
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
    addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn) },
    removeEventListener() {},
    // 触发这个元素上挂的监听（照片图层那块要真的点一下才算跑到）
    _fire(type, ev) {
      for (const fn of (this._listeners[type] || [])) fn(ev === undefined ? { type } : ev);
    },
    _listeners: {},
    // 浏览器里 <select> 追加第一个 option 会自动选中它；桩也必须这样，
    // 否则 projectSelect.value 一直是空串，scanGeoJSON 直接返回，
    // 「载入项目 -> 取照片」这条链根本走不到（踩过）。
    appendChild(child) {
      this.children.push(child);
      if (this.tagName === 'select' && !this.value && child && child.value !== undefined) {
        this.value = child.value;
      }
    },
    removeChild() {}, insertAdjacentHTML() {},
    querySelector() { return null }, querySelectorAll() { return [] },
    setAttribute(k, v) { this._attrs[k] = String(v) },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null },
    removeAttribute(k) { delete this._attrs[k] },
    _attrs: {},
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
    _isMap: true,
    _layers: [],
    addLayer(l) { this._layers.push(l); return this },
    setView() { return this }, on() { return this }, off() { return this },
    setMaxZoom() {}, getZoom() { return 9 }, setZoom() {}, zoomIn() {}, zoomOut() {},
    removeLayer() {}, hasLayer() { return false },
    invalidateSize() {}, panTo() {}, getBoundsZoom() { return 12 },
    // 记录每次 fitBounds（视野缩放）的调用：点「加载全部照片」时要验它
    fitBounds(bounds, options) {
      calls.fitBounds.push({
        points: (bounds && bounds._points) ? bounds._points.length : 0,
        padding: options && options.padding,
        maxZoom: options && options.maxZoom,
      });
      return this;
    },
    getCenter: () => ({ lat: 23, lng: 114, distanceTo: () => 0 }),
    distance: () => 0,
  };
  // 图层桩：把自己收到的子图层记下来（_added / _layers），
  // 这样测试能验证「照片点真的建出来并加进地图了」，而不只是「没抛异常」。
  const layerStub = function layerStub() {
    const self = {
      _added: [],
      _layers: [],
      addTo(target) { if (target && typeof target.addLayer === 'function') target.addLayer(this); return this },
      addLayer(l) { this._layers.push(l); return this },
      clearLayers() { this._layers.length = 0; this._added.length = 0; return this },
      eachLayer(fn) { for (const l of this._layers) fn(l) },
      // on() 要真的把处理函数记下来：照片点的点击测试靠 _fire 触发它。
      // 只 `return this` 的话「点了照片点会不会打开展示区」就永远测不到。
      on(type, fn) { if (typeof fn === 'function') (this._listeners[type] ||= []).push(fn); return this },
      off() { return this },
      bringToBack() { return this }, bringToFront() { return this },
      setLatLngs() { return this }, setStyle() {}, bindPopup() { return this },
      bindTooltip() { return this }, unbindTooltip() { return this },
      getElement() { return null }, getLatLng() { return { lat: 23, lng: 114 } },
      setLatLng() { return this }, remove() {}, setIcon() {},
      addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn) },
      _listeners: {},
      _fire(type, ev) { for (const fn of (this._listeners[type] || [])) fn(ev === undefined ? { type } : ev) },
    };
    // featureGroup/layerGroup 都靠 addTo 记录；marker 也走同一条路
    self.addTo = (target) => {
      if (target && target._added) target._added.push(self);
      if (target && typeof target.addLayer === 'function') target.addLayer(self);
      return self;
    };
    return self;
  };
  return {
    map: () => mapStub,
    tileLayer: layerStub, polyline: layerStub, polygon: layerStub,
    featureGroup: layerStub, layerGroup: layerStub,
    // 所有 marker 都收进 calls.markers —— 不依赖图层桩的内部结构，
    // 直接看「建了几个、上面挂了什么」最可靠。
    marker: (...args) => { const m = layerStub(...args); calls.markers.push(m); return m },
    geoJSON: layerStub,
    divIcon: () => { calls.divIcon++; return {} },
    icon: () => ({}),
    latLng: (a, b, c) => ({ lat: a, lng: b, alt: c }),
    // 记下 extend 进来的点，供 fitBounds 断言「覆盖了几个照片点」
    latLngBounds: () => {
      const b = {
        _points: [],
        isValid: () => b._points.length > 0,
        pad() { return this },
        extend(p) { b._points.push(p); return this },
        getCenter: () => ({ lat: 23, lng: 114 }),
      };
      return b;
    },
    control: { layers: () => ({ addTo() { return this } }) },
    DomEvent: { stopPropagation() {} },
  };
}

function buildSandbox(withLeaflet) {
  const els = new Map();
  // 几个标签名会影响行为的元素：<select> 追加第一个 option 会自动选中它，
  // 桩里必须照做（否则 projectSelect.value 恒为空，载入项目那条链直接断）。
  const TAGS = { projectSelect: 'select', filterDate: 'select', filterType: 'select', baseMap: 'select', followMode: 'select' };
  const document = {
    body: makeElement('body'),
    head: makeElement('head'),
    getElementById(id) {
      if (!els.has(id)) els.set(id, makeElement(id, TAGS[id] || 'div'));
      return els.get(id);
    },
    createElement(tag) { return makeElement(tag, String(tag).toLowerCase()) },
    querySelector() { return null },
    querySelectorAll() { return [] },
    addEventListener() {},
  };

  const timers = [];
  const windowListeners = {};
  const calls = { divIcon: 0, mapStub: null, markers: [], fitBounds: [] };
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
  if (withLeaflet) {
    const stub = makeLStub(calls);
    calls.mapStub = stub.map();
    globalThis.L = stub;
  } else delete globalThis.L;

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

console.log('\n=== 照片图层真的能点亮吗（真跑一次点击）===');
(async () => {
  // 场景 1 的沙箱里 fetch 一律 reject，照片那块只能走到「读取失败」分支。
  // 这里换一个能应答的 fetch，把「载入项目 -> 照片计数 -> 打开图层 -> 点一个照片点」
  // 这条链真的走一遍 —— 顶层脚本不抛异常只说明初始化没崩，不说明功能通。
  const sb = buildSandbox(true);
  const svgHolder = [];
  const PHOTO = {
    groups: [
      { stamp: '20260924_095348', folder: 'D:\\数据\\架次1', lat: 23.0415, lon: 114.1064,
        accuracy: '实测', count: 2, lead: 'WideCamera',
        members: [
          { name: 'DJI_20260924095348_0002_V.JPG', folder: 'D:\\数据\\架次1', camera: 'WideCamera',
            accuracy: '实测', accuracy_note: '', lat: 23.0415, lon: 114.1064,
            distance: 178.6, depression: 29.4, gimbal_yaw: 166.7, relative_alt: 97.2,
            drone_lat: 23.043, drone_lon: 114.106 },
          { name: 'DJI_20260924095348_0002_T.JPG', folder: 'D:\\数据\\架次1', camera: 'InfraredCamera',
            accuracy: '实测', accuracy_note: '', lat: 23.0415, lon: 114.1064,
            distance: 178.6, depression: 29.4, gimbal_yaw: 166.7, relative_alt: 97.2,
            drone_lat: 23.043, drone_lon: 114.106 }
        ] },
      { stamp: '20260924_102746', folder: 'D:\\数据\\架次1', lat: 23.05, lon: 114.11,
        accuracy: '位置不准', count: 1, lead: 'WideCamera',
        members: [
          { name: 'DJI_20260924102746_0034_T.JPG', folder: 'D:\\数据\\架次1', camera: 'InfraredCamera',
            accuracy: '位置不准', accuracy_note: '该张没有激光数据，中心点按平地假设估算',
            lat: 23.05, lon: 114.11, distance: 171.5, depression: 19.8, gimbal_yaw: 200,
            relative_alt: 97, drone_lat: 23.06, drone_lon: 114.11 }
        ] }
    ],
    counts: { groups: 2, photos: 3, with_target: 3, inaccurate: 1, merged: 1 }
  };

  sb.fetch = (url) => {
    const u = String(url);
    (sb.debugFetches ||= []).push(u);
    const json = (o) => Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(o)) });

    if (u.includes('/api/project/list')) return json({ projects: [{ name: '测试项目' }] });
    if (u.includes('/api/project/get')) return json({ project: { folders: [{ path: 'D:\\数据\\架次1' }] } });
    if (u.includes('/api/project/photos')) return json(PHOTO);
    if (u.includes('/api/project/geojson-list')) return json({ files: [] });

    return json({});
  };

  // divIcon 的 html 参数里带着照片点/叹号；className 里带着 photo-warn
  const realDivIcon = globalThis.L.divIcon;
  const iconOpts = [];
  globalThis.L.divIcon = (opts) => {
    svgHolder.push(String((opts && opts.html) || ''));
    iconOpts.push(opts || {});
    return realDivIcon(opts);
  };

  let threw = null;
  try {
    new Function('__env',
      'const {' + Object.keys(sb).filter((k) => !['els', 'timers', 'calls'].includes(k)).join(',') + '} = __env;\n' + body
    )(sb);
  } catch (e) { threw = e }

  chk(!threw, '带照片接口的顶层脚本执行不抛异常', threw ? threw.message : '');


  // 排空定时器（等待 fetch 链），再把挂起的 Promise 多跑几轮 —— leafletWait 轮询
  // 与「载入项目 -> 取照片」都是异步的，一次 drainTimers 不一定够。
  for (let round = 0; round < 5; round++) {
    drainTimers(sb, 200);
    await new Promise((r) => setImmediate(r));
  }

  const count = sb.els.get('photoLayerCount');
  const countExtra = sb.els.get('photoLayerCountExtra');
  chk(count && /3 张 → 2 个点/.test(String(count.textContent)),
    '照片计数写到位（3 张 → 2 个点）', count ? String(count.textContent) : '-');
  chk(countExtra && /1 处合并/.test(String(countExtra.textContent)),
    '合并了几处单独一段（窄窗口时它能整段让位，不挤掉主信息）',
    countExtra ? String(countExtra.textContent) : '-');

  // 标记点卡片：默认收起（用户要求把高度让给照片与视频），点箭头能展开
  {
    const mCard = sb.els.get('markerCard');
    const mArrow = sb.els.get('markerCollapseBtn');

    chk(mCard && mCard._classes.has('is-collapsed'), '标记点卡片默认收起');
    chk(mArrow && String(mArrow.getAttribute('aria-expanded')) === 'false',
      '收起时 aria-expanded=false', mArrow ? String(mArrow.getAttribute('aria-expanded')) : '-');
    chk(mArrow && String(mArrow.textContent) === '▸', '收起时箭头朝右 ▸',
      mArrow ? String(mArrow.textContent) : '-');

    if (mArrow) mArrow._fire('click');
    chk(mCard && !mCard._classes.has('is-collapsed'), '点箭头后展开');
    chk(mArrow && String(mArrow.getAttribute('aria-expanded')) === 'true', '展开时 aria-expanded=true');
    chk(mArrow && String(mArrow.textContent) === '▾', '展开时箭头朝下 ▾',
      mArrow ? String(mArrow.textContent) : '-');
    chk(mArrow && /收起标记点/.test(String(mArrow.title)), '展开后悬停提示变成「收起标记点」');

    if (mArrow) mArrow._fire('click');
    chk(mCard && mCard._classes.has('is-collapsed'), '再点一次又收起');
    // #markerBody 是纯 CSS 包裹层（JS 不引用，靠 .is-collapsed 隐藏），
    // 所以这里验 HTML 里有它、且包着列表；元素本身用 html 段断言。
    chk(/id="markerBody"/.test(html), '#markerBody 在页面 HTML 里（收起时整块隐藏的包裹层）');
    chk(/id="markerBody"[\s\S]{0,400}id="markerList"/.test(html), '#markerBody 里包着 #markerList');
  }

  const btn = sb.els.get('photoLayerBtn');
  chk(btn && btn._classes.has('off'), '照片图层默认关（不挡航迹）');
  chk(btn && String(btn.textContent || '') === '', '开关按钮取得到');

  // 点一下「加载全部照片」：应该建出两个照片点，并把视野缩放到全部照片
  const before = svgHolder.length;
  let toggleErr = null;
  if (btn) { try { btn._fire('click') } catch (e) { toggleErr = e } }
  const made = svgHolder.length - before;
  chk(!toggleErr, '点「加载全部照片」不抛异常', toggleErr ? toggleErr.message : '');
  chk(made >= 2, '打开后为每个照片点建了图标', made + ' 个');
  chk(!btn || !btn._classes.has('off'), '按钮的 off 类被摘掉了（看着是「开」）');
  chk(btn && String(btn.getAttribute('aria-pressed')) !== 'false' || !btn, 'aria-pressed 跟着变');

  // 视野缩放：桩里记下 fitBounds 的调用，验证「一次把全部照片摆进画面」
  chk(sb.calls.fitBounds.length === 1, '点按钮时调了一次 fitBounds（自动缩放到全部照片）',
    String(sb.calls.fitBounds.length) + ' 次');
  {
    const call = sb.calls.fitBounds[0];
    chk(!!call, '拿到了 fitBounds 的参数');
    chk(call && call.points === 2, '外接矩形覆盖了 2 个照片点', call ? String(call.points) : '-');
    chk(call && call.maxZoom === 15, '带 maxZoom 上限（复用 TRACK_FIT_MAX_ZOOM=15，看得全而不是看得近）',
      call ? String(call.maxZoom) : '-');
    chk(call && Array.isArray(call.padding) && call.padding.length === 2, '带 padding（点不会贴边）');
  }

  const iconHtml = svgHolder.slice(before).join('\n');
  const iconCls = iconOpts.slice(before).map((o) => String(o.className || '')).join('\n');
  chk(/photo-dot/.test(iconHtml), '照片点用 SVG 圆点画');
  chk(/photo-warn/.test(iconCls), '「位置不准」的那个点带 photo-warn 类',
    iconCls.replace(/\s+/g, ' ').slice(0, 80));
  chk(/photo-dot-mark/.test(iconHtml), '「位置不准」的圆里画了叹号（.photo-dot-mark）');
  chk((iconHtml.match(/--photo-dot:#f5b301/g) || []).length === 1,
    '只有那一个「位置不准」的是黄点（实测的不黄）',
    String((iconHtml.match(/--photo-dot:#f5b301/g) || []).length) + ' 个');
  chk(/--photo-dot:#1d4ed8/.test(iconHtml), '实测那个点是蓝色');
  chk(!/⚠/.test(iconHtml), '图标里不再有 ⚠ 三角（合并成一个叹号了）');

  // 点第一个照片点：展示区应被打开，并把该组全部成员放出来
  const card = sb.els.get('photoCard');
  const gallery = sb.els.get('photoGallery');

  // 开关那一下新建的图标个数，就是照片点的个数（每个点一个 divIcon）
  chk(made === 2, '两个照片点 = 两次 divIcon（一组一个点）', made + ' 个');

  // 照片点：从 calls.markers 里按「挂没挂点击处理」筛出来。
  // 不依赖图层桩的内部结构 —— 数「建了几个、上面挂了什么」最可靠。
  const markers = sb.calls.markers.filter((m) => m._listeners && m._listeners.click);
  chk(markers.length === 2, '两个照片点都挂了点击处理', markers.length + ' 个');

  const marker = markers[0];
  chk(!!marker, '照片点确实建出来了（不是只建了图标）');

  if (marker) {
    marker._fire('click', { originalEvent: {} });
    chk(card && card.style.display === 'block', '点照片点后地图下方的展示区打开了');
    const html2 = gallery ? String(gallery.innerHTML) : '';
    chk(/DJI_20260924095348_0002_V\.JPG/.test(html2), '展示区里放出了该组的可见光那张');
    chk(/DJI_20260924095348_0002_T\.JPG/.test(html2), '同组的红外那张也一起放出来了');
    chk(/photo-lead/.test(html2), '两张按「大图 + 小图」排版');
    chk(/\/photo\?path=/.test(html2), '图片走后端 /photo 接口');
    chk(/正在查找对应的视频/.test(String(sb.els.get('photoJump').innerHTML)),
      '展示区里那块「跳视频」先给出「正在查找」而不是空白');

    // 收起
    const closeBtn = sb.els.get('photoCloseBtn');
    if (closeBtn) closeBtn._fire('click', {});
    chk(card && card.style.display === 'none', '收起按钮把展示区收起来了');
  }

  globalThis.L.divIcon = realDivIcon;
})().then(() => {
  // 照片那段是异步的（要等 fetch 链），所以收尾放进 then ——
  // 否则 process.exit 会先跑，异步断言还没来得及判定。
  console.log('\n结果:', ok ? '全部通过' : '有失败项');
  process.exit(ok ? 0 : 1);
});
