// 照片图层 + 展示区 + 「点照片跳视频」的验证。
//
// 分两层：
//   A. 纯函数层（文件名时刻解析、相机标签、画廊拼 HTML、匹配排序）—— 用真值表断言；
//   B. 真实数据层 —— 读 Data/ 下真实的 GeoJSON + SRT 遥测 + 后端的 /api/project/photos，
//      验证「照片时刻 -> 视频帧」这条链路真的能找到那一帧，而且时空都对得上。
//
// 页面里的函数直接从 HTML 里抠出来跑（和 test_filelist.js / test_nearest.js 同一套做法），
// 这样测的就是页面上真正在用的那份代码，不会出现「测试里一份、页面里另一份」。
//
// 路径按脚本所在目录推导；可用 argv[2] 覆盖 HTML 路径。

const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const HTML = process.argv[2] || path.join(ROOT, 'Code', 'project_geojson_preview.html');
const html = fs.readFileSync(HTML, 'utf8');

let ok = true;
const chk = (c, label, extra = '') => {
  ok &&= !!c;
  console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
};

// ------------------------------------------------------------
// 从页面里抠函数（按花括号配平截取）
// ------------------------------------------------------------
function extractFn(name) {
  const start = html.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('页面里找不到 function ' + name + '()');
  let depth = 0;
  for (let j = html.indexOf('{', start); j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (depth === 0) return html.slice(start, j + 1); }
  }
  throw new Error('函数没配平：' + name);
}

// 顶层 const 取值（写成 `const X=...;` 一行的那种）
function extractConst(name) {
  const m = html.match(new RegExp('const\\s+' + name + '\\s*=\\s*([^;\\n]+);'));
  if (!m) throw new Error('页面里找不到 const ' + name);
  return m[1];
}

const PURE = [
  // 相机与文案
  'photoCameraLabel', 'photoCameraClass', 'photoTimeText', 'photoClockText',
  // 大图挑法（可见光变焦 > 可见光广角 > 热成像，用户 2026-10-07 定的规则）
  'photoLeadMember', 'photoCameraRank',
  'photoGroupTimeText', 'photoLeadName', 'photoShotText',
  'photoGroupLabel', 'hexToRgba',
  // 图片地址 / 前缀
  'photoThumbUrl', 'photoStreamPrefix', 'photoVideoFolderPath', 'streamTagOf',
  // 点某张照片时「该播哪一路」的选择（这条错过一次：点 _V 照片跳成了 _S 视频）
  'pickMatchForPhoto',
  // 跳视频候选排序：把「和大图同一路」的提到最前
  'orderMatchesForLead',
  // 时刻对齐
  'videoRealStartMs', 'photoFileTime', 'photoVideoStartSeconds', 'photoFrameAt',
  // 匹配与展示
  'photoFrameMatch', 'photoMatchRank', 'photoGalleryHtml', 'photoJumpHtml',
  'photoCardChips', 'photoTooltip', 'telemetryIndexOf', 'telemetryQuery',
  'videoPathFromGeojson',
  // 候选构造（要验它给出的路径是 .mp4 而不是 .geojson —— 这条错过一次：
  // 界面上「点一下跳到视频」的按钮能点，一按就报「指定文件不是 MP4/MOV 视频」）
  'photoClipOf', 'photoMatchesFor'
];

// imagePointOfGround 是页面里「按位置检索」用的同一个反投影函数，这里连它的
// 依赖（fovOf / BASE_FOCAL / 画幅常量）一起抠出来 —— 照片的「画面内」判定
// 与检索必须完全同源，所以不另写一份简化版。
//
// 顺带把「画面中心对应的地面点」那套（offsetLatLng / centerGroundLatLng /
// groundCenterDistance）也抠出来：真实数据那一层要用它造一个确定的目标点。
const GEO = ['imagePointOfGround', 'fovOf', 'offsetLatLng', 'centerGroundLatLng',
             'groundCenterDistance'];

const consts = {
  FRAME_ASPECT: extractConst('FRAME_ASPECT'),
  FULLFRAME_DIAGONAL: extractConst('FULLFRAME_DIAGONAL'),
  BASE_FOCAL: extractConst('BASE_FOCAL'),
  GROUND_MIN_PITCH: extractConst('GROUND_MIN_PITCH'),
  PHOTO_ZOOM: extractConst('PHOTO_ZOOM'),
  PHOTO_MATCH_MAX_GAP: extractConst('PHOTO_MATCH_MAX_GAP'),
  PHOTO_DRONE_NEAR_M: extractConst('PHOTO_DRONE_NEAR_M'),
  PHOTO_MATCH_LIMIT: extractConst('PHOTO_MATCH_LIMIT'),
  PHOTO_CAM_NAMES: extractConst('PHOTO_CAM_NAMES'),
  // 大图的相机优先级（可见光变焦 > 可见光广角 > 热成像）
  PHOTO_CAMERA_RANK: extractConst('PHOTO_CAMERA_RANK'),
  // 点照片跳视频时往前倒退多久起播（用户 2026-10-07：先用 3 秒试）
  PHOTO_PREROLL_SECONDS: extractConst('PHOTO_PREROLL_SECONDS'),
};

const src = [
  ...Object.entries(consts).map(([k, v]) => `const ${k}=${v};`),
  extractFn('streamLabelOf'),
  extractFn('esc'),
  extractFn('formatTime'),
  ...PURE.map(extractFn),
  ...GEO.map(extractFn),
  // 测试用的桩：L 只用到 latLng，map 只用到 distance（球面近似足够断言用）
  `const L={latLng:(a,b)=>({lat:a,lng:b})};`,
  `const map={distance:(a,b)=>{const R=6371000;const p1=a.lat*Math.PI/180,p2=b.lat*Math.PI/180;`
  + `const dp=p2-p1,dl=(b.lng-a.lng)*Math.PI/180;`
  + `const h=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;`
  + `return 2*R*Math.asin(Math.sqrt(h));}};`,
  `let projectFolderPaths=null;`,
  `let loadedTracks=[];`,  // 真实数据那一层用：第 i 帧「画面中心对应的地面点」。
  // ---- 点照片跳视频的「倒计时 + 到点自动暂停」用的桩 ----
  // 这几个名字在页面里是模块级变量，抽出来一起放进同一个函数体就能共享作用域。
  `let photoPauseAt=null;`,
  `let photoPauseByUs=false;`,
  `let clip={};`,
  `const videoStatus={textContent:''};`,
  `const videoCountdown={hidden:true,textContent:''};`,
  `const videoPlayer={currentTime:0,paused:false,ended:false,_paused:0,`
  + `play(){this.paused=false;return Promise.resolve()},`
  + `pause(){this.paused=true;this._paused++}};`,
  extractFn('setPhotoCountdownTarget'),
  extractFn('stopPhotoCountdown'),
  extractFn('updatePhotoCountdown'),
  extractFn('tickPhotoPause'),
  // 这正是照片解算在做的事（ground_target 与 centerGroundLatLng 是同一套公式），
  // 所以拿它当目标点回投影，理应落在画面中心。
  `function centerGroundPointForTest(track,tele,i){`
  + `const c=(track.coords||[])[i];`
  + `if(!Array.isArray(c)||c.length<2)return null;`
  + `const alt=Number(tele.alt&&tele.alt[i]);`
  + `const yaw=Number(tele.yaw&&tele.yaw[i]);`
  + `const pitch=Number(tele.pitch&&tele.pitch[i]);`
  + `if(!Number.isFinite(alt)||alt<=0)return null;`
  + `if(!Number.isFinite(yaw)||!Number.isFinite(pitch)||pitch>=0)return null;`
  + `return centerGroundLatLng(L.latLng(Number(c[1]),Number(c[0])),yaw,pitch,alt);}`,
  `return {${[...PURE, ...GEO].join(',')},centerGroundPointForTest,loadedTracks,`
  + `setFolders:v=>{projectFolderPaths=v},getFolders:()=>projectFolderPaths,`
  // 倒计时那几个：连同它们用到的桩状态一起暴露出来，好逐档断言
  + `cd:{setTarget:setPhotoCountdownTarget,stop:stopPhotoCountdown,`
  + `update:updatePhotoCountdown,tick:tickPhotoPause,`
  + `getTarget:()=>photoPauseAt,setTargetRaw:v=>{photoPauseAt=v},`
  + `player:videoPlayer,countdown:videoCountdown,status:videoStatus}};`
].join('\n');

const page = new Function(src)();

console.log('=== 1) 文件名里的时刻（时刻对齐的地基）===');

