// 「这个位置被哪些画面拍到过」图墙的端到端测试。
//
// 为什么值得单独测：
//   ① 图墙要跨架次 —— 只在一个架次里找就退化成了已有的 A+B 检索
//   ② 缩略图 URL 必须带对 folder_index / path / t，任何一个错都会让
//      「图是 A 位置、点开跳到 B 时刻」这种很难发现的错
//   ③ 点图必须真的调 openVideoFromPopup，且 photo_pause_at 要能算出"到点暂停"
//
// 做法：用真实页面脚本 + 桩 fetch（返回合成的检索结果），
// 像用户一样点按钮，然后把渲染出来的卡片和跳播参数读回来比对。

const fs = require('fs');
const path = require('path');

// 顶层不能用 await（会和 require 撞成 "ambiguous module syntax"），
// 所以主体包在一个 async 函数里，末尾再调它。
const tick = () => new Promise((res) => setImmediate(res));

async function main() {

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

// 极简 innerHTML 解析：页面大量用 `box.innerHTML='<h4>..</h4><div class="sub">..</div>'`，
// 桩如果只把 innerHTML 当字符串存，querySelector('h4') 就永远取不到 ——
// 那验的就不是页面而是桩了。这里只处理这些简单结构：普通标签 + class 属性 + 文本。
function parseHtml(str) {
  const nodes = [];
  const re = /<(\/?)([a-zA-Z0-9]+)([^>]*)>/g;
  const stack = [{ children: nodes }];
  let last = 0, mm;
  const textOf = (s) => s.replace(/<[^>]*>/g, '').trim();
  while ((mm = re.exec(str))) {
    const [full, closing, tag, attrsRaw] = mm;
    const between = str.slice(last, mm.index);
    if (between.trim()) {
      const top = stack[stack.length - 1];
      if (top) top.children.push({ _text: textOf(between) });
    }
    last = mm.index + full.length;
    const selfClose = /\/$/.test(attrsRaw) || ['img', 'br', 'input', 'hr'].includes(tag.toLowerCase());
    if (closing) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    const el = makeEl(tag);
    const cm = attrsRaw.match(/class="([^"]*)"/);
    if (cm) {
      el.className = cm[1];
      cm[1].split(/\s+/).filter(Boolean).forEach((c) => el._classes.add(c));
    }
    const im = attrsRaw.match(/id="([^"]*)"/);
    if (im) el.id = im[1];
    const tm = attrsRaw.match(/title="([^"]*)"/);
    if (tm) el.title = tm[1];
    const dm = attrsRaw.match(/data-thumb="([^"]*)"/);
    if (dm) el.setAttribute('data-thumb', dm[1]);
    const top = stack[stack.length - 1];
    if (top) top.children.push(el);
    if (!selfClose) stack.push(el);
  }
  const tail = str.slice(last);
  if (tail.trim()) {
    const top = stack[stack.length - 1];
    if (top) top.children.push({ _text: textOf(tail) });
  }
  return nodes;
}

// ---------- DOM 桩（比 test_boot 的略强：支持查询已渲染的子节点）----------
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
      contains: (c) => classes.has(c),
      toggle: (c, on) => { if (on === undefined) on = !classes.has(c); on ? classes.add(c) : classes.delete(c) },
    },
    addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn) },
    removeEventListener() {},
    appendChild(c) { this.children.push(c); c.parentElement = this; return c },
    insertBefore(c) { this.children.unshift(c); return c },
    remove() {
      if (this.parentElement) {
        const i = this.parentElement.children.indexOf(this);
        if (i >= 0) this.parentElement.children.splice(i, 1);
      }
    },
    setAttribute(k, v) { this._attrs[k] = String(v) },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null },
    removeAttribute(k) { delete this._attrs[k] },
    querySelector(sel) { return walkFind(this, sel) },
    querySelectorAll(sel) { const out = []; walk(this, sel, out); return out },
    focus() {}, blur() {}, click() {},
  };
  // innerHTML 一旦被赋值就解析成真实子树（否则 querySelector 查不到）
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html || '' },
    set(v) {
      el._html = String(v);
      el.children.length = 0;
      for (const n of parseHtml(el._html)) {
        if (n._text !== undefined) { el.textContent = (el.textContent || '') + n._text; continue }
        el.children.push(n); n.parentElement = el;
      }
    },
  });
  return el;
}

