// 验证地图跟随：①真的能跟住 ②大部分时间一动不动（不抖）③三种模式行为正确
const fs = require('fs');
const path = require('path');

const HTML = '<仓库根>\\Code\\project_geojson_preview.html';
const DIR = '<仓库根>\\Data\\DJI_202609240950_001';
const html = fs.readFileSync(HTML, 'utf8');

function extractFn(name) {
  const start = html.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('找不到函数 ' + name);
  let depth = 0;
  for (let j = html.indexOf('{', start); j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (depth === 0) return html.slice(start, j + 1); }
  }
  throw new Error('花括号不配对: ' + name);
}
function extractBetween(a, b) {
  const i = html.indexOf(a), j = html.indexOf(b);
  if (i < 0 || j < 0 || j <= i) throw new Error('区间锚点找不到: ' + a);
  return html.slice(i, j);
}

// --- 最小 Leaflet 替身 ---
function Bounds(sw, ne) { this.sw = sw; this.ne = ne; }
Bounds.prototype.isValid = function () { return this.sw.lat <= this.ne.lat && this.sw.lng <= this.ne.lng; };
Bounds.prototype.contains = function (ll) {
  return ll.lat >= this.sw.lat && ll.lat <= this.ne.lat && ll.lng >= this.sw.lng && ll.lng <= this.ne.lng;
};
// 与 Leaflet 一致：pad(r) 向外扩张 r 倍跨度，pad(-r) 向内收缩
Bounds.prototype.pad = function (r) {
  const dLat = (this.ne.lat - this.sw.lat) * r, dLng = (this.ne.lng - this.sw.lng) * r;
  return new Bounds({ lat: this.sw.lat - dLat, lng: this.sw.lng - dLng },
                    { lat: this.ne.lat + dLat, lng: this.ne.lng + dLng });
};
Bounds.prototype.getSouthWest = function () { return this.sw; };
Bounds.prototype.getNorthEast = function () { return this.ne; };

const L = {
  latLng: (lat, lng) => ({ lat, lng }),
  latLngBounds: (arr) => {
    let sw = { lat: Infinity, lng: Infinity }, ne = { lat: -Infinity, lng: -Infinity };
    for (const ll of arr) {
      sw.lat = Math.min(sw.lat, ll.lat); sw.lng = Math.min(sw.lng, ll.lng);
      ne.lat = Math.max(ne.lat, ll.lat); ne.lng = Math.max(ne.lng, ll.lng);
    }
    return new Bounds(sw, ne);
  }
};

let viewport, calls, fakeNow;
function makeMap() {
  return {
    getBounds: () => viewport,
    getSize: () => ({ x: 1000, y: 700 }),
    latLngToContainerPoint: (ll) => ({
      x: (ll.lng - viewport.sw.lng) / (viewport.ne.lng - viewport.sw.lng) * 1000,
      y: (viewport.ne.lat - ll.lat) / (viewport.ne.lat - viewport.sw.lat) * 700
    }),
    // 真实 fitBounds 会带 padding，结果视野比 bounds 略大，这里按 15% 模拟
    fitBounds: (b) => { calls.fit.push(b); viewport = b.pad(0.15); },
    panTo: (ll) => {
      calls.pan.push(ll);
      const hLat = (viewport.ne.lat - viewport.sw.lat) / 2, hLng = (viewport.ne.lng - viewport.sw.lng) / 2;
      viewport = new Bounds({ lat: ll.lat - hLat, lng: ll.lng - hLng }, { lat: ll.lat + hLat, lng: ll.lng + hLng });
    }
  };
}

const consts = extractBetween('const FOLLOW_LOOKAHEAD=', '// 取一段航迹上的点');
// 缩放上限常量声明在 let map=null 之前，不在上面那段区间里，要单独抽出来
const zoomConsts = extractBetween('const TRACK_FIT_MAX_ZOOM=', 'let map=null;');
const src = zoomConsts + '\n' + consts + '\n' + extractFn('trackLatLngs') + '\n' + extractFn('followViewport');
const idxSrc = extractFn('indexAtTime');

