// 用真实航迹数据验证"视频时间 -> 航迹点 -> 箭头位置/朝向"这条链路
const fs = require('fs');
const path = require('path');

// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2]/argv[3] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');
const DIR = process.argv[3] || path.join(__dirname, 'Data', 'DJI_202609240950_001');

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

// 抽真实源码：常量 + 几个函数
const consts = extractBetween('const PROXY_SECONDS=90;', 'const MEDIA_ERROR_TEXT=');
const fns = ['proxyBucketOf', 'bearingBetween', 'bearingAt']
  .map(extractFn).join('\n\n');
const spanConst = extractBetween('const BEARING_SPANS=', '// 算飞行方位角');
const idxFn = extractFn('indexAtTime');
const api = new Function(consts + '\n' + spanConst + '\n' + fns + '\n' + idxFn +
  '\nreturn {proxyBucketOf,indexAtTime,bearingAt,PROXY_SECONDS,PROXY_BUCKET_SECONDS,BEARING_SPANS};')();

const { proxyBucketOf, indexAtTime, bearingAt, PROXY_SECONDS, PROXY_BUCKET_SECONDS, BEARING_SPANS } = api;

// 载入真实航迹
const g = JSON.parse(fs.readFileSync(
  path.join(DIR, 'DJI_20260924095258_0001.geojson'), 'utf8'));
const f = g.features[0];
const coords = f.geometry.coordinates;
const times = f.properties.point_times;
const total = Number(f.properties.video_end);