// 极简选择器支持：.class / #id / tag / [attr] / tag[attr] / .class tag
function matches(node, sel) {
  if (!node || node._text !== undefined) return false;   // 纯文本节点不参与选择器
  const s = sel.trim();
  const attrM = s.match(/\[([\w-]+)\]/);
  if (attrM && !(attrM[1] in node._attrs)) return false;
  let rest = s.replace(/\[[\w-]+\]/g, '').trim();
  const classM = rest.match(/\.([\w-]+)/g) || [];
  for (const c of classM) {
    if (!node._classes.has(c.slice(1)) && !String(node.className || '').split(/\s+/).includes(c.slice(1))) return false;
  }
  const idM = rest.match(/#([\w-]+)/);
  if (idM && node.id !== idM[1]) return false;
  const tagM = rest.replace(/[.#][\w-]+/g, '').trim();
  if (tagM && node.tagName !== tagM.toUpperCase()) return false;
  return true;
}
function walk(node, sel, out) {
  if (!node || !node.children) return;
  for (const c of node.children) {
    if (c._text !== undefined) continue;
    if (matches(c, sel)) out.push(c);
    walk(c, sel, out);
  }
}
function walkFind(node, sel) { const o = []; walk(node, sel, o); return o[0] || null }

// 在文档树里按 id 找（不是查缓存）—— 判断"子树还在不在文档里"要用它
function idInTree(node, id) {
  if (!node || !node.children) return null;
  for (const c of node.children) {
    if (c._text !== undefined) continue;
    if (c.id === id) return c;
    const hit = idInTree(c, id);
    if (hit) return hit;
  }
  return null;
}

// 递归取节点文本（桩的 textContent 只是被赋过的那部分，
// 子节点里的文字要自己往下收）
function textOfNode(node) {
  if (!node) return '';
  if (node._text !== undefined) return node._text;
  let s = '';
  for (const c of (node.children || [])) s += c._text !== undefined ? c._text : textOfNode(c);
  return s || String(node.textContent || '');
}

// ---------- 沙箱 ----------
function build() {
  const els = new Map();
  const document = {
    body: makeEl('body'), head: makeEl('head'),
    // 先找文档里已有的，再退回缓存 —— 页面探针要判断"子树还在不在文档里"，
    // 缓存里那份可能已经脱离了。
    getElementById(id) {
      const found = idInTree(document.body, id);
      if (found) { els.set(id, found); return found }
      if (!els.has(id)) { const e = makeEl('div'); e.id = id; els.set(id, e) }
      return els.get(id);
    },
    createElement: (t) => makeEl(t),
    querySelector(sel) {
      // #id 优先查文档树；查不到就退回注册表 —— 桩里大量元素是
      // getElementById 按需创建、并没有真的挂在 body 上。
      if (typeof sel === 'string' && sel.startsWith('#')) {
        const id = sel.slice(1);
        return idInTree(document.body, id) || els.get(id) || null;
      }
      const o = []; walk(document.body, sel, o); return o[0] || null;
    },
    querySelectorAll: () => [], addEventListener() {},
    _els: els,
  };
  // 让文档知道"谁在文档里"：页面探针靠这个判断子树有没有脱离
  document.ownerDocument = document;
  // 让 document.querySelectorAll 真的能查到 body 下的东西
  document.querySelectorAll = (sel) => { const o = []; walk(document.body, sel, o); return o };

  const calls = { videoOpen: [], fetchUrls: [] };
  let fetchImpl = () => Promise.reject(new Error('未设置的桩'));
  const timers = [];

  const sb = {
    document, els, calls,
    window: { innerWidth: 1600, innerHeight: 900, location: { search: '' }, addEventListener() {} },
    location: { search: '' },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    setTimeout: (fn) => { timers.push(fn); return timers.length },
    clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    fetch: (url) => { calls.fetchUrls.push(String(url)); return fetchImpl(String(url)) },
    alert() {}, console, URLSearchParams,
    navigator: { userAgent: 'node' },
    _timers: timers,
    _setFetch(fn) { fetchImpl = fn },
  };
  return sb;
}

function makeL(calls) {
  // 用 Proxy 自动补方法：Leaflet 的地图/图层 API 太多（setMaxZoom、setView、
  // zoomControl……），逐个桩会一直漏。任何没显式定义的方法都返回一个
  // 可链式的自身，属性访问也给个合理默认。
  const chain = (extra = {}) => new Proxy(extra, {
    get(t, k) {
      if (k in t) return t[k];
      if (k === 'getBounds') return () => bounds;
      if (k === 'getZoom' || k === 'getMaxZoom' || k === 'getMinZoom') return () => 15;
      if (k === 'isValid') return () => true;
      if (typeof k === 'string' && /^_/.test(k)) return undefined;
      // 未知成员一律当成可链式方法
      const fn = (...a) => chain(extra);
      return fn;
    },
  });
  const bounds = chain({
    isValid: () => true,
    getSouthWest: () => ({ lat: 0, lng: 0 }),
    getNorthEast: () => ({ lat: 1, lng: 1 }),
    pad: () => bounds,
    extend: () => bounds,
  });
  const mk = () => chain();
  return {
    map: mk, tileLayer: mk, layerGroup: mk, featureGroup: mk, geoJSON: mk,
    marker: mk, polyline: mk, polygon: mk, circle: mk, circleMarker: mk,
    imageOverlay: mk, divIcon: () => ({}), icon: () => ({}),
    latLng: (a, b) => ({ lat: a, lng: b }),
    latLngBounds: (sw, ne) => {
      const norm = (p) => Array.isArray(p) ? { lat: p[0], lng: p[1] } : p;
      return {
        _sw: norm(sw), _ne: norm(ne),
        getSouthWest: () => norm(sw), getNorthEast: () => norm(ne),
        isValid: () => true, pad() { return bounds }, extend() { return bounds },
      };
    },
    control: mk, DomUtil: { create: () => makeEl('div') }, Browser: {},
    Point: (x, y) => ({ x, y }), setOptions() {}, extend() {},
  };
}

function run() {
  const sb = build();
  globalThis.L = makeL(sb.calls);
  sb.L = globalThis.L;
  const names = Object.keys(sb).filter((k) => !k.startsWith('_'));
  const code = 'const {' + names.join(',') + '} = __env;\n' + body;
  const ret = '\n;return {' +
    'searchFramesOfSpot, frameGalleryDebug, coverageDebugState, jumpToFrameHitAt,' +
    'frameGalleryClear, frameGalleryHitsRaw, videoContextDebug, frameThumbUrl,' +
    'setProbe, map, projectSelect,' +
    // 逐点帧号那一节：loadedTracks 用来登记一条带 point_frames 的合并航迹，
    // attachPointFrames / frameLineOf 是被测的消费方本身。
    'loadedTracks, attachPointFrames, frameLineOf' +
    '};';
  let threw = null, api = null;
  try {
    api = new Function('__env', code + ret)(sb);
  } catch (e) { threw = e }
  delete globalThis.L;
  return { threw, api, sandbox: sb };
}

// ============================================================

console.log('=== 1) 页面脚本能跑完 ===');
const r = run();
chk(!r.threw, '顶层脚本执行不抛异常',
  r.threw ? r.threw.constructor.name + ': ' + r.threw.message : '');
if (!r.api) { console.log('\n结果: 有失败项'); return 1; }
const { api, sandbox } = r;

console.log('\n=== 2) 没有选点时点按钮 -> 提示而不是发请求 ===');
api.projectSelect.value = 'P1';
// searchFramesOfSpot 是 async，但"没选点"这条分支在 await 之前就 return
api.searchFramesOfSpot();
await tick();
chk(!sandbox.calls.fetchUrls.some((u) => /coverage\/frames/.test(u)),
  '没选点时不去请求接口');
chk(api.frameGalleryDebug().cards === 0, '图墙里没有卡片');

console.log('\n=== 3) 合成一次检索结果，像用户一样点按钮 ===');
const FAKE = {
  ok: true, total: 3, returned: 3, preroll_seconds: 3,
  hits: [
    { srt: 'A.srt', video_path: 'X\\A.MP4', video_name: 'DJI_A_0001_V',
      folder_index: 0, relative_path: 'DJI_A_0001_V.MP4', frame: 120, target_seconds: 12.0,
      start_seconds: 9.0, ground_m_per_px: 0.011, can_resolve_cm: 1.1, frames: 300,
      passes: 3, alt_m: 31.0, pitch_deg: -90.0, yaw_deg: 0.0, focal_mm: 24.0,
      zoomed: false, stream: 'visible' },
    { srt: 'B.srt', video_path: 'X\\B.MP4', video_name: 'DJI_B_0001_V',
      folder_index: 1, relative_path: 'DJI_B_0001_V.MP4', frame: 450, target_seconds: 45.0,
      start_seconds: 42.0, ground_m_per_px: 0.038, can_resolve_cm: 3.8, frames: 80,
      passes: 1, alt_m: 61.0, pitch_deg: -52.6, yaw_deg: 15.0, focal_mm: 24.0,
      zoomed: false, stream: 'visible' },
    { srt: 'C.srt', video_path: 'X\\C.MP4', video_name: 'DJI_C_0001_T',
      folder_index: 0, relative_path: 'DJI_C_0001_T.MP4', frame: 60, target_seconds: 2.0,
      start_seconds: 0.0, ground_m_per_px: 0.090, can_resolve_cm: 9.0, frames: 12,
      passes: 1, alt_m: 70.0, pitch_deg: -40.0, yaw_deg: 0.0, focal_mm: 24.0,
      zoomed: false, stream: 'thermal' },
  ],
  skipped: [{ srt: 'D.srt', why: 'no coverage grid built yet' }],
};
sandbox._setFetch(() => Promise.resolve({
  ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(FAKE)),
}));

// 像用户那样先在地图上选一个点
api.setProbe({ lat: 23.047131, lng: 114.104236 }, 'map click', '');
chk(api.coverageDebugState().probe !== null, '选点已生效',
  JSON.stringify(api.coverageDebugState().probe));

api.searchFramesOfSpot();
for (let i = 0; i < 8; i++) await tick();

const dbg = api.frameGalleryDebug();
// 调试：把探针看到的原始信息打出来（桩和真实 DOM 不一致时靠它定位）
if (process.env.DBG) {
  console.log('    [dbg]', JSON.stringify({
    visible: dbg.visible, hits: dbg.hits, cards: dbg.cards, _dbg: dbg._dbg,
    boxChildren: (sandbox.els.get('frameGallery') || {}).children
      ? sandbox.els.get('frameGallery').children.map((c) => c.id || c.className || c.tagName) : null,
    gridInEls: !!sandbox.els.get('frameGrid'),
    gridParent: sandbox.els.get('frameGrid') ? (sandbox.els.get('frameGrid').parentElement || {}).id : null,
    gridKids: sandbox.els.get('frameGrid')
      ? sandbox.els.get('frameGrid').children.map((c) => c.className) : null,
  }, null, 0));
}
chk(dbg.visible, '图墙已打开');
chk(dbg.hits === 3, '拿到 3 条命中', String(dbg.hits));
chk(dbg.cards === 3, '渲染出 3 张卡', String(dbg.cards));
chk(/Frames of this spot/.test(dbg.title), '标题正确', dbg.title);
// 桩里 innerHTML 的空白处理跟真实 DOM 不同（<b> 会被切开），所以断言前去掉所有空白
const subFlat = String(dbg.sub).replace(/\s+/g, '');
chk(/across3flight/i.test(subFlat), '统计里写着 3 个架次', subFlat.slice(0, 70));
// 排序依据必须写清楚，而且是**新**的依据。用户 2026-10-13 提了两版：
//   ① 「目标点至少要在这个红框区域内，就给优先推荐，
//      另一个推荐的是'变焦且镜头覆盖'」
//   ② 「如果有大量帧包含目标点，那么优先跳转的应该是
//      '目标点最贴近画面中心、或者稍微更靠近的位置'」
// 所以现在第一位是**离中心最近**的帧，不再是"最清的在前"。
chk(/Closest to the centre first/.test(body),
  '说明了排序依据（最贴近画面中心的优先）');
chk(/centred/.test(body) && /zoomed &amp; covering|zoomed & covering/.test(body),
  '两类推荐都在文案里（居中 / 变焦且覆盖）');
// 去掉注释行再判"有没有 best first" —— 注释里会提到它是为了说明"不这么写了"
// （我第一版没去注释，断言被自己的注释挂掉）。
chk(!/best first/.test(body.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')),
  '不再写 best first（那会让人以为第一张就是最清晰的）');
// 副标题开头是当前档位名（Different angles / Every pass / Clearest only），
// 档位下拉在标题行里 —— 这是"给个检索选项"那个需求的界面落点
chk(/Differentangles|Everypass|Clearestonly/i.test(subFlat),
  '副标题写明了当前检索档位', subFlat.slice(0, 30));

console.log('\n=== 4) 缩略图 URL 必须带对 folder_index / path / t ===');
const thumbs = dbg.thumbs;
chk(thumbs.length === 3, '三张都有缩略图地址', String(thumbs.length));
const u0 = decodeURIComponent(thumbs[0] || '');
chk(/name=P1/.test(u0), '带项目名', '');
chk(/folder_index=0/.test(u0), '第 1 张 folder_index=0');
chk(/path=DJI_A_0001_V\.MP4/.test(u0), '第 1 张指向 A 视频');
chk(/t=12\.000/.test(u0), '第 1 张时间 = 12.000s（与 target_seconds 一致）');
const u1 = decodeURIComponent(thumbs[1] || '');
chk(/folder_index=1/.test(u1), '第 2 张 folder_index=1（跨架次）');
chk(/t=45\.000/.test(u1), '第 2 张时间 = 45.000s');

console.log('\n=== 5) 卡片文案 ===');
const t0 = dbg.titles[0] || '';
chk(/from 0:09/.test(t0) || /from 00:09/.test(t0), '提示里写了起播时刻', t0);
chk(/pause at 0:12/.test(t0) || /pause at 00:12/.test(t0), '提示里写了暂停时刻', t0);

console.log('\n=== 5b) 卡片上的数字不能带精度尾巴 ===');
{
  // 曾经出现过 `pitch -29.299999237060547°` —— SRT 是一位小数（-29.3），
  // 但存进 .npz 时过了 float32，后端直接吐原始值就把尾巴带到界面上了。
  // 这里用"带 float32 尾巴"的假数据喂进去，验前端会不会把它露出来。
  const TAIL = {
    ok: true, total: 1, returned: 1, preroll_seconds: 3,
    hits: [{
      srt: 'T.srt', video_path: 'X\\T.MP4', video_name: 'DJI_T_0001_V',
      folder_index: 0, relative_path: 'DJI_T_0001_V.MP4', frame: 10,
      target_seconds: 1.0, start_seconds: 0.0,
      ground_m_per_px: 0.029299999237060547,
      can_resolve_cm: 2.9299999237060547,
      frames: 1, passes: 1,
      alt_m: 73.5, pitch_deg: -29.299999237060547,
      yaw_deg: -162.60000610351562, focal_mm: 24.0,
      zoomed: false, stream: 'visible',
    }],
    skipped: [],
  };
  sandbox._setFetch(() => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(TAIL)),
  }));
  api.setProbe({ lat: 23.0, lng: 114.0 }, 'map click', '');
  api.searchFramesOfSpot();
  for (let i = 0; i < 8; i++) await tick();
  const dd = api.frameGalleryDebug();
  const all = [dd.sub, ...dd.titles].join(' | ');
  // 前端**应该**自己把显示值格式化（后端也会 round，但不能只靠后端）
  const tail = all.match(/\d+\.\d{4,}/);
  chk(!tail, '卡片文字里没有超长小数', tail ? tail[0] : '无');

  // 这一段把命中列表换成了假的，后面的断言还指望原来的 3 条 —— 恢复回去
  sandbox._setFetch(() => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(FAKE)),
  }));
  api.setProbe({ lat: 23.047131, lng: 114.104236 }, 'map click', '');
  api.searchFramesOfSpot();
  for (let i = 0; i < 8; i++) await tick();
  chk(api.frameGalleryDebug().hits === 3, '已恢复成原来的 3 条命中',
    String(api.frameGalleryDebug().hits));
}

