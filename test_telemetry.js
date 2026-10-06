// 验证视频实时信息的换算逻辑：中文朝向、地面水平距离、镜头判定
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
  const i = html.indexOf(a), j = html.indexOf(b);
  if (i < 0 || j < 0 || j <= i) throw new Error('区间锚点找不到: ' + a);
  return html.slice(i, j);
}

const consts = extractBetween('const BASE_FOCAL=24;', '// 方位角 ->');
const src = consts + '\n'
  + extractFn('isInfraredPath') + '\n'
  + extractFn('opticalFocalOf') + '\n'
  + extractFn('lensInfoOf') + '\n'
  + extractFn('compassText') + '\n'
  + extractFn('offsetLatLng') + '\n'
  + extractFn('groundCenterDistance') + '\n'
  + extractFn('centerGroundLatLng');

const api = new Function(src +
  '\nreturn {compassText,groundCenterDistance,lensInfoOf,opticalFocalOf,isInfraredPath,'
  + 'BASE_FOCAL,M4T_LENS_BANDS,GROUND_MIN_PITCH,COMPASS_NAMES};')();
const { compassText, groundCenterDistance, lensInfoOf, opticalFocalOf, isInfraredPath,
        BASE_FOCAL, M4T_LENS_BANDS, GROUND_MIN_PITCH, COMPASS_NAMES } = api;

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

console.log('=== 1) 中文朝向格式（用户要的“东偏南 35°”）===');
const cases = [
  [125, '东偏南 35°'],
  [35, '北偏东 35°'],
  [170, '南偏东 10°'],
  [190, '南偏西 10°'],
  [350, '北偏西 10°'],
  [0, '正北'],
  [90, '正东'],
  [180, '正南'],
  [270, '正西'],
  [45, '北偏东 45°'],
  [-90, '正西'],
  [360, '正北'],
  [235, '西南'],
];
for (const [deg, expect] of cases) {
  const got = compassText(deg);
  if (expect === '西南') {           // 235 度：与南、西各差 55/35 -> 应在西偏南 55 或南偏西 55
    chk(typeof got === 'string' && /偏/.test(got), `235° 给出偏角表述`, got);
    continue;
  }
  chk(got === expect, `${deg}° -> ${expect}`, got);
}
chk(compassText(NaN) === '—', 'NaN -> “—”');
chk(compassText(undefined) === '—', 'undefined -> “—”');

console.log('\n=== 2) 朝向文本反向解析回来，应与原角度一致（往返一致性）===');
const NAMES = COMPASS_NAMES;
function parseCompass(text) {
  let m = text.match(/^正(.)$/);
  if (m) { const i = NAMES.indexOf(m[1]); return i < 0 ? null : i * 90; }
  m = text.match(/^(.)偏(.)\s+(\d+)°$/);
  if (!m) return null;
  const i = NAMES.indexOf(m[1]), j = NAMES.indexOf(m[2]);
  if (i < 0 || j < 0) return null;
  const off = Number(m[3]);
  const cw = ((j - i + 4) % 4) === 1;
  return (((i * 90 + (cw ? off : -off)) % 360) + 360) % 360;
}
let worst = 0, bad = 0;
for (let d = 0; d < 360; d += 0.5) {
  const text = compassText(d);
  const back = parseCompass(text);
  if (back === null) { bad++; console.log('    无法解析:', d, text); continue; }
  let diff = Math.abs(back - d);
  if (diff > 180) diff = 360 - diff;
  worst = Math.max(worst, diff);
}
chk(bad === 0, '720 个角度都能被解析回来', `失败 ${bad}`);
chk(worst <= 0.5, '反向解析最大误差 ≤ 0.5°（仅取整损失）', worst.toFixed(3) + '°');