{
  const t = page.photoFileTime('DJI_20260924095348_0002_V.JPG');
  const ref = new Date(2026, 8, 24, 9, 53, 48).getTime();
  chk(t === ref, '照片名 -> 本地时间戳与 Date(2026,8,24,9,53,48) 一致', new Date(t).toString().slice(0, 24));

  chk(page.photoFileTime('DJI_20260924101542_0004_T.JPG') === new Date(2026, 8, 24, 10, 15, 42).getTime(),
    '带 _T 后缀的热成像照片同样能解析');
  chk(page.photoFileTime('随便一个名字.jpg') === null, '拆不出时刻 -> null（不猜）');
  chk(page.photoFileTime('DJI_20261332095348_0001_V.JPG') === null, '月份越界（13 月）-> null（不让 Date 悄悄滚到下一年）');
  chk(page.photoFileTime('DJI_20260932095348_0001_V.JPG') === null, '日期越界（32 日）-> null');

  const v = page.videoRealStartMs('DJI_20260924095258_0001_S.MP4');
  chk(v === new Date(2026, 8, 24, 9, 52, 58).getTime(),
    '视频名 -> 开录时刻（相对时间要对到真实时刻，全靠它）', new Date(v).toLocaleString('zh-CN'));
  chk(page.videoRealStartMs('没有时间戳的视频.mp4') === null, '视频名里没时刻 -> null（该视频不参与匹配）');

  // 与实测互校：SRT 时长 1228.694 s、mtime 10:13:28，开录 09:52:58 —— 差值应为 3 秒以内
  const srtEnd = new Date(2026, 8, 24, 10, 13, 28).getTime();
  const srtSpan = 1228.694 * 1000;
  chk(Math.abs((v + srtSpan) - srtEnd) / 1000 <= 5,
    '文件名开录时刻 + SRT 时长 与文件 mtime 互校在 5 秒内',
    `差 ${((srtEnd - (v + srtSpan)) / 1000).toFixed(1)} 秒`);
}

console.log('\n=== 2) 照片时刻 -> 视频播放进度 ===');

{
  const clip = {
    realStartMs: new Date(2026, 8, 24, 9, 52, 58).getTime(),
    track: { times: [0, 0.033, 0.067, 1, 2, 60, 600, 1228.694] }
  };

  const photoMs = new Date(2026, 8, 24, 9, 53, 48).getTime();   // 开录后 50 秒
  const s = page.photoVideoStartSeconds(clip, photoMs);
  chk(Math.abs(s - 50) < 0.001, '开录后 50 秒的照片 -> 进度 50.0 s', s.toFixed(3));

  chk(page.photoVideoStartSeconds(clip, clip.realStartMs) === 0, '照片时刻 == 开录时刻 -> 0（不为负）');
  chk(page.photoVideoStartSeconds(clip, clip.realStartMs - 60000) === 0,
    '照片早于开录 -> 夹到 0（播放器不接受负数）');

  // 首条记录不是 0 的情况：基准要跟着首条走，否则第一帧会偏
  const late = { realStartMs: clip.realStartMs, track: { times: [0.5, 1, 2] } };
  chk(Math.abs(page.photoVideoStartSeconds(late, clip.realStartMs + 1000) - 0.5) < 1e-9,
    '首条记录 0.5 s 时，进度基准也跟着首条（1.0 s -> 0.5 s）');
}

console.log('\n=== 3) 按时刻找帧（二分）===');

{
  const track = { times: [0, 1, 2, 3, 4, 5] };

  chk(page.photoFrameAt(track, 2) === 2, '正好命中第 2 秒 -> 下标 2');
  chk(page.photoFrameAt(track, 2.4) === 2, '2.4 s -> 取更近的 2 s（下标 2）');
  chk(page.photoFrameAt(track, 2.6) === 3, '2.6 s -> 取更近的 3 s（下标 3）');
  chk(page.photoFrameAt(track, -5) === 0, '早于首帧 -> 下标 0');
  chk(page.photoFrameAt(track, 999) === 5, '晚于末帧 -> 最后一个下标');
  chk(page.photoFrameAt({ times: [] }, 1) === -1, '没有记录 -> -1');

  // 逐点比对二分结果与线性扫描：几万点的那条链路不能靠运气
  const big = [];
  for (let i = 0; i < 3000; i++) big.push(i * 0.4);
  let mismatch = -1;
  for (let t = -1; t < 1205; t += 7.3) {
    let best = 0;
    for (let i = 1; i < big.length; i++) {
      if (Math.abs(big[i] - t) < Math.abs(big[best] - t)) best = i;
    }
    if (page.photoFrameAt({ times: big }, t) !== best) { mismatch = t; break; }
  }
  chk(mismatch < 0, '二分结果与线性扫描完全一致（3000 点 × 165 个时刻）',
    mismatch < 0 ? '' : '首个不一致 t=' + mismatch);
}

console.log('\n=== 3b) 航迹点下标 -> 遥测下标（抽稀对齐）===');

{
  // 第一条路：按**时间**对齐（真实遥测）。抽稀是按记录计数，SRT 里个别记录缺经纬度
  // 会掉，间隔并不严格均匀，所以按 tele.times 二分找最接近的那条才稳。
  const track = { times: [0, 0.033, 0.067, 0.1, 10, 10.5, 20] };
  const tele = { step: 3, times: [0, 0.1, 10.5, 20], alt: [1, 2, 3, 4] };

  chk(page.telemetryIndexOf(track, tele, 0) === 0, '按时间：第 0 点(t=0) -> 遥测 0');
  chk(page.telemetryIndexOf(track, tele, 3) === 1, '按时间：第 3 点(t=0.1) -> 遥测 1');
  chk(page.telemetryIndexOf(track, tele, 5) === 2, '按时间：第 5 点(t=10.5) -> 遥测 2');
  chk(page.telemetryIndexOf(track, tele, 6) === 3, '按时间：末尾点 -> 最后一条遥测');
  chk(page.telemetryIndexOf({ times: [-99] }, tele, 0) === 0, '按时间：早于首条 -> 夹到 0');

  // 第二条路：遥测里没有 times 时退回 step 整除（测试桩 / 老后端）
  chk(page.telemetryIndexOf({ times: [0, 1, 2, 3] }, { step: 3 }, 0) === 0, '退回 step：第 0 点 -> 0');
  chk(page.telemetryIndexOf({ times: [0, 1, 2, 3] }, { step: 3 }, 3) === 1, '退回 step：第 3 点 -> 1');
  chk(page.telemetryIndexOf({ times: [0, 1] }, { step: 1 }, 1) === 1, 'step=1 时退化为原下标');
  chk(page.telemetryIndexOf({ times: [0, 1] }, {}, 1) === 1, 'step 缺失时也退化为原下标（老后端不上报 step）');

  // 端到端：同一帧、同一目标点，用抽稀遥测与用全量遥测算出的画面坐标必须一致。
  // 这条断言失败就说明下标映射又错位了 —— 画面内判定会整片误判。
  const coords = Array(9).fill([114.0, 23.0]);
  const times = Array.from({ length: 9 }, (_, k) => k / 30);
  const full = {
    alt: Array(9).fill(100), yaw: Array.from({ length: 9 }, (_, k) => k * 3),
    pitch: Array(9).fill(-45), focal: Array(9).fill(24), times: times.slice()
  };
  // 抽稀成 step=3 的形式（每 3 帧留一条），但 times 保留真实时刻
  const thin = { step: 3, alt: [], yaw: [], pitch: [], focal: [], times: [] };
  for (let k = 0; k < 9; k += 3) {
    thin.alt.push(full.alt[k]); thin.yaw.push(full.yaw[k]);
    thin.pitch.push(full.pitch[k]); thin.focal.push(full.focal[k]); thin.times.push(times[k]);
  }

  const trackFull = { coords, times };
  const target = { lat: 23.0 + 100 / 110540, lng: 114.0 };

  let same = true;
  let detail = '';
  for (const i of [0, 3, 6]) {
    const a = page.imagePointOfGround(trackFull, full, i, target);
    // 抽稀遥测里没有第 i 帧，映射过去的是最接近的采样帧 —— 这两者本来就该一致
    const b = page.imagePointOfGround(trackFull, thin, i, target);
    if (!a || !b || Math.abs(a.xImg - b.xImg) > 1e-9 || Math.abs(a.yImg - b.yImg) > 1e-9) {
      same = false;
      detail = `i=${i} 全量(${a && a.xImg.toFixed(3)},${a && a.yImg.toFixed(3)})`
        + ` vs 抽稀(${b && b.xImg.toFixed(3)},${b && b.yImg.toFixed(3)})`;
      break;
    }
  }
  chk(same, '采样点上的图像坐标与全量遥测一致（画面内判定不再整片误判）', detail);

  // 反面：不按抽稀映射时会读到「第 3i 帧」的姿态。
  // 为了让它必然算出不同结果，这里给 unmapped 的每一帧都写成不同姿态 ——
  // 只要读错下标，结果就会变。
  const unmapped = {
    alt: [], yaw: Array.from({ length: 9 }, (_, k) => k * 11),
    pitch: Array(9).fill(-45), focal: Array(9).fill(24), times: times.slice()
  };
  for (let k = 0; k < 9; k++) unmapped.alt.push(100);
  const wrong = page.imagePointOfGround(trackFull, unmapped, 6, target);
  const right = page.imagePointOfGround(trackFull, thin, 6, target);
  chk(!!wrong && !!right && Math.abs(wrong.xImg - right.xImg) > 1e-6,
    '对照：读错下标（拿第 6 帧直接读遥测第 6 条，而不是采样后的第 2 条）结果确实不同',
    wrong ? `x ${wrong.xImg.toFixed(3)} vs ${right.xImg.toFixed(3)}` : '-');
}