console.log('\n=== 6) 点图 -> 跳播载荷正确 ===');
chk(api.videoContextDebug() === null, '点之前没有播放上下文');
const h = api.jumpToFrameHitAt(0);
chk(!!h, '取到第 1 条并按它跳播');
chk(h && h.folder_index === 0, 'folder_index 传对', String(h && h.folder_index));
chk(h && h.target_seconds === 12.0, 'target_seconds 传对', String(h && h.target_seconds));
chk(h && h.start_seconds === 9.0, 'start_seconds = 目标 − 3', String(h && h.start_seconds));
{
  // 读页面真实的 clip（不是另开的记录通道）—— 这才是"到底开了哪个"的真相
  const v = api.videoContextDebug();
  chk(!!v, '真的开了视频（clip 已建立）');
  chk(v && v.folderIndex === 0, '开的架次对', v ? String(v.folderIndex) : '');
  chk(v && v.path === 'DJI_A_0001_V.MP4', '开的视频文件对', v ? v.path : '');
  chk(v && v.videoStart === 12.0,
    '起播/定位时刻 = 12.0（有 3 秒余量时用 target；即从 9.0 起播）',
    v ? String(v.videoStart) : '');
  chk(v && v.photoPauseAt === 12.0, '到点暂停 = 12.0（即 target）',
    v ? String(v.photoPauseAt) : '');
  chk(v && v.pauseHasLeadIn === true, '标记"有余量"，走倒计时那条路',
    v ? String(v.pauseHasLeadIn) : '');
}