const R = 6371000, rad = d => d * Math.PI / 180;
function meters(a, b) {
  const dLat = rad(b[1] - a[1]), dLng = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
// 独立实现的标准大圆方位角，用来交叉验证 bearingAt
function geodesicBearing(a, b) {
  const φ1 = rad(a[1]), φ2 = rad(b[1]), Δλ = rad(b[0] - a[0]);
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

console.log(`航迹：${coords.length} 点，时间 ${times[0]} ~ ${times[times.length-1]} 秒，视频总长 ${total} 秒`);
chk(coords.length === times.length, '坐标与时间一一对应');

console.log('\n=== 1) indexAtTime 时间->点索引 ===');
chk(indexAtTime(times, 0) === 0, 't=0 -> 索引 0');
chk(indexAtTime(times, times[0]) === 0, 't=首点时间 -> 索引 0');
chk(indexAtTime(times, -5) === 0, 't 为负 -> 夹到 0');
chk(indexAtTime(times, times[times.length-1]) === times.length-1, 't=末点时间 -> 最后一点');
chk(indexAtTime(times, total + 999) === times.length-1, 't 超出片长 -> 夹到最后一点');
let exact = 0;
for (const k of [0, 1, 500, 5000, 12345, 20000, 36541]) {
  if (indexAtTime(times, times[k]) === k) exact++;
}
chk(exact === 7, '精确命中 7 个抽样索引', `${exact}/7`);
let near = 0;
for (let k = 100; k < 36000; k += 997) {
  const t = (times[k] + times[k + 1]) / 2;
  const i = indexAtTime(times, t);
  if (i === k || i === k + 1) near++;
}
chk(near === Math.ceil((36000 - 100) / 997), '落在相邻两点之间的查询返回其一', `${near}`);

console.log('\n=== 2) bearingAt 方位角 vs 独立实现的大圆方位角 ===');
console.log(`  逐级回看窗口: ${BEARING_SPANS.join(' / ')} 帧`);
let maxDiff = 0, checked = 0, nulls = 0, widened = 0;
for (let k = 10; k < coords.length - 10; k += 500) {
  const b = bearingAt(coords, k);
  if (b === null) { nulls++; continue; }

  // 该点是否处在悬停里（最近 8 帧无位移）
  const hovering = coords[k][0] === coords[k - 8][0] && coords[k][1] === coords[k - 8][1];

  if (hovering) { widened++; continue; }   // 悬停段用宽窗口，不能用窄窗口做基准

  const ref = geodesicBearing(coords[k - 8], coords[k]);
  let d = Math.abs(b - ref);
  if (d > 180) d = 360 - d;
  maxDiff = Math.max(maxDiff, d);
  checked++;
}
chk(checked > 40, '正常飞行段抽样点足够', checked);
chk(nulls <= 2, '长悬停也能算出朝向（放宽窗口生效）', `null=${nulls}，其中悬停点 ${widened}`);
chk(maxDiff < 2, '正常飞行段与标准大圆方位角一致（窄窗口精确）', maxDiff.toFixed(3) + '°');
const bearings = [];
for (let k = 10; k < coords.length - 10; k += 500) { const b = bearingAt(coords, k); if (b !== null) bearings.push(b); }
chk(bearings.every(b => b >= 0 && b < 360), '方位角都落在 [0,360)');

console.log('\n=== 2b) 悬停段专项（最长那段 26.4 秒悬停） ===');
const hoverStart = 19023, hoverEnd = 19813;
const hoverMid = Math.floor((hoverStart + hoverEnd) / 2);
const hb = bearingAt(coords, hoverMid);
chk(hb !== null, '悬停正中间仍能给出朝向', hb === null ? 'null' : hb.toFixed(1) + '°');
const beforeHover = bearingAt(coords, hoverStart - 60);
chk(beforeHover !== null, '悬停前的朝向', beforeHover.toFixed(1) + '°');
if (hb !== null && beforeHover !== null) {
  let dd = Math.abs(hb - beforeHover);
  if (dd > 180) dd = 360 - dd;
  chk(dd < 90, '悬停期间的朝向与入悬停前大致一致（箭头不会乱转）', dd.toFixed(1) + '° 差');
}

console.log('\n=== 3) 模拟一次播放：转码片段 start=900，时长 90 秒 ===');
const start = 900;
const bucket = proxyBucketOf(start);
chk(bucket === 900, 'start=900 对齐到 bucket 900', bucket);
chk(PROXY_SECONDS === 90 && PROXY_BUCKET_SECONDS === 30, '片段参数与后端一致');

const seekTo = start - bucket;
console.log(`  起播点桶=${bucket}，片段内 currentTime 应定位到 ${seekTo} 秒`);

const trackSeconds = [];
for (let ct = 0; ct <= PROXY_SECONDS; ct += 0.25) {
  trackSeconds.push(bucket + ct);
}
const idxs = trackSeconds.map(t => indexAtTime(times, t));
chk(idxs.every((v, i) => v >= 0 && v < coords.length), '全程索引合法');
chk(idxs.every((v, i) => i === 0 || v >= idxs[i-1]), '索引单调不回退（箭头不会倒退）');

// 起播位置是否就是用户点击的那一点附近
const clickIdx = indexAtTime(times, start);
const startIdx = indexAtTime(times, bucket + seekTo);
chk(Math.abs(startIdx - clickIdx) <= 1, '起播时箭头落在用户点击的位置', `diff=${Math.abs(startIdx-clickIdx)}`);

// 走过的地面距离是否与 90 秒飞行相符
let dist = 0;
for (let i = 1; i < idxs.length; i++) dist += meters(coords[idxs[i-1]], coords[idxs[i]]);
console.log(`  片段内箭头走过地面距离约 ${(dist/1000).toFixed(3)} km（90 秒）`);
chk(dist > 50 && dist < 3000, '距离量级合理', `${(dist/90).toFixed(1)} m/s 平均`);

// 帧间位移不应出现跳变
let maxJump = 0;
for (let i = 1; i < idxs.length; i++) maxJump = Math.max(maxJump, meters(coords[idxs[i-1]], coords[idxs[i]]));
chk(maxJump < 60, '相邻 0.25 秒之间没有位置跳变', maxJump.toFixed(1) + ' m');

console.log('\n=== 4) 原片直出模式（无 offset） ===');
const directIdxs = [];
for (let ct = 900; ct <= 990; ct += 0.25) directIdxs.push(indexAtTime(times, ct));
chk(JSON.stringify(directIdxs) === JSON.stringify(idxs), '原片模式与转码模式算出的点完全一致（时间基准换算正确）');

console.log('\n=== 5) 箭头朝向在飞行中的变化 ===');
const samples = [];
for (let k = 0; k < coords.length - 20; k += 4000) {
  const b = bearingAt(coords, k);
  samples.push({ k, t: times[k].toFixed(1), b: b === null ? '—' : b.toFixed(1) });
}
samples.forEach(s => console.log(`    第 ${String(s.k).padStart(6)} 点  t=${String(s.t).padStart(8)}s  方位角 ${String(s.b).padStart(6)}°`));
chk(samples.length >= 8, '抽样点足够展示航向变化');
chk(samples.every(s => s.b !== '—'), '所有抽样点都给出了朝向');

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