console.log('\n=== 3) 画面中心地面距离：必须是地面水平距离，不是空中直线 ===');
{
  const alt = 98.4, pitch = -30;
  const ground = groundCenterDistance(alt, pitch);
  const slant = alt / Math.sin(30 * Math.PI / 180);          // 空中直线距离
  const expect = alt / Math.tan(30 * Math.PI / 180);
  console.log(`  高度 ${alt} m，俯角 30°：`);
  console.log(`    地面水平距离 = ${ground.toFixed(2)} m   （应为 ${expect.toFixed(2)}）`);
  console.log(`    空中直线距离 = ${slant.toFixed(2)} m   （不能是这个）`);
  chk(Math.abs(ground - expect) < 0.01, '等于 h/tan(俯角)', ground.toFixed(2) + ' m');
  chk(Math.abs(ground - slant) > 1, '与空中直线距离明显不同（没算错）', `${ground.toFixed(1)} vs ${slant.toFixed(1)}`);
}
// tan(90°) 浮点下不是无穷大，结果会是 ~6e-15，显示为 0 m，这里按数值等价判断
chk(Math.abs(groundCenterDistance(100, -90)) < 1e-9, '正下视（-90°）距离为 0',
  String(groundCenterDistance(100, -90)));
chk(Math.abs(groundCenterDistance(100, -45) - 100) < 1e-9, '俯角 45° 时等于高度');
chk(groundCenterDistance(100, -5) > 1000, '俯角 5° 时距离已超过 1 km', groundCenterDistance(100, -5).toFixed(0) + ' m');
chk(groundCenterDistance(100, -4.9) === null, `俯角 < ${GROUND_MIN_PITCH}° 时不给距离`);
chk(groundCenterDistance(100, 0) === null, '水平（0°）不给距离');
chk(groundCenterDistance(100, 5) === groundCenterDistance(100, -5), '仰角与俯角对称（取绝对值）');
chk(groundCenterDistance(0, -30) === null, '高度为 0 时不给距离');
chk(groundCenterDistance(-5, -30) === null, '高度为负时不给距离');
chk(groundCenterDistance(NaN, -30) === null, '高度 NaN 时不给距离');

console.log('\n=== 4) 当前镜头（DJI App 写法：广角 1× / 中长焦 3× / 长焦 7× / 红外）===');
chk(BASE_FOCAL === 24, '广角端等效焦距 = 24 mm（也是倍率基准）', String(BASE_FOCAL));
chk(M4T_LENS_BANDS.length === 3, '三颗可见光镜头', String(M4T_LENS_BANDS.length));
chk(M4T_LENS_BANDS.map(b => b.base).join('/') === '1/3/7',
  '标称倍率为 1× / 3× / 7×', M4T_LENS_BANDS.map(b => b.base).join(' / '));

// 报告焦距 ÷ 数码变焦 = 光学焦距（M4T 的三种光学焦距是 24 / 70 / 168）
chk(Math.abs(opticalFocalOf(172.5, 1.03) - 167.5) < 0.1, '172.5mm ÷ 1.03 -> 光学 167.5mm',
  opticalFocalOf(172.5, 1.03).toFixed(2));
chk(opticalFocalOf(24, null) === 24, '没有数码变焦时按原值');
chk(opticalFocalOf(24, 0) === 24, '数码变焦为 0 时不除零');
chk(opticalFocalOf(null, 1) === null, '焦距缺失 -> null');

const info = (f, z) => lensInfoOf('DJI_x_V.mp4', f, z);

console.log('  光学焦距 × 数码变焦 -> 显示：');
for (const [f, z, expect] of [
  [24, 1, '广角 1×'],
  [70, 1, '中长焦 3×'],
  [168, 1, '长焦 7×'],
  [140, 2, '中长焦 6×'],
  [218.4, 1.3, '长焦 9.1×'],
  [81.12, 3.38, '广角 3.4×'],
]) {
  const got = info(f, z);
  console.log(`    光学 ${(f / z).toFixed(1).padStart(5)} mm  数码 ${String(z).padStart(4)}×  ->  ${got.text}`);
  chk(got.text === expect, `显示为「${expect}」`, got.text);
}

chk(info(81, 3.38).name === '广角', '广角开 3.38× 数码变焦仍判广角（必须用光学焦距）');
chk(info(237, 3.38).name === '中长焦', '中长焦开 3.38× 数码变焦仍判中长焦');
chk(info(229.1, 1).name === '长焦', '229.1 mm -> 长焦');
chk(info(null, 1).text === '—', '焦距缺失 -> —');
chk(lensInfoOf('DJI_x_T.mp4', 52.7, 1).text === '红外', 'T 路 -> 红外（不带倍率）');
chk(lensInfoOf('DJI_x_T.mp4', null, 1).text === '红外', '红外优先级高于焦距判断');
chk(isInfraredPath('DJI_x_T.MP4') && !isInfraredPath('DJI_x_V.mp4') && !isInfraredPath('DJI_x_S.mp4'),
  '只有 _T 判为红外');