console.log('\n=== 7) 「到点自动暂停」的机制确实接上了 ===');
// 历史：曾经无条件设 photo_pause_at=target（"只要有目标时刻就一定要停"）。
// 但用户 2026-10-13 报了一个反例：命中帧就在视频**开头**（t=0.0s）时，
// 起播点被夹到 0、暂停点也是 0，`currentTime >= 0-0.02` 一开播就成立 ——
// 于是瞬间停在第 0 帧，看着像"播放坏了"，而不是"到点自动停了"。
//
// 现在的规则：**余量够才设暂停点**；余量不够就不暂停、让它正常播，
// 并在标题说明原因（那一帧本来就在起播位置上，不会错过）。
chk(/const hasLeadIn=target>=PHOTO_PREROLL_SECONDS/.test(body),
  '按"目标是否够 3 秒余量"决定要不要暂停');
chk(/photo_pause_at:hasLeadIn\?target:0/.test(body),
  '余量足 -> 暂停在目标帧；不足 -> 不暂停');
chk(!/photo_pause_at:target\b/.test(body),
  '没有留下"无条件设暂停点"的老写法（它会让开头帧一开播就停）');
chk(/tickPhotoPause/.test(body) && /videoPlayer\.pause\(\)/.test(body),
  '播放器里有逐帧检查并暂停的实现');
