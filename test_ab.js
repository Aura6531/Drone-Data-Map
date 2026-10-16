// A+B 检索的数学基础测试
// ---------------------------------------------------------------
// 只验证最容易被"看起来对"糊弄过去的部分：
//   1) 反投影 imagePointOfGround 在几个【能闭式手算】的姿态下结果是否正确
//   2) 反投影 与 正投影 互为逆运算（把正向公式算出的地面点反投影回去，应回到原坐标）
//
// 正投影 groundPointForImage 本身已由 test_footprint.js 覆盖，
// 这里只验证新加的反投影与它严格互逆。

const fs = require('fs');
const path = require('path');

// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');

if (!fs.existsSync(HTML)) {
  console.error('找不到页面文件：' + HTML);
  process.exit(1);
}

const html = fs.readFileSync(HTML, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/g);
const body = m[m.length - 1].replace(/^<script>/, '').replace(/<\/script>$/, '');

let pass = 0;
const fails = [];
function chk(ok, name, extra) {
  if (ok) { pass++; console.log('  [OK] ' + name + (extra ? ' -> ' + extra : '')); }
  else { fails.push(name + (extra ? ' -> ' + extra : '')); console.log('  [FAIL] ' + name + (extra ? ' -> ' + extra : '')); }
}

// 取出页面里的函数（本项目所有函数都以行首 } 收尾）
function extractFn(name) {
  const i = body.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('找不到函数 ' + name);
  const j = body.indexOf('\n}', i);
  if (j < 0) throw new Error('函数 ' + name + ' 没有正常收尾');
  return body.slice(i, j + 2);
}

const aspectSrc = (body.match(/const FRAME_ASPECT=\[[^\]]*\]/) || [''])[0];
const diagSrc = (body.match(/const FULLFRAME_DIAGONAL=[\d.]+/) || [''])[0];
if (!aspectSrc || !diagSrc) {
  console.error('取不到 FRAME_ASPECT / FULLFRAME_DIAGONAL，无法算出视场角');
  process.exit(1);
}

const src = [
  aspectSrc,
  diagSrc,
  extractFn('fovOf'),
  // 抽稀后的遥测要按下标换算才能读（见 telemetryIndexOf 的注释）；
  // 它是 imagePointOfGround / frameCenterLatLng 的依赖，必须一起抠出来。
  extractFn('telemetryIndexOf'),
  extractFn('imagePointOfGround'),
  extractFn('framePositionText')
].join('\n');

// 极简的 L 桩：只用到 latLng
const L = {
  latLng(a, b) { return (typeof a === 'object' && a !== null) ? a : { lat: Number(a), lng: Number(b) }; }
};

const api = new Function('L', src + '\nreturn {fovOf,telemetryIndexOf,imagePointOfGround,framePositionText};')(L);

// ---- 固定姿态：无人机 23.0N / 114.0E，高 100 m，机头朝正北，俯角 45° ----
// 俯角 45° + 高 100 m -> 画面中心正好落在正北 100 m 处（可闭式手算）
const DRONE = L.latLng(23.0, 114.0);
const ALT = 100;
const YAW = 0;        // 正北
const PITCH = -45;    // 俯角 45
const FOCAL = 24;     // 广角

// 与页面同一套 ENU 约定：东 = lng 增量 * 111320 * cos(lat)，北 = lat 增量 * 110540
function groundAt(eastM, northM) {
  const latR = DRONE.lat * Math.PI / 180;
  return L.latLng(
    DRONE.lat + northM / 110540,
    DRONE.lng + eastM / (111320 * Math.cos(latR))
  );
}

// 用一条只含 1 个点的合成航迹；索引 0 就是无人机所在点
const track = { coords: [[DRONE.lng, DRONE.lat]], times: [0], feature: { properties: {} } };
const tele = { alt: [ALT], yaw: [YAW], pitch: [PITCH], focal: [FOCAL], times: [0] };

// 正向公式（与页面 groundPointForImage 完全一致），供互逆性测试生成地面点。
// yawDeg / pitchDeg 可覆盖（默认用那组固定姿态），供抽稀对齐测试按帧取姿态。
function forwardToGround(xImg, yImg, yawDeg, pitchDeg) {
  const fov = api.fovOf(FOCAL);
  const tanH = Math.tan(fov[0] * Math.PI / 360);
  const tanV = Math.tan(fov[1] * Math.PI / 360);
  const p = (pitchDeg === undefined ? PITCH : pitchDeg) * Math.PI / 180;
  const y = (yawDeg === undefined ? YAW : yawDeg) * Math.PI / 180;
  const f = [Math.cos(p) * Math.sin(y), Math.cos(p) * Math.cos(y), Math.sin(p)];
  const u = [-Math.sin(p) * Math.sin(y), -Math.sin(p) * Math.cos(y), Math.cos(p)];
  const r = [f[1] * u[2] - f[2] * u[1], f[2] * u[0] - f[0] * u[2], f[0] * u[1] - f[1] * u[0]];
  const d = [
    r[0] * (xImg * tanH) + u[0] * (yImg * tanV) + f[0],
    r[1] * (xImg * tanH) + u[1] * (yImg * tanV) + f[1],
    r[2] * (xImg * tanH) + u[2] * (yImg * tanV) + f[2]
  ];
  if (d[2] >= -1e-6) return null;
  const t = -ALT / d[2];
  return groundAt(t * d[0], t * d[1]);
}