console.log('\n=== 4) 相机标签与分组文案 ===');
{
  chk(page.photoCameraLabel('ZoomCamera') === '变焦', 'ZoomCamera -> 变焦（大图优先给这张）');
  chk(page.photoCameraLabel('WideCamera') === '广角', 'WideCamera -> 广角');
  chk(page.photoCameraLabel('InfraredCamera') === '热成像', 'InfraredCamera -> 热成像');
  chk(page.photoCameraLabel('别的相机') === '别的相机', '认不出的相机原样显示（不猜）');
  chk(page.photoCameraLabel('') === '照片', '空值 -> 「照片」兜底');
  chk(page.photoCameraClass('ZoomCamera').includes('cam-zoom'), '变焦有独立配色类');
  chk(page.photoCameraClass('InfraredCamera').includes('cam-thermal'), '热成像有独立配色类');

  chk(page.photoTimeText('DJI_20260924095348_0002_V.JPG') === '2026-09-24 09:53:48', '照片名 -> 完整时刻');
  chk(page.photoClockText('DJI_20260924095348_0002_V.JPG') === '09:53:48', '照片名 -> 钟点');
  chk(page.photoTimeText('x.jpg') === '', '拆不出来 -> 空串');

  const group = {
    stamp: '20260924_095348',
    lat: 23.0415,
    lon: 114.1064,
    accuracy: '实测',
    count: 2,
    members: [
      { name: 'DJI_20260924095348_0002_V.JPG', folder: 'D:\\a b\\架次1', camera: 'WideCamera', accuracy: '实测', distance: 178.6, depression: 29.4 },
      { name: 'DJI_20260924095348_0002_T.JPG', folder: 'D:\\a b\\架次1', camera: 'InfraredCamera', accuracy: '实测', distance: 178.6, depression: 29.4 }
    ]
  };

  chk(page.photoShotText(group) === '广角 + 热成像', '组文案按组内顺序拼', page.photoShotText(group));
  chk(page.photoLeadName(group).endsWith('_V.JPG'), 'lead 取组内第一张');
  chk(page.photoGroupTimeText(group) === '2026-09-24 09:53:48', '组时刻取第一张的名字');
  chk(page.photoGroupLabel([group], 0) === '地图下方的照片展示区', '单点时标题不写序号');
  chk(page.photoGroupLabel([group, group], 1).includes('2 / 2'), '多点时标题带序号', page.photoGroupLabel([group, group], 1));

  chk(page.hexToRgba('#1d4ed8', 0.35) === 'rgba(29,78,216,0.35)', '光晕色换算正确');
  chk(page.hexToRgba('乱写', 0.5) === 'rgba(37,99,235,0.5)', '坏值退回默认蓝');
}

console.log('\n=== 5) 展示区：变焦大图优先、其余小图并排 ===');

{
  const mk = (camera, name, accuracy) => ({
    name, folder: 'D:\\数据\\架次1', camera, accuracy: accuracy || '实测',
    accuracy_note: '', distance: 100, depression: 30
  });

  // 后端已按 变焦 -> 广角 -> 热成像 排好，前端不再重排
  const group = {
    lat: 23.1, lon: 114.2, accuracy: '实测', count: 3,
    members: [
      mk('ZoomCamera', 'DJI_20260924101542_0004_S.JPG'),
      mk('WideCamera', 'DJI_20260924101542_0004_V.JPG'),
      mk('InfraredCamera', 'DJI_20260924101542_0004_T.JPG')
    ]
  };

  const g = page.photoGalleryHtml(group);

  chk(g.indexOf('photo-lead') >= 0, '有「大图」那一块');
  chk(/photo-lead[\s\S]*?0004_S\.JPG/.test(g), '大图用的就是变焦那张（_S）');
  chk(/photo-lead[\s\S]*?>大图</.test(g), '大图上标了「大图」');
  chk((g.match(/photo-shot photo-thumb/g) || []).length === 2, '其余两张进小图区（并排）',
    String((g.match(/photo-shot photo-thumb/g) || []).length) + ' 张');
  chk(g.indexOf('0004_V.JPG') > g.indexOf('0004_S.JPG'), '小图排在大图之后');
  chk(g.indexOf('0004_V.JPG') < g.indexOf('0004_T.JPG'), '小图内部保持后端给的顺序（广角在热成像前）');
  chk((g.match(/\/photo\?path=/g) || []).length === 3, '三张都走后端 /photo 接口');
  chk(g.includes('%5C'), '绝对路径里的反斜杠被编码（否则后端解析不出 path）');
  chk(g.includes('data-photo-name='), '小图带文件名，点它才知道要按哪张的时刻跳');
  chk(/alt="[^"]*照片"/.test(g), '每张都有 alt（图片取不到时不至于一片空白）');

  // 只有一张时不该出现空的小图区
  const single = page.photoGalleryHtml({ lat: 1, lon: 2, accuracy: '实测', count: 1, members: [mk('ZoomCamera', 'a_S.JPG')] });
  chk(single.indexOf('photo-thumbs') < 0, '单张时没有小图区');
  chk(single.indexOf('大图') >= 0, '单张也走「大图」这套版式');

  // 「位置不准」的照片要带 ⚠，这是用户明确要的
  const warn = page.photoGalleryHtml({
    lat: 1, lon: 2, accuracy: '位置不准', count: 1,
    members: [mk('WideCamera', 'w_V.JPG', '位置不准')]
  });
  chk(warn.includes('⚠'), '位置不准的那张带 ⚠ 角标标记');

  const chips = page.photoCardChips({
    lat: 23.041556, lon: 114.106484, accuracy: '位置不准', count: 1,
    members: [{ name: 'DJI_20260924102746_0034_T.JPG', camera: 'InfraredCamera', accuracy: '位置不准', accuracy_note: '该张没有激光数据，中心点按平地假设估算', distance: 171.5, depression: 19.8 }]
  });
  chk(chips.includes('23.041556'), '点信息里有目标点坐标');
  chk(chips.includes('2026-09-24 10:27:46'), '点信息里有拍摄时刻');
  chk(chips.includes('位置不准') && chips.includes('⚠'), '位置不准时如实标出，并带上依据说明');
}

console.log('\n=== 6) 「跳视频」那块的说法 ===');

{
  const group = { lat: 23.1, lon: 114.2, accuracy: '实测', count: 1, members: [{ name: 'DJI_20260924095348_0002_V.JPG', camera: 'WideCamera' }] };

  const hit = page.photoJumpHtml(group, [{
    video: 'DJI_20260924095258_0001_V.MP4', relativePath: 'DJI_20260924095258_0001_V.MP4',
    folderIndex: 0, stream: '可见光 3840×2160', index: 1500, time: 49.9,
    gapSeconds: -0.1, startSeconds: 49.9, droneDistance: 4, inFrame: true, inFrameKnown: true
  }]);

  chk(hit.includes('DJI_20260924095258_0001_V.MP4'), '按钮上写着视频文件名');
  chk(hit.includes('data-photo-match="0"'), '按钮带下标，点它才知道跳哪一段');
  chk(hit.includes('画面内'), '时空都对上时，明确说「目标点在画面内」—— 这就是交叉验证');
  chk(hit.includes('2026-09-24 09:53:48'), '写清是按哪个时刻对齐的');
  chk(hit.includes('-0.1 秒'), '给出时间差（用户能自己判断可信度）');

  const far = page.photoJumpHtml(group, [{
    video: 'b.MP4', relativePath: 'b.MP4', folderIndex: 0, stream: 'x', index: 5,
    time: 300, gapSeconds: 250, startSeconds: 300, droneDistance: 900,
    inFrame: false, inFrameKnown: true
  }]);
  chk(far.includes('参考') || far.includes('核对'), '时间差大时提示只能当参考、要人工核对', far.includes('参考') ? '含「参考」' : '含「核对」');

  const none = page.photoJumpHtml(group, []);
  chk(none.includes('没有找到时间对得上的视频'), '找不到时说明白，而不是留空白');
  chk(none.includes('加载全部'), '并给出可照做的下一步（先加载全部）');

  const tip = page.photoTooltip({ lat: 23.041556, lon: 114.106484, accuracy: '位置不准', count: 2, members: [{ name: 'DJI_20260924095348_0002_V.JPG', camera: 'WideCamera' }] });
  chk(tip.includes('位置不准'), '悬停提示里就写清位置可不可信');
  chk(tip.includes('共 2 张'), '悬停提示里说明点开会有几张');
}

console.log('\n=== 7) 真实数据：照片时刻真的能落到视频的那一帧 ===');