chk(/PHOTO_PREROLL_SECONDS=3/.test(body), '倒数秒数是 3');
// 余量不足时：**直接定位到那一帧、只定位不播放**（用户 2026-10-13 定：
// 「那就让它在这种情况下直接跳转到对应的帧好了，不需要再来 3 秒倒计时」）。
// 所以要断言"只定位不播放"这条路被走到，而不是"播下去"。
chk(/openVideoFromPopup\(encoded,hasLeadIn\)/.test(body),
  '余量不足时走「只定位不播放」（autoPlay=false）');
chk(/Positioned \$\{h\.video_name\} at/.test(body),
  '余量不足时标题说明"已定位到该帧、按播放继续"');
// setPhotoCountdownTarget 必须能收到 hasLeadIn 并据此清掉暂停点
chk(/function setPhotoCountdownTarget\(photoAtAbs,bucket,hasLeadIn\)/.test(body),
  'setPhotoCountdownTarget 接受 hasLeadIn');
chk(/hasLeadIn===false[\s\S]{0,200}photoPauseAt=null/.test(body),
  'hasLeadIn=false 时清掉暂停点（不暂停）');
chk(/setPhotoCountdownTarget\(Number\(st\.data\.photo_pause_at\|\|0\)[\s\S]{0,80}pause_has_lead_in\)/.test(body),
  'startClip 把 pause_has_lead_in 透传下去');

