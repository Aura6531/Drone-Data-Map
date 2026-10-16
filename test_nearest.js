const fs = require('fs');
const path = require('path');

// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2]/argv[3] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');
const DIR = process.argv[3] || path.join(__dirname, 'Data', 'DJI_202609240950_001');

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

const helpers = [
  extractFn('formatTime'),
  extractFn('videoPathFromGeojson'),
  extractFn('joinDir'),
  // 反查方向要用：把「任一路视频」对回「那份合并航迹」的两个判据
  extractFn('flightStemOfForMatch'),
  extractFn('trackMatchesPath'),
].join('\n');
const searchBlock = extractBetween('// 同一位置可能有多路视频', 'async function searchNearby(){');

// videoPathFromGeojson 的第三级取值是「加载时登记好的映射表」VIDEO_REL_BY_GEOJSON
// （页面里全页共用，见 addGeo）。这里只抠了单个函数，得把这个模块级常量也补上，
// 否则一走到第三级就 ReferenceError。页面里它是空表起手、由 addGeo 填，
// 所以桩也照这个来（addGeo 在测试里没被抠出来，自然也不会有人填）。
const sandboxConsts = `
const VIDEO_REL_BY_GEOJSON=Object.create(null);
`;
const src = helpers + '\n' + sandboxConsts + searchBlock;

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

// 页面 addGeo 现在登记的字段（合并航迹带 videos / streams / point_frames /
// reference_stream）。这里照抄一份，测试才测得到「按流取帧号」这类新性质。
let loadedTracks = [];
for (const n of names) {
  const g = JSON.parse(fs.readFileSync(path.join(DIR, n), 'utf8'));
  for (const f of g.features) {
    if (f.geometry.type !== 'LineString') continue;
    const p = f.properties || {};
    loadedTracks.push({
      coords: f.geometry.coordinates,
      times: p.point_times || [],
      heights: heightsOf(f),
      fileInfo: { relative_path: n, folder_index: 0 },
      feature: f, color: '#000', name: n,
      video: p.video || '',
      // 新增：一次拍摄合成一份航迹后，三路视频与三路帧号都挂在这一条上
      videos: p.videos || null,
      streams: p.streams || null,
      pointFrames: p.point_frames || null,
      referenceStream: p.reference_stream || null,
      videoEnd: Number(p.video_end || 0)
    });
  }
}

const api = new Function('loadedTracks', 'map', 'L', src +
  '\nreturn {nearestPerStream,pickNearestGroup,streamLabelOf,videoPathFromGeojson,formatTime,GROUP_METERS,GROUP_SECONDS,trackMatchesPath,flightStemOfForMatch,loadedTracksRead:()=>loadedTracks};');
const A = api(loadedTracks, map, L);
const { nearestPerStream, pickNearestGroup, streamLabelOf, videoPathFromGeojson, formatTime,
        trackMatchesPath } = A;

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

console.log(`载入航迹 ${loadedTracks.length} 条（一次拍摄 = 一份合并航迹，三路在里面）：`);
for (const t of loadedTracks) console.log('   ', t.fileInfo.relative_path, t.coords.length, '点');

// 一次拍摄现在只有**一份** geojson（文件名不带 _V/_S/_T），三路视频与三路帧号
// 都在这一条的 properties 里（videos / streams / point_frames / reference_stream）。
// 所以本节不再「按 _V 后缀挑一条航迹」，而是**找那种合并航迹**。
// 「按流取标签」的输入也从航迹路径换成了**视频文件名**：航迹名没有后缀了，
// streamLabelOf(合并航迹名) 必然是 'Other'（它对纯字符串函数的断言仍然有效）。
const V = loadedTracks[0];
const merged = loadedTracks.filter(t => t.videos && t.streams);
const videoOf = (t, suf) => (t.videos && t.videos[suf]) || t.video || '';

chk(loadedTracks.length === 1, '一次拍摄只有 1 份航迹（不再是 V/S/T 三份 + 3D 六份）', loadedTracks.length);
chk(merged.length === loadedTracks.length, '每条都是合并航迹（带 videos/streams）', merged.length);
chk(V && Array.isArray(V.streams) && V.streams.join('') === 'STV',
  '三路流都在这一条上（streams = S/T/V）', V && JSON.stringify(V.streams));
