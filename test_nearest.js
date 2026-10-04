const fs = require('fs');
const path = require('path');

const HTML = '<仓库根>\\Code\\project_geojson_preview.html';
const DIR = '<仓库根>\\Data\\DJI_202609240950_001';

const html = fs.readFileSync(HTML, 'utf8');

// 从 HTML 里抽出真实源码：函数按花括号配对，常量块按锚点区间
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

const helpers = [extractFn('formatTime'), extractFn('videoPathFromGeojson')].join('\n');
const searchBlock = extractBetween('// 同一位置可能有多路视频', 'async function searchNearby(){');
const src = helpers + '\n' + searchBlock;

// Leaflet 最小替身：latLng + haversine 距离（与 Leaflet 同算法）
const L = { latLng: (lat, lng) => ({ lat, lng }) };
const R = 6371000, rad = d => d * Math.PI / 180;
const map = {
  distance(a, b) {
    const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
};

// 用真实 GeoJSON，按页面 addGeo 的方式登记航迹
const names = fs.readdirSync(DIR).filter(f => /\.geojson$/i.test(f)).sort();

// 高度取法要和页面的 heightsOfTrack() 一致：
// 新生成的 3D 文件不再写 point_heights（它和坐标第三维完全重复，属于冗余），
// 所以旧字段没有时退回从坐标第三维取。
// （以前这里写死 point_heights，于是新格式的文件高度全是 null，
//   那条「高度已从 3D 版本带过来」的断言就再也过不了 —— 是测试落后于页面。）
function heightsOf(f) {
  const p = f.properties || {};
  if (Array.isArray(p.point_heights) && p.point_heights.length) {
    return p.point_heights;
  }
  return (f.geometry.coordinates || []).map(c => (c.length > 2 ? c[2] : null));
}

let loadedTracks = [];
for (const n of names) {
  const g = JSON.parse(fs.readFileSync(path.join(DIR, n), 'utf8'));
  for (const f of g.features) {
    if (f.geometry.type !== 'LineString') continue;
    loadedTracks.push({
      coords: f.geometry.coordinates,
      times: f.properties.point_times || [],
      heights: heightsOf(f),
      fileInfo: { relative_path: n, folder_index: 0 },
      feature: f, color: '#000', name: n,
      video: f.properties.video || '',
      videoEnd: Number(f.properties.video_end || 0)
    });
  }
}

const api = new Function('loadedTracks', 'map', 'L', src +
  '\nreturn {nearestPerStream,pickNearestGroup,streamLabelOf,videoPathFromGeojson,formatTime,GROUP_METERS,GROUP_SECONDS,loadedTracksRead:()=>loadedTracks};');
const A = api(loadedTracks, map, L);
const { nearestPerStream, pickNearestGroup, streamLabelOf, videoPathFromGeojson, formatTime } = A;

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

console.log(`载入航迹 ${loadedTracks.length} 条（含各视频流的 2D 与 3D 两份）：`);
for (const t of loadedTracks) console.log('   ', t.fileInfo.relative_path, t.coords.length, '点');

const V = loadedTracks.find(t => /_V\.geojson$/i.test(t.fileInfo.relative_path));
const k = Math.floor(V.coords.length / 2);
const onTrack = { lng: V.coords[k][0], lat: V.coords[k][1] };

console.log('\n=== 1) 按视频流去重：6 份 GeoJSON 应合成 3 条候选 ===');
const cands = nearestPerStream(onTrack);
chk(cands.length === 3, '候选数 = 3（V 4K / S 1080p / T 红外）', cands.length);
console.log('    候选：' + cands.map(c => `${streamLabelOf(c.track.fileInfo.relative_path)}(距离${c.distance.toFixed(2)}m, ${formatTime(c.time)})`).join('  '));
chk(cands.every(c => !/\.3d\.geojson$/i.test(c.track.fileInfo.relative_path)), '3D 版本已被去重掉');
chk(cands.every((c, i) => i === 0 || c.distance >= cands[i - 1].distance), '候选按距离升序');

console.log('\n=== 2) 命中点必须真的落在轨迹上，距离≈0 ===');
chk(cands[0].distance < 0.05, '最近距离 ≈ 0 m', cands[0].distance.toFixed(4) + ' m');
const hc = cands[0].track.coords[cands[0].index];
chk(hc[0] === onTrack.lng && hc[1] === onTrack.lat, '返回的轨迹点坐标与目标一致');
chk(Number.isFinite(cands[0].time) && cands[0].time >= 0 && cands[0].time <= cands[0].track.videoEnd + 1,
  '视频时间在 [0, 视频总长] 区间内', `${cands[0].time}s / 共${cands[0].track.videoEnd}s`);

console.log('\n=== 3) 分组：主视频应为可见光，其余作为备选 ===');
const grp = pickNearestGroup(onTrack);
chk(grp !== null, '有结果');
chk(/_(V)\.geojson$/i.test(grp.primary.track.fileInfo.relative_path),
  'primary 是可见光 _V （修复前会命中列表里第一条 S.3d）', grp.primary.track.fileInfo.relative_path);
chk(streamLabelOf(grp.primary.track.fileInfo.relative_path) === '可见光 3840×2160',
  '主视频标为“可见光 3840×2160”');
chk(streamLabelOf('DJI_x_S.geojson') === '可见光 1920×1080', '_S 标为“可见光 1920×1080”');
chk(streamLabelOf('DJI_x_T.geojson') === '热成像 1280×1024',
  '_T 标为“热成像 1280×1024”（实测尺寸，不是 640×512 也不是 540p）');
chk(grp.others.length === 2, '另外 2 路作为备选', grp.others.map(o => streamLabelOf(o.track.fileInfo.relative_path)).join('/'));
chk(grp.others.every(o => Math.abs(o.time - grp.primary.time) <= A.GROUP_SECONDS), '备选与主视频时间差在阈值内');
chk(grp.others.every(o => o.distance <= grp.primary.distance + A.GROUP_METERS), '备选与主视频距离差在阈值内');

console.log('\n=== 4) 三路视频给出的时间应基本一致（同一次经过）===');
for (const c of [grp.primary, ...grp.others]) {
  console.log(`    ${streamLabelOf(c.track.fileInfo.relative_path).padEnd(4)} ${c.track.fileInfo.relative_path.padEnd(38)} ${formatTime(c.time)}  距离 ${c.distance.toFixed(2)} m  高度 ${c.height ?? '-'}`);
}
const times = [grp.primary, ...grp.others].map(c => c.time);
chk(Math.max(...times) - Math.min(...times) < A.GROUP_SECONDS, '三路时间跨度小于阈值', (Math.max(...times) - Math.min(...times)).toFixed(2) + ' s');
chk(grp.primary.height !== null, '高度已从 3D 版本带过来', grp.primary.height);

console.log('\n=== 5) 远处目标（北京）===');
const far = pickNearestGroup({ lng: 116.4, lat: 39.9 });
chk(far.primary.distance > 1e6, '距离 > 1000 km', (far.primary.distance / 1000).toFixed(0) + ' km');
chk(far.primary.distance > 3000, '会触发“距离较远”提示');

console.log('\n=== 6) 沿轨迹取多个点，检索结果应始终贴在该轨迹上 ===');
let maxOff = 0, mismatched = 0;
for (let s = 0; s < 20; s++) {
  const idx = Math.floor(V.coords.length * s / 20);
  const p = { lng: V.coords[idx][0], lat: V.coords[idx][1] };
  const g = pickNearestGroup(p);
  maxOff = Math.max(maxOff, g.primary.distance);
  const pt = g.primary.track.coords[g.primary.index];
  if (pt[0] !== p.lng || pt[1] !== p.lat) mismatched++;
}
chk(maxOff < 0.05, '20 个采样点的最大偏差 ≈ 0 m', maxOff.toFixed(4) + ' m');
chk(mismatched === 0, '全部命中同一坐标点');

console.log('\n=== 7) GeoJSON 路径 -> 视频路径（含 .3d），并验证文件存在 ===');
for (const t of loadedTracks) {
  const v = videoPathFromGeojson(t.fileInfo.relative_path);
  const exists = fs.existsSync(path.join(DIR, v));
  chk(exists, `${t.fileInfo.relative_path.padEnd(38)} -> ${v}`, exists ? '存在' : '不存在！');
}

console.log('\n=== 8) 性能 ===');
const total = loadedTracks.reduce((s, t) => s + t.coords.length, 0);
const t0 = process.hrtime.bigint();
for (let i = 0; i < 20; i++) pickNearestGroup({ lng: onTrack.lng + i * 1e-4, lat: onTrack.lat });
const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 20;
console.log(`  ${loadedTracks.length} 条航迹 / ${total.toLocaleString()} 个点，单次检索 ${ms.toFixed(2)} ms`);
chk(ms < 200, '单次检索 < 200 ms');

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