console.log('\n=== 8) 清空选点时图墙一起收掉 ===');
{
  const d8 = api.frameGalleryDebug();
  // 用"本轮实际追加过多少张"来判断，而不是去 DOM 里数：
  // 测试桩每次解析 innerHTML 都会造新的子元素实例，
  // 去 DOM 里数会把"桩的问题"误报成"页面重复累积"。
  chk(d8.added === 3, '本轮只追加了 3 张（没有重复累积）', String(d8.added));
  api.frameGalleryClear();
  const d9 = api.frameGalleryDebug();
  chk(d9.hits === 0, '命中清空');
  chk(d9.added === 0, '追加计数归零');
  chk(d9.galleryEmpty, '页面状态已回到「空」（这才是用户看到的）');
}

console.log('\n=== 10) 视频开着也能换选点；换点清掉旧图墙，但不碰播放内容 ===');
{
  // 规则（用户 2026-10-13 定）：
  //   点地图 = 新选点，马上能按新位置搜索；
  //   右侧正在播的视频**不动**；只有点开某一帧才换播放内容。
  //
  // 这里分两层验：
  //   ① 静态：地图点击处理里不再有「视频开着就返回」的分支
  //   ② 行为：换选点会清掉旧图墙，且**不会**自动开视频
  const clickBlock = body.slice(body.indexOf("map.on('click'"),
    body.indexOf("map.on('click'") + 700);
  chk(!/if\s*\(\s*clip\s*\)/.test(clickBlock),
    '地图点击处理里没有「视频开着就拦下」的分支');
  chk(/setProbe\(e\.latlng/.test(clickBlock), '点击照常设置新选点');

  // 再搜一次，让图墙里有东西
  sandbox._setFetch(() => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(FAKE)),
  }));
  api.setProbe({ lat: 23.05, lng: 114.11 }, 'map click', '');
  api.searchFramesOfSpot();
  for (let i = 0; i < 8; i++) await tick();
  // 不断言"卡片数"：测试桩每次解析 innerHTML 都会造新的子元素实例，
  // 二次渲染后 querySelector 拿到的那份可能不是装了卡的那份。
  // 「能渲染出 3 张卡」已在第 3 节验过，这里只验本节真正要证的：
  // 换点会清掉旧图墙，但不动播放内容。
  chk(api.frameGalleryDebug().hits === 3, '新位置重新搜到了 3 条命中',
    String(api.frameGalleryDebug().hits));

  // 换一个新选点：图墙应被清掉，但没有换掉播放内容
  const beforeCtx = api.videoContextDebug();
  api.setProbe({ lat: 23.06, lng: 114.12 }, 'map click', '');
  const d3 = api.frameGalleryDebug();
  chk(d3.hits === 0 && d3.cards === 0, '换选点后旧图墙被清掉',
    `hits=${d3.hits} cards=${d3.cards}`);
  chk(api.coverageDebugState().probe.lat === 23.06, '选点确实换成了新的',
    JSON.stringify(api.coverageDebugState().probe));
  const afterCtx = api.videoContextDebug();
  chk(JSON.stringify(beforeCtx) === JSON.stringify(afterCtx),
    '换选点没有动播放内容（右侧视频照旧）',
    afterCtx ? afterCtx.path : 'null');
}

console.log('\n=== 11) 只有「点开某一帧」才换播放内容 ===');
{
  sandbox._setFetch(() => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(FAKE)),
  }));
  api.setProbe({ lat: 23.047131, lng: 114.104236 }, 'map click', '');
  api.searchFramesOfSpot();
  for (let i = 0; i < 8; i++) await tick();
  const h = api.jumpToFrameHitAt(1);          // 点第 2 张
  chk(!!h, '点到第 2 张');
  const v = api.videoContextDebug();
  chk(!!v, '这时才真的去开视频（clip 建立了）');
  chk(v && v.folderIndex === 1, '开的是第 2 张所属的架次', v ? String(v.folderIndex) : '');
  chk(v && v.path === 'DJI_B_0001_V.MP4', '开的是对应的视频文件', v ? v.path : '');
  chk(v && v.photoPauseAt === v.videoStart,
    '暂停点 = 定位到的那一刻（往前倒数 3 秒后停）',
    v ? `start=${v.videoStart} pause=${v.photoPauseAt}` : '');
}