const build = (map, clip, probe, mode) => {
  const sel = { value: mode };
  const f = new Function('L', 'map', 'clip', 'probeLatLng', 'followModeSelect', 'indexAtTime', 'Date',
    src + '\n' + idxSrc + '\nreturn {followViewport,trackLatLngs};');
  return { api: f(L, map, clip, probe, sel, idxAtTimeRef, { now: () => fakeNow }), sel };
};

// 真实航迹
const g = JSON.parse(fs.readFileSync(path.join(DIR, 'DJI_20260924095258_0001_V.geojson'), 'utf8'));
const feat = g.features[0];
const coords = feat.geometry.coordinates;
const times = feat.properties.point_times;

let idxAtTimeRef;
{ // indexAtTime 用真实源码
  const f = new Function(extractFn('indexAtTime') + '\nreturn indexAtTime;');
  idxAtTimeRef = f();
}

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

// 从 t=900 秒开始，模拟 90 秒播放
const startIdx = idxAtTimeRef(times, 900);
const probe = { lat: coords[startIdx][1] + 0.002, lng: coords[startIdx][0] + 0.002 };

console.log('=== 1) fit 模式：模拟 90 秒播放，逐 tick 调用 ===');
{
  calls = { fit: [], pan: [] };
  fakeNow = 1000000;
  const m = makeMap();
  // 初始视野：只看得到起点附近（模拟检索后的紧视野）
  viewport = new Bounds({ lat: coords[startIdx][1] - 0.0008, lng: coords[startIdx][0] - 0.0008 },
                        { lat: coords[startIdx][1] + 0.0008, lng: coords[startIdx][0] + 0.0008 });

  const clip = { track: { coords, times } };
  const api = build(m, clip, probe, 'fit').api;

  let tick = 0, outOfView = 0, total = 0;
  for (let ct = 0; ct <= 90; ct += 0.25) {
    tick++;
    fakeNow += 250;
    const trackSeconds = 900 + ct;
    const index = idxAtTimeRef(times, trackSeconds);
    clip.index = index;
    clip.trackSeconds = trackSeconds;
    clip.droneLatLng = { lat: coords[index][1], lng: coords[index][0] };
    api.followViewport();

    total++;
    if (!viewport.contains(clip.droneLatLng)) outOfView++;
  }

  console.log(`  共 ${total} 次 tick（90 秒），fitBounds 只调用了 ${calls.fit.length} 次，panTo ${calls.pan.length} 次`);
  chk(calls.pan.length === 0, 'fit 模式不用 panTo');
  chk(calls.fit.length >= 1, '至少调整过一次（初始视野太紧）');
  chk(calls.fit.length <= 6, '调整次数很少（不抖）', `${calls.fit.length} 次 / ${total} tick`);
  chk(outOfView <= 4, '飞机几乎始终在视野内', `出框 ${outOfView} / ${total} tick`);
  console.log(`  平均每 ${(90 / calls.fit.length).toFixed(1)} 秒才调整一次地图`);
}

console.log('\n=== 2) 节流：连续调用不会重复调整 ===');
{
  calls = { fit: [], pan: [] };
  fakeNow = 2000000;
  const m = makeMap();
  viewport = new Bounds({ lat: 23.0, lng: 114.0 }, { lat: 23.001, lng: 114.001 });
  const clip = { track: { coords, times }, index: startIdx, trackSeconds: 900, droneLatLng: { lat: coords[startIdx][1], lng: coords[startIdx][0] } };
  const api = build(m, clip, probe, 'fit').api;

  api.followViewport();
  const after1 = calls.fit.length;
  api.followViewport(); api.followViewport(); api.followViewport();
  chk(calls.fit.length === after1, '1.5 秒内重复调用被节流', `${after1} -> ${calls.fit.length}`);

  fakeNow += 1600;
  api.followViewport();
  chk(calls.fit.length === after1, '即使过了节流，装得下也不会再动（视野已够）', `${calls.fit.length}`);
}