chk(V && V.referenceStream === 'V', '参考路是 V（可见光 4K，提供坐标与时刻）', V && V.referenceStream);

const k = Math.floor(V.coords.length / 2);
const onTrack = { lng: V.coords[k][0], lat: V.coords[k][1] };

console.log('\n=== 1) 按航迹去重：一次拍摄只该给出一条候选 ===');
const cands = nearestPerStream(onTrack);
// 旧模型：6 份 geojson（V/S/T 各 2D+3D）去重成 3 条候选（V 4K / S 1080p / T 红外）。
// 新模型：三路已经合成一份航迹，所以候选就是 1 条 —— 地图上只画一条线的直接后果。
// 三路各自的身份改由这条候选的 streams/videos 表达（见第 4 节）。
chk(cands.length === 1, '候选数 = 1（一次拍摄一条航迹）', cands.length);
console.log('    候选：' + cands.map(c => `${c.track.fileInfo.relative_path}(距离${c.distance.toFixed(2)}m, ${formatTime(c.time)})`).join('  '));
chk(cands.every(c => !/\.3d\.geojson$/i.test(c.track.fileInfo.relative_path)), '3D 版本已被去重掉');
chk(cands.every((c, i) => i === 0 || c.distance >= cands[i - 1].distance), '候选按距离升序');

console.log('\n=== 2) 命中点必须真的落在轨迹上，距离≈0 ===');
chk(cands[0].distance < 0.05, '最近距离 ≈ 0 m', cands[0].distance.toFixed(4) + ' m');
const hc = cands[0].track.coords[cands[0].index];
chk(hc[0] === onTrack.lng && hc[1] === onTrack.lat, '返回的轨迹点坐标与目标一致');
chk(Number.isFinite(cands[0].time) && cands[0].time >= 0 && cands[0].time <= cands[0].track.videoEnd + 1,
  '视频时间在 [0, 视频总长] 区间内', `${cands[0].time}s / 共${cands[0].track.videoEnd}s`);

console.log('\n=== 3) 分组：合并航迹自己就是主视频，没有「另外两路」了 ===');
const grp = pickNearestGroup(onTrack);
chk(grp !== null, '有结果');
// 旧断言是「primary 是 _V 那份 geojson、others 是 _S/_T 两份、三路时间差在阈值内」。
// 新模型下这三条已经没有对应物：**没有三份航迹可比**，三路只差帧号（时间轴是共用的）。
// 等价性质改成：唯一那条候选就是 primary，且它就是参考路 V 的那条 —— 主视频仍是可见光。
chk(grp.primary === grp.others.length + 1 || grp.others.length === 0,
  '只有一条候选时不会凭空造出备选', `primary 1 条 / others ${grp.others.length} 条`);
chk(grp.primary.track === V, 'primary 就是那份合并航迹');
chk(grp.primary.track.referenceStream === 'V',
  '主视频仍标为可见光（参考路 V）—— 修复前会命中列表里第一条 S.3d', grp.primary.track.referenceStream);
// streamLabelOf 现在要拿**视频文件名**问，不能拿合并航迹名（那个没有后缀，必是 Other）
chk(streamLabelOf(videoOf(V, V.referenceStream)) === 'Visible 3840×2160',
  '主视频视频名标为“Visible 3840×2160”', videoOf(V, V.referenceStream));
chk(streamLabelOf('DJI_x_S.geojson') === 'Visible 1920×1080', '_S 标为“Visible 1920×1080”');
chk(streamLabelOf('DJI_x_T.geojson') === 'Thermal 1280×1024',
  '_T 标为“Thermal 1280×1024”（实测尺寸，不是 640×512 也不是 540p）');
chk(streamLabelOf(V.fileInfo.relative_path) === 'Other',
  '合并航迹名本身没有流后缀（所以标签必须从 videos 取，不能从航迹名猜）',
  V.fileInfo.relative_path);
chk(grp.primary.distance <= cands[0].distance + 1e-9, 'primary 与最近候选一致');

console.log('\n=== 4) 三路（V/S/T）都挂在这一条航迹上，各有自己的视频与帧号 ===');
for (const suf of V.streams) {
  console.log(`    ${suf} ${String(videoOf(V, suf)).padEnd(38)} ${streamLabelOf(videoOf(V, suf))}`);
}
chk(V.streams.every(suf => !!videoOf(V, suf)), '三路都能取到视频文件名',
  V.streams.map(s => videoOf(V, s)).join(' / '));