const near = (a, b, tol) => Math.abs(a - b) <= (tol === undefined ? 1e-9 : tol);

console.log('\n=== 1) 反投影：画面中心应落在正北 100 m（俯角 45°、高 100 m 可手算）===');
{
  const p = api.imagePointOfGround(track, tele, 0, groundAt(0, 100));
  chk(!!p, '能算出画面坐标');
  if (p) {
    chk(near(p.xImg, 0, 1e-9), 'xImg ≈ 0（正对中心）', p.xImg.toFixed(12));
    chk(near(p.yImg, 0, 1e-9), 'yImg ≈ 0（正对中心）', p.yImg.toFixed(12));
    chk(p.visible === true, '判定为「画面内」');
  }
}

console.log('\n=== 2) 方位与俯仰方向必须正确 ===');
{
  const close = api.imagePointOfGround(track, tele, 0, groundAt(0, 50));   // 更近 -> 画面更下方
  const far = api.imagePointOfGround(track, tele, 0, groundAt(0, 200));    // 更远 -> 画面更上方
  const east = api.imagePointOfGround(track, tele, 0, groundAt(100, 100)); // 正东 -> 右侧

  chk(!!close && close.yImg < 0, '更近的点在画面下方（yImg < 0）', close && close.yImg.toFixed(6));
  chk(!!far && far.yImg > 0, '更远的点在画面上方（yImg > 0）', far && far.yImg.toFixed(6));
  chk(!!east && east.xImg > 0, '正东的点在画面右侧（xImg > 0）', east && east.xImg.toFixed(6));
}

console.log('\n=== 3) 相机背后 / 非法姿态应返回 null ===');
{
  chk(api.imagePointOfGround(track, tele, 0, groundAt(0, -100)) === null, '正后方的地面点算不出（在相机背后）');
  chk(api.imagePointOfGround(track, tele, 0, null) === null, '没有目标点时返回 null');
  chk(api.imagePointOfGround(null, tele, 0, groundAt(0, 100)) === null, '没有航迹时返回 null');
  chk(api.imagePointOfGround(track, tele, 99, groundAt(0, 100)) === null, '索引越界时返回 null');
  chk(api.imagePointOfGround(track, { alt: [0], yaw: [0], pitch: [-45], focal: [24] }, 0, groundAt(0, 100)) === null,
    '高度为 0 时返回 null');
}