console.log('\n=== 12) 余量不足时不留一个「一开播就停」的暂停点 ===');
{
  // 第 3 条 target=2.0、start=0.0，即"这一帧靠近视频开头、倒不出 3 秒"
  const raw = api.frameGalleryHitsRaw();
  const h3 = raw[2];
  chk(!!h3, '取到第 3 条');
  if (h3) {
    chk(h3.start_seconds === 0, '起播就是 0（没有可倒退的余量）',
      String(h3.start_seconds));
    chk(h3.target_seconds > 0, '目标时刻 > 0', String(h3.target_seconds));
    api.jumpToFrameHitAt(2);
    const v3 = api.videoContextDebug();
    chk(!!v3, '点它也会去开视频');
    // 用户 2026-10-13 报的 bug：命中帧在视频开头时，暂停点被设成 0，
    // 而 `currentTime(0) >= 0 - 0.02` 一开播就成立 —— 瞬间停住，
    // 看着像"播放坏了"而不是"到点自动停了"。
    // 现在：余量不足就**不设暂停点**，并且**只定位不播放**（autoPlay=false），
    // 直接把画面停在那一帧上、没有倒计时。
    chk(v3 && v3.photoPauseAt === 0,
      '余量不足时不给暂停点（0 = 不暂停，不会一开播就停）',
      v3 ? String(v3.photoPauseAt) : '');
    chk(v3 && v3.videoStart === 2.0,
      '直接定位到目标帧（2.0s），不再往前倒 3 秒', v3 ? String(v3.videoStart) : '');
    chk(v3 && v3.autoPlay === false, '只定位不播放（停在那一帧、无倒计时）',
      v3 ? String(v3.autoPlay) : '');
    chk(v3 && v3.pauseHasLeadIn === false, '并标记"没有余量"，供界面说明原因',
      v3 ? String(v3.pauseHasLeadIn) : '');
  }
}

console.log('\n=== 13) 0 命中时要讲清原因，而不是空白 ===');
const EMPTY = { ok: true, total: 0, returned: 0, preroll_seconds: 3, hits: [],
  skipped: [{ srt: 'E.srt', why: 'no coverage grid built yet' }] };
sandbox._setFetch(() => Promise.resolve({
  ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(EMPTY)),
}));
api.setProbe({ lat: 23.0, lng: 114.0 }, 'map click', '');
api.searchFramesOfSpot();
for (let i = 0; i < 8; i++) await tick();
const d2 = api.frameGalleryDebug();
chk(d2.hits === 0, '没有命中');
const sub2 = String(d2.sub).replace(/\s+/g, '');
chk(/Noframeinthisproject/.test(sub2), '明确说没有覆盖', sub2.slice(0, 50));
chk(/Build/.test(d2.sub), '提示要去 Build 建网格');