chk(V.streams.every(suf => fs.existsSync(path.join(DIR, videoOf(V, suf)))),
  '三路视频文件都真实存在（以前从合并航迹名会推出不存在的 DJI_x.mp4）');
// 帧号推不出来（帧率不同、还各有丢帧），所以必须逐点存下来 —— 这条就是新格式的核心理由
const frames = V.pointFrames || {};
chk(V.streams.every(suf => Array.isArray(frames[suf]) && frames[suf].length === V.coords.length),
  '三路都有逐点帧号，且与坐标一一对应',
  V.streams.map(s => `${s}:${(frames[s] || []).length}`).join(' '));
chk(frames.V[k] !== frames.T[k],
  '同一时刻 T 与 V 的帧号不同（正是推不出来的证据）', `V=${frames.V[k]} T=${frames.T[k]}`);

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

console.log('\n=== 7) 合并航迹 -> 视频路径（含 .3d），并验证文件存在 ===');
// 旧模型：航迹名去掉 .geojson 加 .mp4 就是那一路视频。
// 新模型：合并航迹名推出来的是**不存在的** `DJI_x.mp4`，必须读 videos 表 ——
// 这正是这次改动里最容易踩空的一根线（踩过：图标/箭头全建不出来）。
for (const t of loadedTracks) {
  const byName = videoPathFromGeojson(t.fileInfo.relative_path);
  chk(!fs.existsSync(path.join(DIR, byName)),
    `${t.fileInfo.relative_path} -> ${byName}（靠文件名推出来的，确实不存在）`, '不存在（符合预期）');

  if (!t.videos) continue;

  // ① 有 track 时按 videos 表取（页面 addGeo 走的就是这条）
  for (const suf of t.streams) {
    const v = videoPathFromGeojson(t.fileInfo.relative_path, {
      videos: t.videos, video: t.video, referenceStream: t.referenceStream, stream: suf
    });
    const exists = fs.existsSync(path.join(DIR, v));
    chk(exists, `${t.fileInfo.relative_path.padEnd(38)} [${suf}] -> ${v}`, exists ? '存在' : '不存在！');
  }

  // ② 只给 referenceStream（不指定哪一路）时应落到参考路 V
  const vref = videoPathFromGeojson(t.fileInfo.relative_path, {
    videos: t.videos, video: t.video, referenceStream: t.referenceStream
  });
  chk(path.basename(vref) === t.video, '不指定路时取参考路（video 字段）',
    `${path.basename(vref)} / ${t.video}`);

  // ③ 反查：三路视频名都要能对回**这一份**合并航迹。
  // 这条线断了的后果是「地图不动、信息栏却正常」（trackForClip 找不到航迹就提前返回），
  // 而它靠的正是 flightStemOfForMatch / trackMatchesPath（页面里 trackForClip 用的同一对）。
  for (const suf of t.streams) {
    chk(trackMatchesPath(t.fileInfo.relative_path, videoOf(t, suf)),
      `${videoOf(t, suf).padEnd(38)} -> ${t.fileInfo.relative_path}（视频反查航迹）`);
  }
  chk(!trackMatchesPath(t.fileInfo.relative_path, 'DJI_20260924101516_0001_V.MP4'),
    '别的架次不会被误判成同一次拍摄');
}

console.log('\n=== 8) 性能 ===');
const total = loadedTracks.reduce((s, t) => s + t.coords.length, 0);
const t0 = process.hrtime.bigint();
for (let i = 0; i < 20; i++) pickNearestGroup({ lng: onTrack.lng + i * 1e-4, lat: onTrack.lat });
const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 20;
console.log(`  ${loadedTracks.length} 条航迹 / ${total.toLocaleString()} 个点，单次检索 ${ms.toFixed(2)} ms`);
chk(ms < 200, '单次检索 < 200 ms');

console.log('\n=== 9) 候选上带的高度（供「距离较远」提示旁边的信息栏用）===');
// 保留旧模型里的这一条：3D 文件已经不再写冗余的 point_heights，
// 高度要从坐标第三维取回来（heightsOfTrack）。合并航迹也是这么取的。
chk(grp.primary.height !== null, '高度已从坐标第三维带过来', grp.primary.height);

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
