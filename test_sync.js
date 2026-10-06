// 直接执行真实的 syncDroneMarker()，验证它每次都能走到最后。
//
// 为什么需要：这个函数在开头有若干 return 分支（找不到航迹、时间数组为空、
// 下标越界、图标不可用……）。一旦中途返回，后面的
// renderTelemetry / syncCrosshair / syncFootprint / followViewport / syncMapPip
// 就全部不执行 —— 表现是「地图上的箭头、准星、视场都不动」，
// 而信息栏却仍有数值（那是 loadTelemetry 单独调的），症状很容易被误判。
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

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

const code = `
let droneIcon=null, crosshairIcon=null, probeIcon=null;
let droneMarker=null, droneBearing=0;
${extractFn('leafletReady')}
${extractFn('ensureMapIcons')}
${extractFn('iconsUsable')}
${extractFn('indexAtTime')}
${extractFn('streamKeyOf')}
${extractFn('trackForClip')}
${extractFn('syncDroneMarker')}
return {syncDroneMarker,ensureMapIcons,iconsUsable,indexAtTime,trackForClip};`;

const build = new Function(
  'L', 'clip', 'map', 'telemetry', 'videoPlayer', 'loadedTracks',
  'renderTelemetry', 'syncCrosshair', 'syncFootprint', 'followViewport', 'syncMapPip',
  'telemetryIndexAt', 'proxyBucketOf', 'bearingAt', 'noteMissingTrack',
  code
);

// ---------- 真实数据 ----------
const gj = JSON.parse(fs.readFileSync(path.join(DIR, 'DJI_20260924095258_0001_V.geojson'), 'utf8'));
const f0 = gj.features[0];
const relPath = 'DJI_20260924095258_0001_V.geojson';

function makeTrack() {
  return {
    coords: f0.geometry.coordinates,
    times: f0.properties.point_times,
    heights: [],
    fileInfo: { relative_path: relPath, folder_index: 0 },
    video: 'DJI_20260924095258_0001_V.MP4',
    videoEnd: Number(f0.properties.video_end || 0),
  };
}

// 简化遥测：每 3 帧一个采样点，和真实接口一致
function makeTelemetry() {
  const t = [], yaw = [], pitch = [], alt = [], focal = [], dzoom = [];
  for (let i = 0; i < f0.properties.point_times.length; i += 3) {
    t.push(f0.properties.point_times[i]);
    yaw.push(41.2 + (i % 90) * 0.1);
    pitch.push(-17.4 - (i % 40) * 0.1);
    alt.push(19.6 + (i % 200) * 0.4);
    focal.push(24);
    dzoom.push(1);
  }
  return { times: t, yaw, pitch, alt, focal, dzoom };
}

function makeL(calls) {
  const layer = (kind) => () => {
    calls[kind] = (calls[kind] || 0) + 1;
    return {
      addTo() { return this }, on() { return this }, setLatLngs() { return this },
      setLatLng() { return this }, getElement() { return null }, remove() {},
      bindTooltip() { return this }, bindPopup() { return this }, bringToBack() { return this },
    };
  };
  return {
    divIcon: () => { calls.divIcon = (calls.divIcon || 0) + 1; return { __icon: true } },
    marker: layer('marker'),
    polyline: layer('polyline'),
    polygon: layer('polygon'),
    latLng: (a, b) => ({ lat: a, lng: b }),
    latLngBounds: (pts) => ({
      pad() { return this },
      getCenter: () => pts[0],
      getSouthWest: () => pts[0],
      getNorthEast: () => pts[pts.length - 1],
      isValid: () => true,
      contains() { return true },
    }),
  };
}

function run(withLeaflet, opts = {}) {
  const calls = { reached: [] };
  const L = withLeaflet ? makeL(calls) : undefined;
  const track = opts.noTrack ? null : makeTrack();
  const loadedTracks = track ? [track] : [];

  const clip = {
    path: 'DJI_20260924095258_0001_V.MP4',
    start: 0,
    useProxy: false,
    track: null,
    droneLatLng: null,
    trackSeconds: null,
    index: -1,
  };

  const map = {};

  const api = build(
    L, clip, map, makeTelemetry(), { currentTime: 60, paused: false }, loadedTracks,
    () => calls.reached.push('renderTelemetry'),
    () => calls.reached.push('syncCrosshair'),
    () => calls.reached.push('syncFootprint'),
    () => calls.reached.push('followViewport'),
    () => calls.reached.push('syncMapPip'),
    () => 0,
    () => 0,
    () => 90,
    () => calls.reached.push('noteMissingTrack')
  );

  let threw = null;
  try { api.syncDroneMarker(60); } catch (e) { threw = e }

  return { calls, threw, api, clip };
}