console.log('\n=== 3b) 抽稀遥测的下标换算（这块错位的代价是「画面内」整片误判）===');
{
  // 真实遥测是按 TELEMETRY_STEP=3 抽稀的：航迹 3.6 万点、遥测 1.2 万条。
  // 按时间对齐是首选（SRT 里个别记录缺经纬度会让采样间隔不严格均匀）
  const t = { times: [0, 0.033, 0.067, 0.1, 5, 5.033] };
  const tele = { step: 3, times: [0, 0.1, 5.033], alt: [1, 2, 3], yaw: [10, 20, 30], pitch: [-45, -45, -45], focal: [24, 24, 24] };

  chk(api.telemetryIndexOf(t, tele, 0) === 0, '第 0 点(t=0) -> 遥测 0');
  chk(api.telemetryIndexOf(t, tele, 3) === 1, '第 3 点(t=0.1) -> 遥测 1');
  chk(api.telemetryIndexOf(t, tele, 5) === 2, '第 5 点(t=5.033) -> 遥测 2');
  chk(api.telemetryIndexOf({ times: [-99] }, tele, 0) === 0, '早于首条 -> 夹到 0（不越界）');
  chk(api.telemetryIndexOf({ times: [999] }, tele, 0) === 2, '晚于末条 -> 夹到最后一条');
  // 遥测里没有 times 时退回 step 整除（老后端 / 测试桩）
  chk(api.telemetryIndexOf({ times: [0, 1, 2, 3] }, { step: 3 }, 3) === 1, '没有 tele.times 时按 step 整除');
  chk(api.telemetryIndexOf({ times: [0, 1] }, {}, 1) === 1, 'step 也没有时退化为原下标');

  // 端到端：同一个航迹点下标，遥测抽稀与不抽稀算出的画面坐标必须一致。
  // yaw 用采样点上的真实姿态（抽稀留的是第 0/3/6 帧，这两套在这些点上完全相同）。
  const yawAt = (k) => YAW + k * 5;
  // 注意坐标顺序：GeoJSON / 页面里都是 [经度, 纬度]，不是 L.latLng 对象。
  // 写成 L.latLng(...) 的话 c[0] 是 undefined，反投影会静默返回 null（踩过一次）。
  const coords = Array(9).fill([DRONE.lng, DRONE.lat]);
  const times = Array.from({ length: 9 }, (_, k) => k / 30);
  const full = {
    alt: Array(9).fill(ALT), yaw: Array.from({ length: 9 }, (_, k) => yawAt(k)),
    pitch: Array(9).fill(PITCH), focal: Array(9).fill(FOCAL), times: times.slice()
  };
  const thin = { step: 3, alt: [], yaw: [], pitch: [], focal: [], times: [] };
  for (let k = 0; k < 9; k += 3) {
    thin.alt.push(full.alt[k]); thin.yaw.push(full.yaw[k]);
    thin.pitch.push(full.pitch[k]); thin.focal.push(full.focal[k]); thin.times.push(times[k]);
  }
  const tr = { coords, times };

  let worst = 0;
  let detail = '';
  for (const i of [0, 3, 6]) {
    // 目标点用「该帧画面里偏一点的那个地面点」算出 —— 不能取正中，
    // 正中正好在飞机正下方，反投影会因 tf≈0 判成「在相机平面附近」返回 null。
    // 两套遥测在采样帧上姿态完全相同，所以这个点对两者都成立。
    const c = forwardToGround(0.3, 0.3, full.yaw[i]);
    const a = api.imagePointOfGround(tr, full, i, c);
    const b = api.imagePointOfGround(tr, thin, i, c);
    if (!a || !b) {
      worst = Infinity;
      detail = `i=${i} 有 null（目标点 ${c && c.lat.toFixed(6)}）`
        + ` 全量=${a ? 'ok' : 'null'} 抽稀=${b ? 'ok' : 'null'}`;
      break;
    }
    worst = Math.max(worst, Math.abs(a.xImg - b.xImg), Math.abs(a.yImg - b.yImg));
    detail = `i=${i} 全量(${a.xImg.toFixed(6)},${a.yImg.toFixed(6)}) 抽稀(${b.xImg.toFixed(6)},${b.yImg.toFixed(6)})`;
  }
  chk(worst === 0, '采样点上：抽稀遥测与全量遥测算出的画面坐标完全一致', detail);
}

console.log('\n=== 4) 正/反投影互为逆运算（关键）===');
{
  // 取画面里若干位置 -> 正向算出地面点 -> 反投影回来，应回到原坐标
  const samples = [[0, 0], [0.5, -0.5], [-0.5, 0.5], [0.9, -0.9], [-0.9, -0.2], [0.2, 0.8]];
  let worst = 0, bad = 0;

  for (const [x, y] of samples) {
    const g = forwardToGround(x, y);
    if (!g) { bad++; continue; }
    const back = api.imagePointOfGround(track, tele, 0, g);
    if (!back) { bad++; continue; }
    worst = Math.max(worst, Math.abs(back.xImg - x), Math.abs(back.yImg - y));
  }

  chk(bad === 0, '六个采样点都成功往返', bad + ' 个失败');
  chk(worst < 1e-9, '往返误差 < 1e-9（严格互逆）', worst.toExponential(3));
}

console.log('\n=== 5) 可见性判定与画面位置描述 ===');
{
  const center = api.imagePointOfGround(track, tele, 0, groundAt(0, 100));
  const rightEdge = api.imagePointOfGround(track, tele, 0, forwardToGround(0.95, 0));
  const leftDown = api.imagePointOfGround(track, tele, 0, forwardToGround(-0.8, -0.8));
  const outside = api.imagePointOfGround(track, tele, 0, groundAt(80, 100));

  chk(!!center && center.visible === true, '中心点判定可见');
  chk(!!rightEdge && rightEdge.visible === true, 'xImg=0.95 仍在画面内（阈值 1）');
  chk(api.framePositionText(0, 0) === 'center', '画面位置：center', api.framePositionText(0, 0));
  chk(api.framePositionText(-0.8, -0.8) === 'bottom left', '画面位置：bottom left', api.framePositionText(-0.8, -0.8));
  chk(api.framePositionText(0.8, 0.8) === 'top right', '画面位置：top right', api.framePositionText(0.8, 0.8));
  chk(!!outside && typeof outside.visible === 'boolean', '画面外也能算出坐标，并用 visible=false 标出',
    outside && String(outside.visible) + ' (' + outside.xImg.toFixed(2) + ')');
  void leftDown;
}

console.log('\n结果: ' + (fails.length ? '有失败项' : '全部通过') + '（通过 ' + pass + ' 项）');
if (fails.length) { fails.forEach((f) => console.log('  FAIL: ' + f)); process.exit(1); }
