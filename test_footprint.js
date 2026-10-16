// 验证镜头视场范围（地面覆盖区域）的几何：
// 针孔模型 -> 图像四角射线与地面求交 -> 远边按距离截断
const fs = require('fs');
const path = require('path');

// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');
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
  // a 可以是普通字符串，也可以是 /正则/ —— 用正则是为了不把常量的**数值**写进测试：
  // 之前这里写的是 'const FOOTPRINT_MAX_DISTANCE=300;'，页面把 300 改成 600 之后
  // 锚点就找不到了。数值本来就该从页面里读（下面用了 FOOTPRINT_MAX_DISTANCE 变量）。
  let i;
  if (a instanceof RegExp) {
    const m = a.exec(html);
    if (!m) throw new Error('区间锚点（正则）找不到: ' + a);
    i = m.index;
  } else {
    i = html.indexOf(a);
  }
  const j = html.indexOf(b);
  if (i < 0 || j < 0 || j <= i) throw new Error('区间锚点找不到: ' + a);
  return html.slice(i, j);
}

const consts = extractBetween('const BASE_FOCAL=24;', '// 方位角 ->')
  + '\n' + extractBetween(/const FOOTPRINT_MAX_PER_ALT\s*=\s*\d+;/, 'let footprintLayers=null;');

const src = consts + '\n'
  + extractFn('isInfraredPath') + '\n'
  + extractFn('opticalFocalOf') + '\n'
  + extractFn('offsetLatLng') + '\n'
  + extractFn('groundCenterDistance') + '\n'
  + extractFn('centerGroundLatLng') + '\n'
  + extractFn('fovOf') + '\n'
  + extractFn('groundPointForImage') + '\n'
  + extractFn('edgePointAtDistance') + '\n'
  + extractFn('footprintGeometry');

const L = { latLng: (lat, lng) => ({ lat, lng }) };
const api = new Function('L', src +
  '\nreturn {fovOf,groundPointForImage,edgePointAtDistance,footprintGeometry,'
  + 'offsetLatLng,centerGroundLatLng,opticalFocalOf,'
  + 'FOOTPRINT_MAX_PER_ALT,FOOTPRINT_MAX_DISTANCE_MIN,FRAME_ASPECT};')(L);

const { fovOf, groundPointForImage, footprintGeometry,
        FOOTPRINT_MAX_PER_ALT, FOOTPRINT_MAX_DISTANCE_MIN, FRAME_ASPECT } = api;

// 与页面 footprintGeometry() 里同一套算法：远边截断距离按高度成比例，低空保底
const maxDist = (alt) => Math.max(FOOTPRINT_MAX_DISTANCE_MIN, FOOTPRINT_MAX_PER_ALT * alt);

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