// ============================================================

console.log('=== 正常路径：航迹已加载、Leaflet 可用 ===');
{
  const r = run(true);
  chk(!r.threw, '不抛异常', r.threw ? r.threw.constructor.name + ': ' + r.threw.message : '');
  chk(r.calls.divIcon === 3, '按需建出三个图标', String(r.calls.divIcon));
  chk((r.calls.marker || 0) >= 1, '建了飞机箭头 marker', String(r.calls.marker || 0));
  chk(r.calls.reached.length === 5, '走到了函数最后（5 个下游调用都执行了）',
    r.calls.reached.join(' -> ') || '（一个都没执行）');
  chk(r.calls.reached.join(',') === 'renderTelemetry,syncCrosshair,syncFootprint,followViewport,syncMapPip',
    '顺序正确');
  chk(r.clip.droneLatLng && Number.isFinite(r.clip.droneLatLng.lat), '记下了飞机位置',
    r.clip.droneLatLng ? `${r.clip.droneLatLng.lat.toFixed(5)},${r.clip.droneLatLng.lng.toFixed(5)}` : 'null');
  chk(r.clip.trackSeconds === 60, '记下了 SRT 时间轴秒数', String(r.clip.trackSeconds));
}

console.log('\n=== 二次调用：不应重复建图标/箭头 ===');
{
  const r = run(true);
  const r2 = run(true);
  chk(r2.calls.divIcon === 3, '每次都是三个图标（不重复创建）', String(r2.calls.divIcon));
  chk(r2.calls.reached.length === 5, '同样走到最后');
}

console.log('\n=== 边界：这些情况下会提前返回（但不能静默无感）===');
{
  const r = run(true, { noTrack: true });
  chk(!r.threw, '没有匹配航迹时不抛异常');
  chk(r.calls.reached.join(',') === 'noteMissingTrack',
    '确实提前返回了，但走了提示分支（不是静默 return）',
    r.calls.reached.join(' -> ') || '（什么都没执行）');
  console.log('     说明：这条路径的表现就是「地图上的东西不动、信息栏却仍有数值」，');
  console.log('           所以要提示 + 自动补加载，不能静默返回。');
}
{
  const r = run(false);
  // L 完全缺失时函数在 L.latLng 那一步就更早抛了 ——
  // 这是记录真实行为：图标兜底防的不是这种情况（没有地图就不会调用它）。
  chk(!!r.threw && /latLng/.test(String(r.threw && r.threw.message)),
    'L 完全缺失时更早抛错（图标兜底不是防这个，实际不会走到）',
    r.threw ? r.threw.message : '没有抛错');
  chk((r.calls.divIcon || 0) === 0, '不会去建图标', String(r.calls.divIcon || 0));
}

console.log('\n=== 关键：找不到航迹时必须提示 + 自动补加载（不能静默返回）===');
{
  const src = extractFn('syncDroneMarker');
  chk(/noteMissingTrack\(\)/.test(src), '找不到航迹时调用 noteMissingTrack()',
    /noteMissingTrack\(\)/.test(src) ? '' : '当前是静默 return');
  chk(!/const track=clip\.track;\s*\n\s*if\(!track\)return;/.test(src),
    '旧的静默 return 已移除');

  chk(/function noteMissingTrack\(\)/.test(html), 'function noteMissingTrack()');
  chk(/function loadTrackForClip\(/.test(html), 'function loadTrackForClip()');

  const note = extractFn('noteMissingTrack');
  chk(/missingTrackPath===want/.test(note), '同一路视频只提示一次（不会每帧刷屏）');
  chk(/show\(/.test(note), '会给出可见提示');
  chk(/geoFiles\.find\(/.test(note), '会在已扫描的文件里找对应 GeoJSON');
  chk(/loadTrackForClip\(f\)/.test(note), '找到就自动补加载');

  const loader = extractFn('loadTrackForClip');
  chk(/addGeo\(/.test(loader), '用轻量的 addGeo 补加载');
  chk(!/loadOne\(/.test(loader),
    '没有用 loadOne —— 它清空所有图层并跳转视野，播放中调用会搅乱地图');
  chk(/fetchGeo\(/.test(loader), '按需向后端取 GeoJSON');
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
