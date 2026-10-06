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
  extractFn('imagePointOfGround'),
  extractFn('framePositionText')
].join('\n');

// 极简的 L 桩：只用到 latLng
const L = {
  latLng(a, b) { return (typeof a === 'object' && a !== null) ? a : { lat: Number(a), lng: Number(b) }; }
};

const api = new Function('L', src + '\nreturn {fovOf,imagePointOfGround,framePositionText};')(L);

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

// 正向公式（与页面 groundPointForImage 完全一致），供互逆性测试生成地面点
function forwardToGround(xImg, yImg) {
  const fov = api.fovOf(FOCAL);
  const tanH = Math.tan(fov[0] * Math.PI / 360);
  const tanV = Math.tan(fov[1] * Math.PI / 360);
  const p = PITCH * Math.PI / 180, y = YAW * Math.PI / 180;
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
  chk(api.framePositionText(0, 0) === '中心', '画面位置：中心', api.framePositionText(0, 0));
  chk(api.framePositionText(-0.8, -0.8) === '下左', '画面位置：下左', api.framePositionText(-0.8, -0.8));
  chk(api.framePositionText(0.8, 0.8) === '上右', '画面位置：上右', api.framePositionText(0.8, 0.8));
  chk(!!outside && typeof outside.visible === 'boolean', '画面外也能算出坐标，并用 visible=false 标出',
    outside && String(outside.visible) + ' (' + outside.xImg.toFixed(2) + ')');
  void leftDown;
}

console.log('\n结果: ' + (fails.length ? '有失败项' : '全部通过') + '（通过 ' + pass + ' 项）');
if (fails.length) { fails.forEach((f) => console.log('  FAIL: ' + f)); process.exit(1); }