{
  const DATA = path.join(ROOT, 'Data');
  const folders = fs.existsSync(DATA)
    ? fs.readdirSync(DATA).map((n) => path.join(DATA, n)).filter((p) => fs.statSync(p).isDirectory())
    : [];

  const geojsonFile = (() => {
    for (const f of folders) {
      const hit = fs.readdirSync(f).find((n) => /_V\.geojson$/i.test(n));
      if (hit) return path.join(f, hit);
    }
    return null;
  })();

  if (!geojsonFile) {
    console.log('  [SKIP] Data/ 下没有 GeoJSON，跳过真实数据那一层');
  } else {
    const geo = JSON.parse(fs.readFileSync(geojsonFile, 'utf8'));
    const feature = geo.features[0];
    const times = feature.properties.point_times;
    const coords = feature.geometry.coordinates;

    chk(times.length === coords.length, '真实 GeoJSON：时间与坐标一一对应', `${times.length} 条`);

    const srtFile = path.join(path.dirname(geojsonFile), path.basename(geojsonFile).replace(/_V\.geojson$/i, '_V.srt'));
    let tele = null;
    if (fs.existsSync(srtFile)) {
      const text = fs.readFileSync(srtFile, 'utf8').replace(/\r\n/g, '\n');
      const t = [], yaw = [], pitch = [], focal = [], alt = [];
      let cue = null, idx = 0;
      for (const line of text.split('\n')) {
        const m = line.match(/^(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->/);
        if (m) { cue = (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4]) / 1000; continue; }
        if (!line.includes('latitude')) continue;
        if (idx % 3 === 0 && cue != null) {
          t.push(cue);
          const g = (re) => { const x = line.match(re); return x ? parseFloat(x[1]) : null; };
          yaw.push(g(/gb_yaw:\s*(-?\d+(?:\.\d+)?)/));
          pitch.push(g(/gb_pitch:\s*(-?\d+(?:\.\d+)?)/));
          focal.push(g(/\[focal_len:\s*(-?\d+(?:\.\d+)?)\]/));
          alt.push(g(/\[rel_alt:\s*(-?\d+(?:\.\d+)?)/));
        }
        idx++;
      }
      if (t.length) tele = { times: t, yaw, pitch, focal, alt };
    }

    chk(!!tele, '读到真实 SRT 遥测（画面内判定要用它）', tele ? `${tele.times.length} 条` : '没读到');

    const track = {
      coords, times, telemetry: tele,
      video: path.basename(geojsonFile).replace(/\.geojson$/i, '.MP4'),
      fileInfo: { relative_path: path.basename(geojsonFile).replace(/\.geojson$/i, '.MP4'), folder_index: 0 }
    };

    page.setFolders([path.dirname(geojsonFile)]);

    const clip = page.videoRealStartMs(track.fileInfo.relative_path) != null
      ? {
        realStartMs: page.videoRealStartMs(track.fileInfo.relative_path),
        track,
        info: track.fileInfo,
        ms0: page.videoRealStartMs(track.fileInfo.relative_path) + times[0] * 1000,
        msEnd: page.videoRealStartMs(track.fileInfo.relative_path) + times[times.length - 1] * 1000
      }
      : null;

    chk(!!clip, '视频开录时刻可用（照片时刻才有参照）',
      clip ? new Date(clip.realStartMs).toLocaleString('zh-CN') : '取不到');

    // 这一架次的照片（文件名时刻落在视频时间范围内的那些）
    const photos = (() => {
      const dir = path.dirname(geojsonFile);
      const prefix = path.basename(geojsonFile).replace(/_V\.geojson$/i, '');
      return fs.readdirSync(dir).filter((n) => /\.JPG$/i.test(n));
    })();

    chk(photos.length > 0, '同一架次目录里有 JPG', `${photos.length} 张`);

    if (clip && photos.length) {
      // 取一张照片，按它的时刻匹配这一帧
      const photoName = photos[0];
      const t = page.photoFileTime(photoName);
      chk(t != null, '照片名解析出时刻', page.photoTimeText(photoName));

      // 照片的飞机位置：取视频里离该时刻最近的那一帧的坐标当参照，
      // 这样 droneDistance 这一项才有意义（照片 XMP 里的坐标不在这条测试链路上）
      const i = page.photoFrameAt(track, (t - clip.realStartMs) / 1000);
      const c = coords[i];

      // 目标点用「该帧画面中心对应的地面点」—— 这是链路自己算出来的点，
      // 拿它回来反投影，理应落在画面中心；同时也就把
      // 「照片目标点 -> 画面内判定」这条交叉验证真正跑通了。
      const target = tele ? page.centerGroundPointForTest(track, tele, i) : null;

      const group = {
        lat: null, lon: null, accuracy: '实测', count: 1, stamp: '',
        members: [{
          name: photoName,
          folder: path.dirname(geojsonFile),
          camera: 'WideCamera',
          accuracy: '实测',
          drone_lat: Number(c[1]),
          drone_lon: Number(c[0])
        }]
      };

      if (target) {
        group.lat = target.lat;
        group.lon = target.lng !== undefined ? target.lng : target.lon;
      } else {
        // 拿不到遥测时退回该帧坐标，只验证「找得到那一帧」
        group.lat = Number(c[1]);
        group.lon = Number(c[0]);
      }

      const m = page.photoFrameMatch(clip, group);

      // ---- 候选里的相对路径必须是 .mp4 ----
      // 踩过：候选带的是 fileInfo.relative_path（.geojson），于是「点一下跳到视频」
      // 按钮能点，一按就报「指定文件不是 MP4/MOV 视频」，播放器一片黑。
      // 这里用真实航迹 + 刚算出来的这一帧，把整条候选构造真的跑一遍。
      page.loadedTracks.length = 0;
      page.loadedTracks.push(track);
      const ms = page.photoMatchesFor(group);

      chk(ms.length > 0, 'photoMatchesFor 能给出候选（真实航迹）', ms.length + ' 个');

      if (ms.length) {
        const c0 = ms[0];
        chk(/\.mp4$/i.test(c0.relativePath), '候选的 relativePath 是 .mp4', c0.relativePath);
        chk(!/\.geojson$/i.test(c0.relativePath), '候选的 relativePath 不是 .geojson');
        chk(c0.video === c0.relativePath, 'video 与 relativePath 一致（按钮标签与实际播放同一个文件）',
          `${c0.video} / ${c0.relativePath}`);
        chk(!/^[A-Za-z]:/.test(c0.relativePath), 'relativePath 是相对路径（接口要相对路径）');
        chk(Number.isFinite(c0.startSeconds) && c0.startSeconds >= 0,
          '给了可直接用的起播秒数', c0 && String(c0.startSeconds.toFixed(2)));
        // 这条最要紧：起播秒数要与「照片时刻 - 视频首帧时刻」一致
        const want = (t - clip.ms0) / 1000;
        chk(Math.abs(c0.startSeconds - want) <= 1,
          '起播秒数 = 照片时刻 - 视频首帧时刻',
          `${c0.startSeconds.toFixed(2)} vs ${want.toFixed(2)}`);

        page.loadedTracks.length = 0;
      }

      chk(!!m, '匹配函数返回了一帧');
      chk(m && Math.abs(m.gapSeconds) <= 1, '找到的帧与照片时刻相差不到 1 秒（SRT 30fps，理应如此）',
        m ? m.gapSeconds.toFixed(3) + ' 秒' : '-');
      chk(m && Math.abs(m.time - (t - clip.realStartMs) / 1000) < 1,
        '帧的视频内时刻与「照片时刻 - 开录时刻」一致',
        m ? m.time.toFixed(3) + ' s' : '-');
      chk(m && m.droneDistance != null && m.droneDistance < 50,
        '空间也对得上：那一刻飞机就在照片飞机位置附近',
        m && m.droneDistance != null ? m.droneDistance.toFixed(1) + ' 米' : '-');

      if (target) {
        chk(m && m.inFrameKnown === undefined,
          'photoFrameMatch 只管单帧（inFrameKnown 是 photoMatchesFor 汇总后补上的，这里本就不该有）',
          m ? `inFrameKnown=${m.inFrameKnown}` : '-');
        chk(m && m.inFrame === true,
          '照片目标点（= 该帧画面中心的地面点）落在画面内 —— 交叉验证真的能判对',
          m ? `inFrame=${m.inFrame} x=${Number(m.xImg).toFixed(3)} y=${Number(m.yImg).toFixed(3)}` : '-');

        // 目标点是「用全量 SRT 算出来的那一帧画面中心」，而判定用的遥测是
        // 抽稀到 10Hz 的（每 3 帧一条），姿态最多差 50 ms —— 投影落点因此会有点
        // 偏移。这里只要求落在画面内、且明显偏中心区，不要求像素级重合。
        chk(m && Math.abs(m.xImg) < 0.5 && Math.abs(m.yImg) < 0.5,
          '而且落在画面中心附近（抽稀 10Hz 的姿态误差带来的偏移很小）',
          m ? `x=${Number(m.xImg).toFixed(4)} y=${Number(m.yImg).toFixed(4)}` : '-');

        // 「画面内」的证据是前后 ±2 秒（约 ±60 帧）里多数采样都看得见 ——
        // 单看一帧容易被瞬时抖动骗到。这里把同一套采样投票重放一遍：
        // 目标点是画面中心，前后 ±2 秒理应在画面里。
        const votes = (() => {
          const from = Math.max(0, m.index - 60);
          const to = Math.min(tele.times.length - 1, m.index + 60);
          const step = Math.max(1, Math.ceil((to - from + 1) / 5));
          let total = 0, hits = 0;
          for (let k = from; k <= to; k += step) {
            const p = page.imagePointOfGround(track, tele, k,
              { lat: Number(target.lat), lng: Number(target.lng) });
            if (!p) continue;
            total++;
            if (p.visible) hits++;
          }
          return { total, hits };
        })();

        chk(votes.total > 0 && votes.hits * 2 >= votes.total,
          '±2 秒的采样投票也是「看得见」占多数（瞬时抖动不会把结论带偏）',
          `${votes.hits}/${votes.total}`);
      } else {
        console.log('  [SKIP] 画面内判定（没读到遥测）');
      }

      // 时间越远，缺口越大：验证缺口确实是按真实时刻算的
      const group2 = JSON.parse(JSON.stringify(group));
      const laterName = photoName.replace(/(\d{8})(\d{6})/, (s, d, hhmmss) => {
        const hh = Number(hhmmss.slice(0, 2));
        return d + String(hh).padStart(2, '0') + hhmmss.slice(2);
      });
      // 改一小时之后的同名照片：缺口应当约 -3600 秒（照片晚于视频 -> 正/负按符号约定）
      const t2 = page.photoFileTime(laterName);
      if (t2 != null && t2 !== t) {
        group2.members[0].name = laterName;
        const m2 = page.photoFrameMatch(clip, group2);
        const expected = (clip.msEnd - t2) / 1000;   // 晚于视频结束 -> 负的「超出范围」
        chk(m2 === null || Math.abs(m2.gapSeconds) > 1800,
          '把照片时刻改到一小时后：要么没候选，要么缺口很大（说明缺口是按真实时刻算的）',
          m2 ? m2.gapSeconds.toFixed(1) + ' 秒' : 'null（超出范围，符合预期）');
      } else {
        console.log('  [SKIP] 改时刻的边界用例（名字里的小时是 09，改不动）');
      }
    }
  }
}

console.log('\n=== 8) 页面接线：接口 / 元素 / 一次性监听 ===');
{
  chk(html.includes("/api/project/photos?name="), '接了后端的照片接口');
  chk(html.includes("/photo?path="), '图片走后端 /photo（不用绝对路径直接喂浏览器）');
  chk(/id="photoLayerBtn"/.test(html), '有照片图层开关');
  chk(/>加载全部照片</.test(html), '按钮叫「加载全部照片」（用户定的名字）');
  chk(/<button id="loadAllBtn">加载全部轨迹<\/button>/.test(html),
    '左栏那个改叫「加载全部轨迹」（和「加载全部照片」区分开）');
  chk(/textContent=filtered\?`加载筛选（\$\{n\}）`:'加载全部轨迹'/.test(html),
    '筛选后按钮文案也跟着「加载全部轨迹」');
  // 这一行的三段（用户 2026-10-07 定的顺序）：
  //   ① 加载全部照片（贴左，就在「轨迹地图」标题正下方，不留空）
  //   ② 计数（它是按钮的说明，紧跟按钮右边）
  //   ③ 底图 + 天地图key（推到这一行最右边）
  const toolsRow = html.slice(html.indexOf('card-tools map-tools'),
                              html.indexOf('id="mapNotice"'));
  chk(/id="photoLayerBtn"/.test(toolsRow) && /id="baseMap"/.test(toolsRow) && /id="keyBtn"/.test(toolsRow),
    '三个控件在同一行（.card-tools.map-tools）');
  chk(toolsRow.indexOf('id="photoLayerBtn"') < toolsRow.indexOf('id="photoLayerCount"')
      && toolsRow.indexOf('id="photoLayerCount"') < toolsRow.indexOf('class="map-tools-right"'),
    '顺序：加载全部照片 -> 计数（它的说明） -> 底图组');
  chk(/\.card-tools\.map-tools\{[^}]*margin-left:0/.test(html),
    '这一行 margin-left:0 —— 否则被 .card-tools 的 auto 推到中间（实测偏 61px），'
    +'就不是「贴着左边、在标题正下方」了');
  chk(/\.map-tools-right\{[^}]*margin-left:auto/.test(html),
    '底图 / 天地图key 那组用 margin-left:auto 靠这一行最右边');
  chk(/\.photo-tools\{[^}]*margin-left:0/.test(html), '计数不抢 auto 边距，紧跟在按钮右边');
  // 大小与外观要和左栏「加载全部轨迹」一致
  {
    const fileBtn = (html.match(/\.card-tools\.file-actions button\{[^}]*\}/) || [''])[0];
    const photoBtn = (html.match(/\.photo-layer-btn\{[^}]*\}/) || [''])[0];
    const dim = (s) => String(s).match(/height:[^;]*/)[0] + '/'
      + (String(s).match(/font-size:[^;]*/) || [''])[0] + '/'
      + (String(s).match(/font-weight:[^;]*/) || [''])[0];
    chk(dim(photoBtn) === dim(fileBtn),
      '「加载全部照片」与「加载全部轨迹」同尺寸同字重（都走 --ctrl-h / 12px / 600）',
      `photo=${dim(photoBtn)} load=${dim(fileBtn)}`);
    chk(/border-radius:9px/.test(photoBtn), '圆角与全局 button 一致（9px）');
    chk(/color:#2563eb/.test(photoBtn), '关着时是浅底 + 主色字（看着可点，不是禁用灰）');
    const onRule = (html.match(/\.photo-layer-btn\.photo-on[^{]*\{[^}]*\}/) || [''])[0];
    chk(/#2563eb/.test(onRule) && /#fff/.test(onRule), '开启态是主色实心 + 白字（同「加载全部轨迹」）');
    chk(/\.photo-layer-btn\.photo-on/.test(html), '开启态用 .photo-on 表示（替代原来那套灰白 off）');
    chk(!/photoLayerBtn[^>]*class="toggle-btn/.test(html), '不再用 toggle-btn 那套（灰白看着像禁用）');
  }
  chk((html.match(/id="photoLayerCount"/g) || []).length === 1, '计数只有一处（没留重复元素）');
  chk(/max-width:1780px\)\{[\s\S]{0,200}#photoLayerCountExtra\{display:none\}/.test(html),
    '窄窗口时「· N 处合并」整段让位（阈值按实测：这一行满了就先舍补充信息）');
  chk(/max-width:1650px\)\{[\s\S]{0,200}#photoLayerCount\{display:none\}/.test(html),
    '更窄时连张数也让位，只留按钮（按钮是「要点的」，优先保住）');
  chk(!/photoLayerCount\.textContent=total\s*\?[^;]*(->)/.test(html), '计数用「→」而不是 "->"');

  // 点「加载全部照片」要自动缩放到所有照片都看得见（用户 2026-10-07 的要求）
  chk(/function zoomToAllPhotos\(/.test(html), '有 zoomToAllPhotos()');
  const zoomFn = extractFn('zoomToAllPhotos');
  chk(/L\.latLngBounds\(\[\]\)/.test(zoomFn), '按所有照片点求外接矩形');
  chk(/photoGroups/.test(zoomFn), '遍历的就是 `photoGroups`（画在地图上的那批）');
  chk(/bounds\.extend\(\[lat,lon\]\)/.test(zoomFn), '每个点都 extend 进去');
  chk(/map\.fitBounds\(bounds,\{padding:\[30,30\],maxZoom:TRACK_FIT_MAX_ZOOM,animate:false\}\)/.test(zoomFn),
    'fitBounds 带 padding / maxZoom 上限 / animate:false');
  // animate:false 不是可有可无：开着动画时（无头环境或浏览器偏好减少动画）
  // fitBounds 调了、返回 true，但 zoom 与中心完全没变 —— 实测踩过。
  chk(/animate:false/.test(zoomFn),
    'animate:false（否则这一下可能停在动画中间态，视图看着完全没动）');
  chk(/setPhotoLayer\(true\);[\s\S]{0,80}zoomToAllPhotos\(\);/.test(html),
    '点按钮先点亮图层、再缩放到全部照片');

  // 展示区挪到右栏（视频与标记点之间，占标记点上方那半截）
  const rightCol = html.slice(html.indexOf('<section class="col col-right"'),
                              html.indexOf('id="keyModal"'));
  chk(/id="photoCard"/.test(rightCol), '照片展示区在右栏里');
  // 标记点卡片已挪到左栏（与项目数据共用一块地方、标签开关切换）——
  // 右栏现在只有视频面板 + 照片展示区
  const iRight = html.indexOf('<section class="col col-right"');
  chk(iRight > 0 && html.indexOf('id="markerCard"') < iRight,
    '标记点卡片在右栏之前（也就是左栏里）',
    `markerCard@${html.indexOf('id="markerCard"')} col-right@${iRight}`);
  // 注意用 `<aside class="col col-left` 做前缀匹配：实际的标签带 view-project 与 id
  const iLeft = html.indexOf('<aside class="col col-left');
  chk(iLeft > 0 && html.indexOf('id="markerCard"') > iLeft,
    '标记点卡片确实在左栏那个 aside 里',
    `aside@${iLeft} markerCard@${html.indexOf('id="markerCard"')}`);
  chk(html.indexOf('id="photoCard"') > html.indexOf('id="videoModal"'),
    '照片展示区仍在视频面板之后（右栏里）');
  chk(!/id="photoCard"[\s\S]{0,20000}id="photoCard"/.test(html), 'photoCard 只有一处');
  // 原来在地图卡片里（.below-map 之前），现在挪到右栏 —— 所以它应当排在
  // altVideos / stats 这些「地图下面的次要内容」之后。
  chk(html.indexOf('id="photoCard"') > html.indexOf('id="altVideos"'),
    '已从地图卡片里挪走（不再位于 altVideos 之前）');
  chk(/\.col-right:has\(\.photo-card\[style\*="display: block"\]\) \.marker-card/.test(html),
    '右栏里两者按 :has() 分高度（照片区 : 标记点 = 3 : 2）');
  chk(/\.photo-card\{display:none;flex:1 1 auto;min-height:300px/.test(html),
    '展示区 flex:1 1 auto（右栏剩余高度基本都给它，按内容长）');
  chk(/--marker-flex:0 1 130px/.test(html),
    '标记点卡片让到 130px（用户说「不一定用得到标记点和导出」）');
  chk(/\.col-right:has\(\.photo-card/.test(html), '用 :has() 判断展示区是否开着');
  // 画廊必须是「左右分栏」：不换行 + 两边按比例伸缩
  const gal = (html.match(/\.photo-gallery\{[^}]*\}/) || [''])[0];
  chk(/flex-wrap:nowrap/.test(gal), '画廊不换行（换行就会变成上下分栏）');
  chk(!/flex-wrap:wrap/.test(gal), '画廊没有 wrap');
  chk(/\.photo-lead\{flex:2\.6 1 0/.test(html), '大图在左：flex:2.6 1 0');
  chk(/\.photo-thumbs\{flex:1 1 0;display:flex;flex-direction:column/.test(html),
    '小图在右：flex:1 1 0，竖着排');
  chk(/\.photo-shot img\{display:block;max-width:100%;height:auto/.test(html),
    '图片只给 max-width + height:auto（不定宽、不定高，避免黑框也不溢出）');
  chk(/id="photoCard"/.test(html), '有地图下方的展示区容器');
  chk(/id="photoGallery"/.test(html), '展示区里有图片区');
  chk(/id="photoJump"/.test(html), '展示区里有「跳视频」那块');
  chk(/photoLayerBtn\.addEventListener\('click',\(\)=>\{/.test(html),
    '开关接线到一个处理函数（点它加载 + 缩放，再点收起）');
  chk(/if\(photoLayerOn\)\{\s*setPhotoLayer\(false\);/.test(html),
    '已经显示时再点一次收起图层');
  chk(/setPhotoLayer\(true\);\s*zoomToAllPhotos\(\)/.test(html),
    '从关到开这一下会顺便缩放到全部照片');
  chk((html.match(/photoLayerBtn\.addEventListener/g) || []).length === 1, '开关的监听只挂一次');
  chk((html.match(/photoCloseBtn\.addEventListener/g) || []).length === 1, '收起按钮的监听只挂一次');
  chk((html.match(/loadProjectPhotos\(\)/g) || []).length >= 3,
    '换项目 / 载入项目 / 导入之后都会刷新照片',
    String((html.match(/loadProjectPhotos\(\)/g) || []).length) + ' 处');

  // 「非实测」必须走 ⚠ 角标，而不是换一种颜色的点（用户 2026-10-06 明确要求的）
  // 「位置不准」必须是一个合并的标记：黄点 + 圆里的叹号（用户 2026-10-07 定）
  chk(/\.photo-div-icon\.photo-warn \.photo-dot\{fill:var\(--photo-warn-dot,#f5b301\)\}/.test(html),
    '「位置不准」的点本身是黄点（不是外面再挂一个三角）');
  chk(/\.photo-div-icon \.photo-dot-mark\{fill:#1f2937\}/.test(html), '叹号画在圆里面（.photo-dot-mark）');
  chk(!/photo-warn-mark/.test(html), '旧的 ⚠ 角标（外面挂三角）已经去掉');
  chk(!/photo-warn[^}]*background:#fde68a/.test(html), '也没有退回到「黄色小圆点」那套');

  // 展示区现在在右栏（2026-10-07 用户要求挪过去），不在中栏地图下面了
  chk(html.indexOf('id="photoCard"') > html.indexOf('class="col col-mid"'),
    '展示区不在中栏（地图卡片）里');
  chk(/<section class="col col-right"[\s\S]*id="photoCard"/.test(html),
    '展示区在右栏里（与视频 / 标记点同栏）');
}

console.log('\n=== 9) 点某张照片该播哪一路（这条错过一次：点 _V 跳成了 _S）===');
{
  // 照片与视频的序号是各自计数、通常对不上：
  //   照片 DJI_20260924095348_0002_V.JPG（同架次第 2 张）
  //   视频 DJI_20260924095258_0001_V.MP4（同架次第 1 段）
  // 所以**不能**按整个文件名前缀配对，要按末尾的流标识 _V/_T/_S。
  const V = { video: 'DJI_20260924095258_0001_V.MP4', relativePath: 'DJI_20260924095258_0001_V.MP4' };
  const T = { video: 'DJI_20260924095258_0001_T.MP4', relativePath: 'DJI_20260924095258_0001_T.MP4' };
  const S = { video: 'DJI_20260924095258_0001_S.MP4', relativePath: 'DJI_20260924095258_0001_S.MP4' };
  // 候选顺序按「画面内 / 时间差」排，S 排第一是常有的事
  const matches = [S, T, V];

  chk(page.streamTagOf('DJI_20260924095348_0002_V.JPG') === 'V', '取照片的流标识 V');
  chk(page.streamTagOf('DJI_20260924095258_0001_T.MP4', /\.(MP4|MOV)$/i) === 'T', '取视频的流标识 T');
  chk(page.streamTagOf('没有后缀.jpg') === '', '认不出来就返回空串');

  chk(page.pickMatchForPhoto(matches, 'DJI_20260924095348_0002_V.JPG') === V,
    '点 _V 照片 -> 挑 _V 视频（不能因为 S 排在前面就跳到 S）');
  chk(page.pickMatchForPhoto(matches, 'DJI_20260924095348_0002_T.JPG') === T,
    '点 _T 照片 -> 挑 _T 视频');
  chk(page.pickMatchForPhoto([T, V], 'DJI_20260924095348_0002_V.JPG') === V, '顺序无关，按标识配对');

  // 该流不在候选中时：退回「同一架次」（时间戳一致、序号不同也算）
  const noV = [S, T];
  chk(page.pickMatchForPhoto(noV, 'DJI_20260924095348_0002_V.JPG') === S,
    '没有 _V 候选时退回同一架次的第一条（时间戳一致，序号不同也算）');
  const otherFlight = [{ video: 'X_20260924090000_0009_V.MP4', relativePath: 'X_20260924090000_0009_V.MP4' }];
  chk(page.pickMatchForPhoto(otherFlight, 'DJI_20260924095348_0002_V.JPG') === otherFlight[0],
    '连同一架次都没有时，退回排序最好的那条（至少时刻是对）');

  chk(page.pickMatchForPhoto([], 'a_V.JPG') === null, '没有候选时返回 null');
  chk(page.pickMatchForPhoto(null, 'a_V.JPG') === null, '候选不是数组也返回 null');

  // 源码层面也要盯住：不能再退回「按整前缀配」那套
  const fn = extractFn('openPhotoVideo');
  chk(/pickMatchForPhoto\(matches,target\)/.test(fn), 'openPhotoVideo 用 pickMatchForPhoto 挑');
  chk(/pickMatchForPhoto\(fresh,target\)/.test(fn), '「还没匹配」那条兜底路径也用它（不再直接跳 fresh[0]）');
  chk(/members\[0\]&&members\[0\]\.name/.test(fn),
    '没给名字时用领衔照片兜底（否则空名字等于没有流标识，又会退回 matches[0]）');

  // 大图（.photo-lead-shot）也**必须**带 data-photo-name。
  // 这条漏过一次，表现就是用户报的「点热成像照片，跳出来的是可见光视频」：
  // 大图没有名字 -> 流标识为空 -> 只能退回 matches[0]。
  // 实测：147 组里 26 组的大图就是热成像照片，其中 20 组会跳错。
  // 注：从 2026-10-07 起大图先按「变焦 > 广角 > 热成像」挑（见 9b 节），
  // 所以这一组（V 变焦 + T 热成像）的大图是那张 V；这组断言改成
  // 「大图带的是它自己那张（也就是 V）的名字」。
  {
    const g = { members: [
      { name: 'DJI_20260924102325_0026_T.JPG', folder: 'D:\\d', camera: 'InfraredCamera', accuracy: '实测' },
      { name: 'DJI_20260924102325_0026_V.JPG', folder: 'D:\\d', camera: 'ZoomCamera', accuracy: '实测' },
    ] };
    const gh = page.photoGalleryHtml(g);
    const figs = gh.match(/<figure[^>]*>/g) || [];
    chk(figs.length === 2, '两张照片两个 figure', String(figs.length));
    chk(figs.every(f => /data-photo-name="DJI_/.test(f)),
      '每个 figure（**含大图**）都带 data-photo-name',
      figs.map(f => (f.match(/class="([^"]*)"/) || [])[1] || f.slice(0, 40)).join(' | '));

    const leadName = (gh.match(/photo-lead-shot"[\s\S]{0,80}?data-photo-name="([^"]+)"/) || [])[1] || '';
    chk(leadName === 'DJI_20260924102325_0026_V.JPG',
      '大图带的是它自己那张的名字（这一组按规则挑了可见光 V）', leadName || '(缺)');

    // 把大图的名字喂给 pickMatchForPhoto：必须挑同一路的 _V
    const Vc = { video: 'DJI_20260924095258_0001_V.MP4', relativePath: 'DJI_20260924095258_0001_V.MP4' };
    const Tc = { video: 'DJI_20260924095258_0001_T.MP4', relativePath: 'DJI_20260924095258_0001_T.MP4' };
    chk(page.pickMatchForPhoto([Tc, Vc], leadName) === Vc,
      '点大图（可见光 V）-> 挑 _V 视频（候选里 _T 排第一也不动摇）');
    chk(page.pickMatchForPhoto([Vc, Tc], '') === Vc,
      '名字为空时确实会退化成第一条（这正是当初出错的路径，所以名字不能缺）');
  }
}

console.log('\n=== 9b) 大图挑法与跳转优先级：可见光变焦 > 可见光广角 > 热成像 ===');
{
  const mk = (camera, name) => ({ camera, name });
  const T = mk('InfraredCamera', 'a_0020_T.JPG');
  const W = mk('WideCamera', 'a_0020_V.JPG');
  const Z = mk('ZoomCamera', 'a_0020_V.JPG');
  const g = (...ms) => ({ members: ms });

  chk(page.photoCameraRank(Z) < page.photoCameraRank(W), '变焦排在广角前面');
  chk(page.photoCameraRank(W) < page.photoCameraRank(T), '广角排在热成像前面');
  chk(page.photoCameraRank(mk('Unknown', 'x')) === 9, '认不出的相机排最后');

  chk(page.photoLeadMember(g(T, Z)) === Z, '变焦 + 热成像 -> 大图取变焦（喂进来的顺序无关）');
  chk(page.photoLeadMember(g(Z, T)) === Z, '顺序反过来也一样');
  chk(page.photoLeadMember(g(T, W)) === W, '广角 + 热成像 -> 大图取广角');
  chk(page.photoLeadMember(g(T, W, Z)) === Z, '三张都有 -> 大图取变焦');
  chk(page.photoLeadMember(g(T)) === T, '只有热成像 -> 就只能用它');
  chk(page.photoLeadMember({ members: [] }) === null, '空组返回 null');
  chk(page.photoLeadMember(null) === null, '没有组也返回 null');

  // 大图给了 V，照片墙里第一张（大图位）也得是它
  const gh = page.photoGalleryHtml(g(T, Z));
  const leadName = (gh.match(/photo-lead-shot"[\s\S]{0,80}?data-photo-name="([^"]+)"/) || [])[1] || '';
  chk(leadName === Z.name, '照片墙的大图位就是 photoLeadMember 挑的那张', leadName || '(缺)');
  chk(/photo-thumb" data-photo-name="a_0020_T\.JPG"/.test(gh), '另一张（热成像）当小图');

  // 跳转候选：和大图同一路的排第一（否则会出现「大图可见光、最接近写热成像」）
  const Vv = { video: 'x_V.MP4', relativePath: 'x_V.MP4' };
  const Sv = { video: 'x_S.MP4', relativePath: 'x_S.MP4' };
  const Tv = { video: 'x_T.MP4', relativePath: 'x_T.MP4' };
  const ordered = page.orderMatchesForLead([Tv, Sv, Vv], g(T, Z));
  chk(ordered[0] === Vv, '大图是 V -> 候选第一条是 V 视频',
    ordered.map(m => m.relativePath).join(','));
  chk(ordered[1] === Tv && ordered[2] === Sv, '其余保持原来的先后（画面内/时间差顺序不变）',
    ordered.map(m => m.relativePath).join(','));
  chk(page.orderMatchesForLead([Tv, Vv], g(T)).length === 2, '大图只有热成像时也照原样返回');
  chk(page.orderMatchesForLead([Tv, Vv], g(T))[0] === Tv, '大图是 T -> 第一条仍是 T（没有 V 就不硬凑）');
  chk(page.orderMatchesForLead([Tv], g(T, Z))[0] === Tv, '只有一条候选时原样返回');
  chk(page.orderMatchesForLead([], g(T, Z)).length === 0, '空候选返回空');

  const fn = extractFn('selectPhotoGroup');
  chk(/matches=orderMatchesForLead\(matches,group\)/.test(fn),
    '渲染前会把候选按「大图那一路」重排');
  chk(/photoMatches\.set\(index,matches\)/.test(fn),
    '排完再缓存 —— 按钮的 data-photo-match 下标必须和它同一个顺序');
}

console.log('\n=== 10) 点照片跳视频：倒退 3 秒起播 + 3-2-1 倒计时 + 到照片时刻自动暂停 ===');
{
  const { cd } = page;
  const P = Number(consts.PHOTO_PREROLL_SECONDS);
  chk(P === 3, '倒退秒数是 3（用户先让用 3 秒试）', String(P));

  // 起播位置：照片时刻往前 3 秒
  chk(/const photoAt=Math\.max\(0,Number\(m\.startSeconds\)\|\|0\)/.test(extractFn('jumpToPhotoVideo')),
    'jumpToPhotoVideo 先算出照片时刻');
  const jump = extractFn('jumpToPhotoVideo');
  chk(/const from=Math\.max\(0,photoAt-PHOTO_PREROLL_SECONDS\)/.test(jump),
    '起播位置 = 照片时刻 - PHOTO_PREROLL_SECONDS（不早于 0）');
  chk(/video_start:from/.test(jump), '发出去的是倒退后的时间（video_start）');
  chk(/photo_pause_at:from<photoAt\?photoAt:0/.test(jump),
    '并把「照片那一刻」一起发出去（photo_pause_at；开头没有余量时发 0 = 不倒计时）');

  // 目标时刻：走转码片段时 <video> 的时间轴从片段头算起，必须减掉 bucket
  cd.setTarget(489, 0);
  chk(cd.getTarget() === 489, '原片：目标时刻就是照片时刻', String(cd.getTarget()));
  cd.setTarget(489, 480);
  chk(cd.getTarget() === 9, '转码片段：目标时刻要减掉片段起点（489 - 480 = 9）',
    String(cd.getTarget()));
  cd.setTarget(0, 0);
  chk(cd.getTarget() === null, '照片就在视频开头（没有可倒退的余量）时不倒计时');

  // 倒计时数字 = 还剩多少视频时间（上限就是倒退的秒数）
  cd.setTarget(489, 480);          // 目标 9
  cd.player.paused = false;
  const at = (t) => { cd.player.currentTime = t; cd.update(); return cd.countdown; };
  chk(at(6.9).hidden === false && at(6.9).textContent === '3', '还剩 2.1 秒时显示 3');
  chk(at(7.5).textContent === '2', '还剩 1.5 秒时显示 2');
  chk(at(8.2).textContent === '1', '还剩 0.8 秒时显示 1（不出现 0）');
  chk(at(5.0).textContent === '3', '再往前也不超过 3（倒退只有 3 秒）');
  chk(at(9).hidden === true, '到了目标时刻就不再显示数字');
  cd.player.paused = true;
  chk(at(7.0).hidden === true, '暂停时不显示倒计时');

  // 到点自动暂停：时间要卡准（timeupdate 只有 ~4Hz，必须靠每帧查）
  cd.setTarget(489, 480);
  cd.player.paused = false;
  cd.player.currentTime = 9.4;     // 已经冲过目标
  const pausedBefore = cd.player._paused;
  cd.tick();
  chk(cd.player._paused === pausedBefore + 1, '冲过目标时调用 pause()');
  chk(cd.player.currentTime === 9, '并把画面精确停在照片那一帧上（不冲过去）',
    String(cd.player.currentTime));
  chk(cd.getTarget() === null, '暂停后清掉待办（不会反复暂停）');
  chk(cd.countdown.hidden === true, '暂停后倒计时收起来');
  chk(/自动暂停/.test(cd.status.textContent), '状态栏说明「已到照片拍摄时刻，自动暂停」',
    cd.status.textContent);

  // 还没到点时不能动
  cd.setTarget(489, 480);
  cd.player.paused = false;
  cd.player.currentTime = 8.0;
  const before2 = cd.player._paused;
  cd.tick();
  chk(cd.player._paused === before2, '没到点时不暂停');
  chk(cd.getTarget() === 9, '待办还在');

  // 关掉视频 / 用户自己暂停时要撤掉待办
  cd.stop();
  chk(cd.getTarget() === null && cd.countdown.hidden === true, 'stop() 清干净待办与倒计时');
  const pauseHandler = html.slice(html.indexOf("videoPlayer.addEventListener('pause'"),
                                      html.indexOf("videoPlayer.addEventListener('pause'") + 320);
  chk(/!photoPauseByUs\)stopPhotoCountdown\(\)/.test(pauseHandler),
    '用户自己按暂停时撤掉待办（免得他再点播放又被停住）');
  // 每帧查一次：不能只挂 timeupdate
  chk(/tickPhotoPause\(\);/.test(html.slice(html.indexOf('function frame(now)'),
                                          html.indexOf('function frame(now)') + 700)),
    'rAF 每帧都查一次（timeupdate 只有约 4Hz，靠它会冲过目标）');
  chk(!/id="videoCountdown"[^>]*class="[^"]*video-status/.test(html),
    '倒计时是独立浮层（不是复用状态文字）');
}

console.log('\n=== 11) 遥测请求必须带对参数（这条错了，画面内判定会 147/147 全空）===');(async () => {
  // 真实的挫败场景：/api/project/telemetry 要 name + folder_index + path（相对路径、.mp4）。
  // 早先 ensureTrackTelemetry 只传 path，而且传的是航迹自己的 .geojson 相对路径 ——
  // 后端先回「缺少项目名称」，补上 name 后又回「指定文件不是 MP4/MOV 视频」。
  // 遥测一条都取不到时，photoMatchesFor 会**全部**提前返回空（界面上就是
  // 「没有找到时间对得上的视频」），A+B 检索也只剩「无人机位置最近」。
  // 参数拼装抽在 telemetryQuery 里，所以断言直接对着它。
  const fn = extractFn('ensureTrackTelemetry');
  const qf = extractFn('telemetryQuery');

  chk(/name:String\(projectName/.test(qf), '带了 name（项目名）');
  chk(/folder_index:String\(info&&info\.folder_index\)/.test(qf), '带了 folder_index');
  chk(/videoPathFromGeojson\(info&&info\.relative_path\)/.test(qf),
    'path 走 videoPathFromGeojson 换成 .mp4（不能直接送 .geojson）');
  chk(/telemetryQuery\(info,projectSelect\.value\)/.test(fn), '请求时用当前项目名拼参数');
  chk(!/path=.*encodeURIComponent\(path\)/.test(fn), '不再用「拼好的绝对路径」当 path');

  // 缓存键也要带上 folder_index：两个架次下可能有同名文件
  chk(/const key=info\.folder_index\+'\|\'\+rel/.test(fn), '缓存键按「文件夹下标 + 相对路径」');
  chk(/if\(ok\)t\.telemetry=ok/.test(fn), '取到后挂回航迹对象（检索是同步函数，只能这样取）');

  // trackVideoPath 仍然要给照片跳视频用，且必须也是 .mp4
  const tv = extractFn('trackVideoPath');
  chk(/videoPathFromGeojson\(info\.relative_path\)/.test(tv),
    'trackVideoPath 也把 .geojson 换成 .mp4（/api/project/video 同样只收 MP4）');

  // 候选构造必须把 .geojson 换成 .mp4 —— 这条错过一次：按钮能点，
  // 一按就是红字「指定文件不是 MP4/MOV 视频」，播放器全黑。
  const pmf = extractFn('photoMatchesFor');
  chk(/const videoRel=track\.video\|\|videoPathFromGeojson\(clip\.info\.relative_path\)/.test(pmf),
    '候选的路径是视频路径（.mp4），不是航迹的 .geojson');
  chk(/relativePath:videoRel/.test(pmf), 'relativePath 用的是换算后的视频路径');
  chk(!/relativePath:String\(clip\.info\.relative_path\)/.test(pmf),
    '没有把 clip.info.relative_path（.geojson）直接当 relativePath');

  // 真实数据那一层现在能拿到遥测了，就该有「画面内」命中；
  // 这条断言把「遥测取不到 -> 全都不是画面内」这种退化情形也挡住。
  chk(/inFrame === true/.test(fs.readFileSync(__filename, 'utf8')),
    '测试自身保留了「真实数据里必须判出画面内」的断言');

  // 参数拼装抽出来单独测（光看源码文本不够：要能真的断言拼出来的东西）
  const info = { folder_index: 1, relative_path: 'DJI_20260924101516_0001_V.geojson' };
  const q = page.telemetryQuery(info, '东莞1');

  chk(q.name === '东莞1', 'name = 项目名', q.name);
  chk(q.folder_index === '1', 'folder_index 是字符串形式的下标', q.folder_index);
  // 只有扩展名大小写不敏感：videoPathFromGeojson 统一产出小写 .mp4，
  // Windows 路径不分大小写、后端也照 .lower() 判，所以这是对的。
  chk(q.path.toLowerCase() === 'dji_20260924101516_0001_v.mp4',
    'path = 相对路径且已换成 .mp4（后端只认 MP4/MOV）', q.path);
  chk(!/^[A-Za-z]:/.test(q.path), 'path 是相对路径，不是绝对路径');
  chk(String(page.telemetryQuery({ folder_index: 0, relative_path: 'a.3d.geojson' }, 'x').path).toLowerCase() === 'a.mp4',
    '.3d.geojson 也能正确换成 .mp4');

  // 真的去问一次运行中的服务：这条断言挡的是「参数对但接口实际会拒」这类问题。
  // 服务没起时明确跳过，不算失败（测试不该依赖开发服务在跑）。
  await (async () => {
    const base = process.env.PHOTO_TEST_SERVER || 'http://127.0.0.1:8000';
    let alive = false;
    try {
      const r = await fetch(base + '/api/project/list', { signal: AbortSignal.timeout(2000) });
      alive = r.ok;
    } catch (e) { alive = false }

    if (!alive) {
      console.log('  [SKIP] 开发服务没在跑，跳过真实接口验证（起服务后再跑就能验到）');
      return;
    }

    // ---- 分组规则（2026-10-07 改成「同一文件夹 + 同一序号」）----
    // 一次按快门出一张 V 与一张 T，序号相同；但文件名时刻可能差 1 秒
    // （T 文件小先写完、V 大后写完）。旧键「同一秒」会拆错 26 个序号、并错 1 组。
    try {
      const r = await fetch(base + '/api/project/photos?name=' + encodeURIComponent('东莞1'),
                            { signal: AbortSignal.timeout(120000) });
      const d = await r.json().catch(() => null);
      const groups = (d && d.groups) || [];

      chk(r.ok && groups.length > 0, '真实接口给出照片分组',
        groups.length ? `${groups.length} 组 / ${d.counts.photos} 张` : `HTTP ${r.status}`);

      const tagOf = (n) => (String(n).match(/_([A-Za-z]+)\.JPG$/i) || [, ''])[1].toUpperCase();
      const seqOf = (n) => (String(n).match(/DJI_\d{8}\d{6}_(\d+)_/) || [, ''])[1];

      // ① 每组都是「一张 V + 一张 T」（不再是 97 组对 + 50 组单张）
      const sizes = {};
      for (const g of groups) sizes[g.count] = (sizes[g.count] || 0) + 1;
      chk(Object.keys(sizes).length === 1 && Number(Object.keys(sizes)[0]) === 2,
        '每组都是 2 张（T+V 成对）', JSON.stringify(sizes));

      const combos = new Set(groups.map(g => g.members.map(m => tagOf(m.name)).sort().join('+')));
      chk(combos.size === 1 && combos.has('T+V'),
        '每组的成员都是「_V + _T」', [...combos].join(' / '));

      // ② 每组的大图都是 _V（顺序：变焦 > 广角 > 热成像）
      const notV = groups.filter(g => tagOf(g.members[0].name) !== 'V');
      chk(notV.length === 0, '每组的第一张（大图）都是 _V',
        notV.length ? notV.slice(0, 3).map(g => g.members[0].name).join(', ') : '');

      // ③ 序号不再被拆到两个组里
      const seen = new Map();
      let dup = 0;
      for (let i = 0; i < groups.length; i++) {
        for (const m of groups[i].members) {
          const k = m.folder + '|' + seqOf(m.name);
          if (seen.has(k) && seen.get(k) !== i) dup++;
          seen.set(k, i);
        }
      }
      chk(dup === 0, '同一文件夹 + 同一序号只出现在一个组里（不再拆错）', dup + ' 处重复');

      // ④ 组数 = 照片数 / 2，且升序（前端按这个顺序编号「第 N / M 个目标点」）
      chk(groups.length * 2 === d.counts.photos,
        '组数 = 照片数 / 2', `${groups.length} 组 / ${d.counts.photos} 张`);
      chk(d.counts.merged === groups.length, '统计里的「合并」数 = 组数（每组都合并了 2 张）',
        String(d.counts.merged));
      const stamps = groups.map(g => g.stamp);
      chk(stamps.join() === stamps.slice().sort().join(), '组按时刻升序（前端的第 N 个点才对得上时间）');

      // ⑤ 跨秒的那一对要真的合成一组（0020：10:01:45 的 V + 10:01:46 的 T）
      const pair0020 = groups.find(g => g.members.some(m => /_0020_/.test(m.name) && /10014/.test(m.name)));
      chk(!!pair0020 && pair0020.members.length === 2,
        '差 1 秒的那一对（_V 10:01:45 + _T 10:01:46）合成了一组',
        pair0020 ? pair0020.members.map(m => m.name).join(' + ') : '(找不到)');

      // ⑥ 组内解算点间距只记录不拆组：有 3 组 > 8 m
      const far = groups.filter(g => Number(g.spread_m) > 8);
      chk(far.length >= 1 && groups.length > far.length,
        '组内间距 > 8m 的组仍然保留（只记 spread_m，不拿它拆组）',
        `${far.length} 组，最大 ${Math.max(...groups.map(g => Number(g.spread_m) || 0)).toFixed(1)} m`);
    } catch (e) {
      chk(false, '真实分组接口请求没抛异常', e.message);
    }

    const url = base + '/api/project/telemetry?' + new URLSearchParams(
      page.telemetryQuery({ folder_index: 0, relative_path: 'DJI_20260924095258_0001_V.geojson' }, '东莞1')
    ).toString();

    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(30000) });
      const d = await r.json().catch(() => null);
      chk(r.ok, '真实接口返回 200（参数确实是它要的那三个）',
        r.ok ? '' : `HTTP ${r.status} ${d && d.error ? d.error : ''}`);
      chk(!!(d && d.times && d.times.length), '返回里有 times（抽稀后的遥测）',
        d && d.times ? `${d.times.length} 条, step=${d.step}` : '-');
      chk(!!(d && d.step >= 1), '带上了 step（下标换算要用）', d ? String(d.step) : '-');
    } catch (e) {
      chk(false, '真实接口请求没抛异常', e.message);
    }
  })();
})().then(() => {
  // 最后一节是异步的（要问一次真实服务），收尾放进 then ——
  // 否则 process.exit 会先跑，异步断言还没来得及判定。
  console.log(`\n结果: ${ok ? '全部通过' : '有失败项'}`);
  process.exit(ok ? 0 : 1);
});