console.log('\n=== 5) 用真实遥测数据抽查（后端已算好的 12181 点）===');
{
  // 直接读后端返回过一次的数值范围，验证换算在真实数据上不越界
  const samples = [
    { t: 60.294, yaw: 167.4, pitch: -29.4, focal: 24.0, dzoom: 1.0, alt: 97.273 },
    { t: 400.0, yaw: 173.9, pitch: -42.0, focal: 172.5, dzoom: 1.03, alt: 100.3 },
    { t: 5.0, yaw: 41.2, pitch: -17.4, focal: 24.0, dzoom: 1.0, alt: 19.596 },
  ];
  for (const s of samples) {
    const d = groundCenterDistance(s.alt, s.pitch);
    const name = lensInfoOf('DJI_x_V.mp4', s.focal, s.dzoom).text;
    console.log(`    t=${String(s.t).padStart(7)}s  朝向 ${compassText(s.yaw).padEnd(12)} 俯角 ${Math.abs(s.pitch).toFixed(1).padStart(4)}°  ${name.padEnd(9)}  地面距离 ${d != null ? d.toFixed(0) + ' m' : '—'}`);
    chk(d === null || (d >= 0 && d < 5000), `t=${s.t}s 地面距离在合理范围内`);
  }
}

console.log('\n=== 6) 地图准星落点：反推的距离与方位必须与输入一致 ===');
{
  const L = { latLng: (lat, lng) => ({ lat, lng }) };
  // offsetLatLng 必须和 L 定义在同一个作用域里，跨作用域传会拿不到 L
  const build = new Function('L', 'groundCenterDistance',
    extractFn('offsetLatLng') + '\n'
    + extractFn('centerGroundLatLng') + '\nreturn centerGroundLatLng;');
  const centerGroundLatLng = build(L, groundCenterDistance);

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

  const drone = { lat: 23.030, lng: 114.109 };
  const cases = [
    { yaw: 0, pitch: -45, alt: 100 },
    { yaw: 90, pitch: -45, alt: 100 },
    { yaw: 180, pitch: -45, alt: 100 },
    { yaw: 270, pitch: -45, alt: 100 },
    { yaw: 41.2, pitch: -17.4, alt: 19.6 },
    { yaw: -174.2, pitch: -30.1, alt: 98.4 },
    { yaw: 167.4, pitch: -29.4, alt: 97.3 },
    { yaw: -179.9, pitch: -60, alt: 104.8 },
    { yaw: 359.9, pitch: -5.5, alt: 100 },
  ];
  let worstD = 0, worstB = 0;
  for (const c of cases) {
    const target = centerGroundLatLng(drone, c.yaw, c.pitch, c.alt);
    const expect = groundCenterDistance(c.alt, c.pitch);
    const d = dist(drone, target);
    const b = bearing(drone, target);
    let db = Math.abs(b - ((c.yaw % 360) + 360) % 360);
    if (db > 180) db = 360 - db;
    worstD = Math.max(worstD, Math.abs(d - expect));
    worstB = Math.max(worstB, db);
    console.log(`    朝向 ${String(c.yaw).padStart(7)}°  俯角 ${String(Math.abs(c.pitch)).padStart(4)}°  高 ${String(c.alt).padStart(5)} m  ->  落点距飞机 ${d.toFixed(2).padStart(8)} m（应 ${expect.toFixed(2).padStart(8)}）  方位 ${b.toFixed(2).padStart(7)}°`);
  }
  chk(worstD < 0.05, '落点距离与理论值一致（误差 < 5 cm）', worstD.toFixed(4) + ' m');
  chk(worstB < 0.05, '落点方位与镜头朝向一致（误差 < 0.05°）', worstB.toFixed(4) + '°');

  const nadir = centerGroundLatLng(drone, 0, -90, 100);
  chk(nadir.lat === drone.lat && nadir.lng === drone.lng, '正下视时落点就是飞机正下方');
  chk(centerGroundLatLng(drone, 45, -4, 100) === null, '俯角 < 5° 时不给落点（不显示假位置）');
  chk(centerGroundLatLng(drone, NaN, -30, 100) === null, '朝向缺失时不给落点');
  chk(centerGroundLatLng(drone, 45, -30, 0) === null, '高度为 0 时不给落点');
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