const R = 6371000, rad = (d) => d * Math.PI / 180;
function dist(a, b) {
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function bearing(a, b) {
  const p1 = rad(a.lat), p2 = rad(b.lat), dl = rad(b.lng - a.lng);
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}
function angleDiff(a, b) { let d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; }

const drone = { lat: 23.030, lng: 114.109 };

console.log('=== 1) 视场角：由等效焦距折算，16:9 ===');
{
  const [h, v] = fovOf(24);
  console.log(`    等效 24 mm  ->  水平 ${h.toFixed(2)}°  垂直 ${v.toFixed(2)}°`);
  chk(Math.abs(h - 76.32) < 0.1, '广角水平视场 ≈ 76.32°', h.toFixed(2));
  chk(Math.abs(v - 47.69) < 0.1, '广角垂直视场 ≈ 47.69°', v.toFixed(2));
  chk(Math.abs(Math.tan(rad(h) / 2) / Math.tan(rad(v) / 2) - 16 / 9) < 1e-9,
    '水平/垂直视场比正好是 16:9');

  const [h168, v168] = fovOf(168);
  console.log(`    等效 168 mm ->  水平 ${h168.toFixed(2)}°  垂直 ${v168.toFixed(2)}°`);
  chk(h168 < h / 5, '长焦视场远小于广角', `${h168.toFixed(1)}° vs ${h.toFixed(1)}°`);
  const [h70] = fovOf(70);
  console.log(`    等效 70 mm  ->  水平 ${h70.toFixed(2)}°`);
  // 视场角本身不与焦距成反比，tan(视场角/2) 才与焦距成反比
  chk(Math.abs(Math.tan(rad(h70) / 2) / Math.tan(rad(h) / 2) - 24 / 70) < 1e-9,
    'tan(视场角/2) 与焦距严格成反比（这是针孔模型的定义）');
}

console.log('\n=== 2) 正下视（pitch=-90）：地面应是 157.1 × 88.4 m 的矩形 ===');
{
  const g = footprintGeometry(drone, 100, 0, -90, 0, 24, 1);
  chk(!!g, '能算出视场');
  const nearEdge = dist(g.bl, g.br);
  const sideEdge = dist(g.bl, g.left);
  console.log(`    下边缘长 ${nearEdge.toFixed(2)} m   侧边缘长 ${sideEdge.toFixed(2)} m`);
  chk(Math.abs(nearEdge - 157.12) < 0.3, '下边缘宽 = 2·h·tan(HFOV/2) = 157.1 m', nearEdge.toFixed(2));
  chk(Math.abs(sideEdge - 88.38) < 1.5, '侧边缘深 = 2·h·tan(VFOV/2) = 88.4 m', sideEdge.toFixed(2));

  // 正下视时四角到飞机的水平距离相同，且都在截断距离内 -> 不截断
  const c = dist(drone, g.bl);
  console.log(`    角点到飞机正下方 ${c.toFixed(2)} m（应 = √(78.6²+44.2²) = 90.14）`);
  chk(Math.abs(c - 90.14) < 0.3, '角点距离 90.14 m', c.toFixed(2));
  chk(Math.abs(dist(drone, g.left) - c) < 0.3, '未触发截断：左端就是真实左上角');
  chk(Math.abs(dist(drone, g.right) - c) < 0.3, '未触发截断：右端就是真实右上角');

  // 对称性：yaw=0 时下边缘两端纬度相同、经度对称
  chk(Math.abs(g.bl.lat - g.br.lat) < 1e-9, '下边缘两端纬度相同（垂直于航向）');
  chk(Math.abs(Math.abs(g.bl.lng - drone.lng) - Math.abs(g.br.lng - drone.lng)) < 1e-9,
    '下边缘两端关于航向经线对称');
  chk(Math.abs(g.left.lat - g.right.lat) < 1e-9, '左右端纬度相同（对称）');

  // 下边缘在飞机的南侧（yaw=0 且正下视时画面顶部朝北）
  chk(g.bl.lat < drone.lat, '下边缘在飞机南侧（画面上方朝北）');
  chk(g.left.lat > drone.lat, '左右端在飞机北侧');
}

console.log('\n=== 3) 斜视（pitch=-30）：远边落在截断距离之内 ===');
{
  // 截断距离按高度成比例（12×alt）。24 mm 广角在 -30° 俯角时，
  // 真实远角约在 11.4×alt 处 —— 正好在 12×alt 之内，所以这一档**不该被截断**，
  // 画出来的就是真实视场。真正会被截断的是更平的俯角（见下面 -2° 那一例）。
  const alt = 100;
  const g = footprintGeometry(drone, alt, 0, -30, 0, 24, 1);
  chk(!!g, '能算出视场');
  const dNear = dist(drone, g.bl);
  const dLeft = dist(drone, g.left);
  const dRight = dist(drone, g.right);
  const cap = maxDist(alt);
  console.log(`    下边缘距飞机 ${dNear.toFixed(1)} m   左端 ${dLeft.toFixed(1)} m   右端 ${dRight.toFixed(1)} m   上限 ${cap} m`);
  chk(dLeft < cap && dRight < cap, `左右端都在截断距离（${cap} m）之内 —— 用的是真实远角`, `${dLeft.toFixed(0)} / ${dRight.toFixed(0)}`);
  chk(dLeft > 10 * alt, '但远边确实很远（广角低俯角，约 11× 高度）', `${(dLeft / alt).toFixed(1)}×`);
  chk(dNear < dLeft && dNear < dRight, '下边缘比左右端更近');

  // 真实的远角有多远（yImg=+1 那条中心线）
  const far = groundPointForImage(drone, alt, 0, -30, 0, 0, 1, ...fovOf(24));
  console.log(`    参考：真实远边中点在 ${far.distance.toFixed(0)} m 外`);

  // 左右端应分列航向两侧
  const bL = bearing(drone, g.left), bR = bearing(drone, g.right);
  console.log(`    方位：左端 ${bL.toFixed(1)}°  右端 ${bR.toFixed(1)}°（航向 0°）`);
  chk(bL > 180 && bL < 360, '左端在航向左侧');
  chk(bR > 0 && bR < 180, '右端在航向右侧');
}

console.log('\n=== 4) 变焦让视场变窄 ===');
{
  const wide = footprintGeometry(drone, 100, 0, -30, 0, 24, 1);
  const tele = footprintGeometry(drone, 100, 0, -30, 0, 168, 1);
  const spanW = angleDiff(bearing(drone, wide.left), bearing(drone, wide.right));
  const spanT = angleDiff(bearing(drone, tele.left), bearing(drone, tele.right));
  console.log(`    广角 1× 张角 ${spanW.toFixed(1)}°   长焦 7× 张角 ${spanT.toFixed(1)}°`);
  chk(spanT < spanW / 3, '长焦张角不到广角的 1/3', `${spanT.toFixed(1)}° vs ${spanW.toFixed(1)}°`);

  // 数码变焦：必须用「报告焦距」算视场（数码变焦是裁切画面，看到的视场确实变窄）
  const digital = footprintGeometry(drone, 100, 0, -30, 0, 81.12, 3.38);
  const spanD = angleDiff(bearing(drone, digital.left), bearing(drone, digital.right));
  console.log(`    广角叠 3.38× 数码变焦（报告焦距 81.1mm）张角 ${spanD.toFixed(1)}°`);
  chk(spanD < spanW / 2, '数码变焦确实让张角变窄', `${spanD.toFixed(1)}° vs ${spanW.toFixed(1)}°`);

  // 视场只由报告焦距决定，与 dzoom 无关：81.12mm/3.38× 必须和 81.12mm/1× 完全一致
  const same = footprintGeometry(drone, 100, 0, -30, 0, 81.12, 1);
  chk(Math.abs(dist(digital.left, same.left)) < 1e-6
    && Math.abs(dist(digital.right, same.right)) < 1e-6,
    '视场只取决于报告焦距（81.12mm 时 dzoom 填 3.38 还是 1 结果相同）');

  // 长焦叠加数码变焦后应比长焦本身更窄
  const teleDigital = footprintGeometry(drone, 100, 0, -30, 0, 168 * 2, 2);
  const spanTD = angleDiff(bearing(drone, teleDigital.left), bearing(drone, teleDigital.right));
  console.log(`    长焦 7× 再叠 2× 数码变焦 张角 ${spanTD.toFixed(1)}°`);
  chk(spanTD < spanT / 1.8, '长焦叠数码变焦后更窄', `${spanTD.toFixed(1)}° vs ${spanT.toFixed(1)}°`);
}

console.log('\n=== 5) 边界情况：不该画的必须不画 ===');
{
  chk(footprintGeometry(drone, 100, 0, 0, 0, 24, 1) === null, 'pitch=0（水平）-> 不画');
  chk(footprintGeometry(drone, 100, 0, 5, 0, 24, 1) === null, 'pitch>0（朝上）-> 不画');
  chk(footprintGeometry(drone, 0, 0, -30, 0, 24, 1) === null, '高度 0 -> 不画');
  chk(footprintGeometry(drone, -5, 0, -30, 0, 24, 1) === null, '高度为负 -> 不画');
  chk(footprintGeometry(drone, 100, NaN, -30, 0, 24, 1) === null, '航向缺失 -> 不画');
  chk(footprintGeometry(drone, 100, 0, -30, 0, null, 1) === null, '焦距缺失 -> 不画');

  // 很浅的俯角：真实远角在地平线以上（求交失败），但截断逻辑仍应给出结果
  const shallow = footprintGeometry(drone, 100, 0, -2, 0, 24, 1);
  chk(!!shallow, '俯角仅 2° 时靠截断仍能画出（真实远角已在地平线以上）');
  if (shallow) {
    chk(Math.abs(dist(drone, shallow.left) - maxDist(100)) < 0.5,
      `浅俯角下左端同样被截断在 ${maxDist(100)} m`, dist(drone, shallow.left).toFixed(2));
  }
}

console.log('\n=== 6) 真实数据抽查（东莞3，实测姿态）===');
{
  const samples = [
    { t: 60.294, yaw: 167.4, pitch: -29.4, focal: 24.0, dzoom: 1.0, alt: 97.273 },
    { t: 400.0, yaw: 173.9, pitch: -42.0, focal: 172.5, dzoom: 1.03, alt: 100.3 },
    { t: 89.2, yaw: 41.2, pitch: -17.4, focal: 24.0, dzoom: 1.0, alt: 19.596 },
  ];
  for (const s of samples) {
    const g = footprintGeometry(drone, s.alt, s.yaw, s.pitch, 0, s.focal, s.dzoom);
    if (!g) { chk(false, `t=${s.t}s 应能算出视场`); continue; }
    const near = dist(drone, g.bl);
    const left = dist(drone, g.left);
    const width = dist(g.bl, g.br);
    console.log(`    t=${String(s.t).padStart(7)}s  俯角 ${Math.abs(s.pitch).toFixed(1)}°  下边缘距 ${near.toFixed(1)} m 宽 ${width.toFixed(0)} m  左右端 ${left.toFixed(0)} m`);
    chk(near < left, `t=${s.t}s 下边缘始终比左右端近`);
    chk(left <= maxDist(s.alt) + 0.5, `t=${s.t}s 左右端不超过截断距离（${maxDist(s.alt).toFixed(0)} m）`);
  }
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