console.log('\n=== 14) 逐点帧号：命中挂帧号 / 卡片列出三路 / 跳转按帧号定位 ===');
{
  // 数据形状照抄合并航迹的 properties（point_times + point_frames{路->逐点数组}）。
  // 帧号是**推不出来**的（三路帧率不同还各有丢帧），所以只能查表。
  const TRACK = {
    coords: [[114.10, 23.04, 30], [114.11, 23.05, 30], [114.12, 23.06, 30]],
    times: [0, 30, 60],
    heights: [30, 30, 30],
    fileInfo: { relative_path: 'DJI_Z_0001.geojson', folder_index: 0 },
    feature: null, layer: null, color: '#000', name: 'DJI_Z_0001.geojson',
    video: 'DJI_Z_0001_V.MP4',
    videos: { S: 'DJI_Z_0001_S.MP4', T: 'DJI_Z_0001_T.MP4', V: 'DJI_Z_0001_V.MP4' },
    streams: ['S', 'T', 'V'],
    // 同一时刻三路帧号：V 18297 / S 18282 / T 18433（实测差 181 帧）
    pointFrames: { V: [0, 10, 18297], S: [0, 9, 18282], T: [0, 12, 18433] },
    referenceStream: 'V',
    videoEnd: 60,
  };
  api.loadedTracks.push(TRACK);
  const FK = {
    ok: true, total: 3, returned: 3, preroll_seconds: 3,
    hits: [
      { srt: 'Z_V.srt', video_path: 'X\\DJI_Z_0001_V.MP4', video_name: 'DJI_Z_0001_V',
        folder_index: 0, relative_path: 'DJI_Z_0001_V.MP4', frame: 120,
        // 命中自带时刻 59.9、帧号所在时刻 60.0 —— 特意错开，才能验出定位用的是后者
        target_seconds: 59.9, player_seek_seconds: 59.9, start_seconds: 56.9,
        ground_m_per_px: 0.011, can_resolve_cm: 1.1, frames: 300, passes: 3,
        alt_m: 31.0, pitch_deg: -90.0, yaw_deg: 0.0, focal_mm: 24.0,
        zoomed: false, stream: 'visible' },
      { srt: 'Z_T.srt', video_path: 'X\\DJI_Z_0001_T.MP4', video_name: 'DJI_Z_0001_T',
        folder_index: 0, relative_path: 'DJI_Z_0001_T.MP4', frame: 130,
        target_seconds: 59.9, player_seek_seconds: 59.9, start_seconds: 56.9,
        ground_m_per_px: 0.05, can_resolve_cm: 5.0, frames: 90, passes: 1,
        alt_m: 31.0, pitch_deg: -90.0, yaw_deg: 0.0, focal_mm: 24.0,
        zoomed: false, stream: 'thermal' },
      { srt: 'A.srt', video_path: 'X\\DJI_A_0001_V.MP4', video_name: 'DJI_A_0001_V',
        folder_index: 1, relative_path: 'DJI_A_0001_V.MP4', frame: 360,
        target_seconds: 12.0, player_seek_seconds: 12.0, start_seconds: 9.0,
        ground_m_per_px: 0.02, can_resolve_cm: 9.0, frames: 80, passes: 1,
        alt_m: 40.0, pitch_deg: -60.0, yaw_deg: 0.0, focal_mm: 24.0,
        zoomed: false, stream: 'visible' },
    ],
    skipped: [],
  };
  sandbox._setFetch(() => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(FK)),
  }));
  api.setProbe({ lat: 23.05, lng: 114.11 }, 'map click', '');
  api.searchFramesOfSpot();
  for (let i = 0; i < 8; i++) await tick();
  const d = api.frameGalleryDebug();
  chk(d.hits === 3, '拿到 3 条命中', String(d.hits));
  // 本轮**新追加**的那三张卡：桩里卡片是 appendChild 进网格的、网格的 innerHTML
  // 一直是空的（页面用 `grid.innerHTML` 判"要不要清"，在桩里永远判成空），
  // 所以桩里的卡片会**累积** —— 和前几节一样，只看最后 added 张，不数全部。
  const tail = d.frames.slice(-d.added);
  const tailTitles = d.titles.slice(-d.added);
  chk(d.added === 3 && tail.length === 3, '本轮追加了 3 张卡', `added=${d.added}`);
  chk(d.frameData[0] && d.frameData[0].frame === 18297 && d.frameData[0].stream === 'V',
    'V 路命中挂上 V 自己的帧号', JSON.stringify(d.frameData[0]));
  chk(d.frameData[1] && d.frameData[1].frame === 18433 && d.frameData[1].stream === 'T',
    'T 路命中挂的是 T 自己的帧号（不是 V 的 18297）', JSON.stringify(d.frameData[1]));
  chk(d.frameData[1] && d.frameData[1].all && d.frameData[1].all.V === 18297
      && d.frameData[1].all.S === 18282 && d.frameData[1].all.T === 18433,
    '同一时刻三路对照一起带上', JSON.stringify(d.frameData[1] && d.frameData[1].all));
  chk(tail[0] === 'frame V 18297 · S 18282 · T 18433',
    '卡片上真的渲染出三路帧号（V/S/T 顺序固定）', tail[0]);
  chk(tail[1] === 'frame V 18297 · S 18282 · T 18433',
    'T 路那张卡也列出同一时刻三路帧号 —— 用户一眼看出差多少帧', tail[1]);
  chk(tail[2] === '', '对不上号的命中不会多出那一行（优雅退化）',
    JSON.stringify(tail[2]));
  chk(d.frameData[2] && d.frameData[2].frame === null && d.frameData[2].all === null,
    '查不到帧号的命中身上没有帧号值', JSON.stringify(d.frameData[2]));

  // 跳转：有帧号时定位到"帧号所在那一刻"（60.0），不是命中自带的 59.9
  api.jumpToFrameHitAt(0);
  const v0 = api.videoContextDebug();
  chk(v0 && v0.frameNo === 18297, '跳播载荷里带着精确帧号（V 路）', String(v0 && v0.frameNo));
  chk(v0 && v0.frameStream === 'V', '并标明是哪一路 —— 不会被拿去 seek 别的路',
    String(v0 && v0.frameStream));
  chk(v0 && Math.abs(v0.videoStart - 60.0) < 1e-9,
    '定位到"帧号所在那一刻"（60.0，而不是命中自带的 59.9）',
    String(v0 && v0.videoStart));
  // T 路：必须用 T 自己的帧号
  api.jumpToFrameHitAt(1);
  const v1 = api.videoContextDebug();
  chk(v1 && v1.frameNo === 18433, 'T 路跳转用的是 T 自己的帧号 18433',
    String(v1 && v1.frameNo));
  chk(v1 && v1.path === 'DJI_Z_0001_T.MP4', '开的是 T 路的视频文件', String(v1 && v1.path));
  chk(v1 && v1.frameStream === 'T', 'T 路标注为 T', String(v1 && v1.frameStream));

  // 退化：没有帧号的那条 -> 时刻与载荷完全按老行为
  api.jumpToFrameHitAt(2);
  const v2 = api.videoContextDebug();
  chk(v2 && v2.frameNo === null, '没有帧号的命中，载荷里没有帧号', String(v2 && v2.frameNo));
  chk(v2 && v2.videoStart === 12.0 && v2.photoPauseAt === 12.0,
    '没有帧号时定位时刻仍是 target_seconds（与改动前一致）',
    v2 ? `start=${v2.videoStart} pause=${v2.photoPauseAt}` : '');
  const t2 = tailTitles[2] || '';
  chk(/from 0+:09/.test(t2) && /pause at 0+:12/.test(t2),
    '卡片提示仍是原来的措辞（起播 0:09 / 停在 0:12）', t2);
  api.loadedTracks.pop();
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
return ok ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch((e) => { console.error('测试本身出错:', e); process.exit(1) });