console.log('\n=== 3) center 模式：飞机固定在中心 ===');
{
  calls = { fit: [], pan: [] };
  fakeNow = 3000000;
  const m = makeMap();
  viewport = new Bounds({ lat: 23.02, lng: 114.10 }, { lat: 23.04, lng: 114.13 });
  const clip = { track: { coords, times } };
  const api = build(m, clip, probe, 'center').api;
  const cx = (viewport.sw.lat + viewport.ne.lat) / 2, cy = (viewport.sw.lng + viewport.ne.lng) / 2;

  clip.droneLatLng = { lat: cx, lng: cy };
  api.followViewport();
  chk(calls.pan.length === 0, '飞机在中心附近 -> 不平移');

  clip.droneLatLng = { lat: cx + 0.05, lng: cy + 0.05 };
  api.followViewport();
  chk(calls.pan.length === 1, '飞机偏离中心 -> 平移一次', `${calls.pan.length}`);
  chk(viewport.contains(clip.droneLatLng), '平移后飞机回到视野内');

  const before = { ...viewport.sw };
  api.followViewport();
  chk(calls.fit.length === 0, 'center 模式不改缩放（不调用 fitBounds）');
}

console.log('\n=== 4) off 模式：完全不动 ===');
{
  calls = { fit: [], pan: [] };
  fakeNow = 4000000;
  const m = makeMap();
  viewport = new Bounds({ lat: 23.02, lng: 114.10 }, { lat: 23.04, lng: 114.13 });
  const clip = { track: { coords, times }, index: startIdx, trackSeconds: 900, droneLatLng: { lat: 24.5, lng: 115.5 } };
  const api = build(m, clip, probe, 'off').api;
  api.followViewport(); api.followViewport();
  chk(calls.fit.length === 0 && calls.pan.length === 0, 'off 模式不做任何调整');
}

console.log('\n=== 5) fit 模式圈定的范围是否合理 ===');
{
  calls = { fit: [], pan: [] };
  fakeNow = 5000000;
  const m = makeMap();
  viewport = new Bounds({ lat: 23.0, lng: 114.0 }, { lat: 23.001, lng: 114.001 });
  const clip = { track: { coords, times }, index: startIdx, trackSeconds: 900, droneLatLng: { lat: coords[startIdx][1], lng: coords[startIdx][0] } };
  const api = build(m, clip, probe, 'fit').api;
  api.followViewport();

  const b = calls.fit[0];
  chk(b.contains({ lat: coords[startIdx][1], lng: coords[startIdx][0] }), '包含飞机当前位置');
  chk(b.contains(probe), '包含用户点选的目标点');
  const aheadIdx = idxAtTimeRef(times, 900 + 60);
  chk(b.contains({ lat: coords[aheadIdx][1], lng: coords[aheadIdx][0] }), '包含前方 60 秒航迹的末端');
  const spanM = Math.abs(b.ne.lat - b.sw.lat) * 111000;
  console.log(`  圈定范围约 ${(spanM/1000).toFixed(2)} km（纬度方向），换算缩放级别约 z${Math.round(Math.log2(156543 * Math.cos(23*Math.PI/180) * 700 / spanM))}`);
  chk(spanM > 300 && spanM < 3000, '范围量级合理（几百米到几公里）', `${spanM.toFixed(0)} m`);
}

console.log('\n=== 6) 没有目标点（从轨迹弹窗直接播放）时也不会异常 ===');
{
  calls = { fit: [], pan: [] };
  fakeNow = 6000000;
  const m = makeMap();
  viewport = new Bounds({ lat: 23.0, lng: 114.0 }, { lat: 23.001, lng: 114.001 });
  const clip = { track: { coords, times }, index: startIdx, trackSeconds: 900, droneLatLng: { lat: coords[startIdx][1], lng: coords[startIdx][0] } };
  const api = build(m, clip, null, 'fit').api;
  api.followViewport();
  chk(calls.fit.length === 1, '目标点为空时不报错，只按飞机+前方航迹调整');
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
