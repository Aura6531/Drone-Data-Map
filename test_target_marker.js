// 「地图选的点要标在画面上」的测试。
//
// 需求（用户 2026-10-13）：「地图上所选的位置点，应该在画面当中给我标注出来」。
//
// 这里验的是**投影数学 + 百分比换算**：
//   页面 imagePointOfGround() 给出归一化坐标 (xImg, yImg)，范围 -1..1；
//   标记要落在 left=((x+1)/2*100)%、top=((1-y)/2*100)% 上。
// 两处最容易错的地方：
//   ① y 轴方向 —— 图像 y 向下、yImg 向上为正，不翻就上下颠倒；
//   ② 目标在画面外时必须隐藏，不能让标记贴在边缘误导人。

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'Code', 'project_geojson_preview.html'), 'utf8');

let ok = true;
const chk = (c, label, extra = '') => {
  ok = ok && !!c;
  console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
};

console.log('=== 1) 标记元素与样式都在 ===');
{
  chk(/id="videoTarget"/.test(html), '有 #videoTarget 覆盖层');
  chk(/class="video-target"/.test(html), '用的是 .video-target 样式');
  chk(/function targetMarkerEl/.test(html), '有 targetMarkerEl() 取值');
  const css = (html.match(/\.video-target\{([^}]*)\}/) || [])[1] || '';
  chk(/position:\s*absolute/.test(css), '绝对定位（压在画面上）');
  chk(/translate\(-50%,\s*-50%\)/.test(css),
    '用 transform 居中 —— left/top 指的是标记中心', css.slice(0, 70));
  // 和"画面固定准星"必须区分开，否则两个标记会混
  chk(/video-crosshair/.test(html) && /video-target/.test(html),
    '与画面中心准星是两个元素（不是同一个）');
}

console.log('\n=== 2) 每帧更新，且各个时机都接上了 ===');
{
  chk(/updateTargetMarker\(\);\s*\/\/ 地图选的那个点/.test(html),
    '每帧遥测更新里调用（跟着画面走）');
  chk(/function setProbe[\s\S]{0,600}updateTargetMarker\(\)/.test(html),
    '换选点时立刻更新');
  chk(/function clearProbe[\s\S]{0,600}updateTargetMarker\(\)/.test(html),
    '清空选点时收掉');
  chk(/applyTargetMarkerVisibility/.test(html), '有显隐入口');
  chk(/applyTargetMarkerVisibility\(\)/.test(html.split('function boot')[1] || ''),
    'boot 里初始化');
  chk(/遥测到位了[\s\S]{0,120}updateTargetMarker\(\)/.test(html),
    '遥测加载完成后更新（打开视频那一刻就该出现）');
}

console.log('\n=== 3) 复现投影数学，核对百分比换算 ===');
{
  // 直接从页面里抠出投影函数体，在测试里跑 —— 验的是**页面真的用的那段代码**
  const iFn = html.indexOf('function imagePointOfGround(');
  chk(iFn > 0, '找到 imagePointOfGround');
  // 它依赖 fovOf / telemetryIndexOf / BASE_FOCAL，这里给最小替身。
  // 按**行**取到函数结尾（顶层 `}` 单独一行）——
  // 用 indexOf('}') 会因为函数体里有嵌套对象 `{xImg,yImg,...}` 而截断。
  // 注意：页面文件是 **CRLF**，所以每行末尾带 \r，比较前必须 trim（踩过：
  // 用 `lines[k] === '}'` 永远为假，于是切片为空、报"函数能编译"失败）。
  const lines = html.slice(iFn).split('\n');
  let end = 0;
  for (let k = 1; k < lines.length; k++) {
    if (lines[k].replace(/\r$/, '') === '}') { end = k; break }
  }
  const fnSrc = end > 0 ? lines.slice(0, end + 1).join('\n') : '';
  chk(/\{xImg,yImg,visible:/.test(fnSrc), '切片包含了函数体与返回值',
    `end=${end} 长度=${fnSrc.length}`);

  const fovOf = (f) => {
    // 24mm 等效：水平 76.31°、垂直 47.68°（与 coverage.fov_of 一致）
    if (Math.abs(f - 24) < 0.01) return [76.31, 47.68];
    return [60, 36];
  };
  const L = { latLng: (a, b) => ({ lat: a, lng: b }) };
  const BASE_FOCAL = 24;
  const telemetryIndexOf = (t, tele, i) => i;

  let imagePointOfGround;
  try {
    imagePointOfGround = new Function(
      'L', 'fovOf', 'BASE_FOCAL', 'telemetryIndexOf',
      fnSrc + '; return imagePointOfGround;'
    )(L, fovOf, BASE_FOCAL, telemetryIndexOf);
  } catch (e) {
    chk(false, '抠出来的投影函数能编译', e.message);
  }

  if (imagePointOfGround) {
    // 无人机在 (23.0, 114.0)、高 100 m、正下视（俯角 -90）
    const tele = { alt: [100], yaw: [0], pitch: [-90], focal: [24] };
    const track = { coords: [[114.0, 23.0]] };

    // 正下方那一点 -> 应该在画面正中（xImg≈0, yImg≈0）
    const center = imagePointOfGround(track, tele, 0, L.latLng(23.0, 114.0));
    chk(center && Math.abs(center.xImg) < 0.02 && Math.abs(center.yImg) < 0.02,
      '正下方目标投到画面正中',
      center ? `${center.xImg.toFixed(3)}, ${center.yImg.toFixed(3)}` : 'null');
    chk(center && center.visible === true, '正中判定为可见');

    // 正北偏一点：正下视 + yaw=0（相机朝北），北在画面**上方** -> yImg > 0。
    // 注意别偏太多：高度 100 m、垂直视场 47.68° 时，画面只覆盖南北约 ±44 m，
    // 偏 55 m 就出画面了（第一版就是偏太多，visible=false 还拿来断言）。
    const north = imagePointOfGround(track, tele, 0, L.latLng(23.0003, 114.0));
    chk(north && north.yImg > 0 && north.visible,
      '北侧目标在画面上方且可见（yImg > 0）',
      north ? `yImg=${north.yImg.toFixed(3)} visible=${north.visible}` : 'null');

    // 换算成百分比：上方 -> top 更小（因为图像 y 向下）
    const topPct = (1 - north.yImg) / 2 * 100;
    chk(topPct > 0 && topPct < 50,
      '北侧目标的 top% 落在 0~50（y 轴翻对了）', `${topPct.toFixed(1)}%`);

    // 正东：yaw=0 朝北，东在画面**右侧** -> xImg > 0
    const east = imagePointOfGround(track, tele, 0, L.latLng(23.0, 114.0003));
    chk(east && east.xImg > 0, '东侧目标在画面右方（xImg > 0）',
      east ? `xImg=${east.xImg.toFixed(3)}` : 'null');

    // 远处目标 -> 超出视场 -> visible 必须为 false
    const far = imagePointOfGround(track, tele, 0, L.latLng(23.02, 114.02));
    chk(far && far.visible === false, '视场外的目标 visible=false',
      far ? `${far.xImg.toFixed(2)}, ${far.yImg.toFixed(2)}` : 'null');
  }
}

console.log('\n=== 4) 画面外 / 无遥测时必须隐藏 ===');
{
  const iFn = html.indexOf('function updateTargetMarker()');
  const seg = html.slice(iFn, iFn + 1600);
  chk(/!p\|\|!p\.visible/.test(seg) && /el\.hidden=true/.test(seg),
    '目标不可见 -> 隐藏标记');
  chk(/if\(!probeLatLng\|\|!clip\|\|!clip\.track\|\|!telemetry/.test(seg),
    '没选点 / 没视频 / 没遥测 -> 隐藏');
  // 遥测挂的是模块级 `telemetry`，不是 clip.telemetry —— 写错过一次。
  // 只扫代码、跳过注释行（注释里也会提到 clip.telemetry，那是解释为什么不用它）。
  const codeOnly = seg.split('\n')
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .join('\n');
  chk(!/clip\.telemetry/.test(codeOnly),
    '代码里用的是模块级 telemetry（不是 clip.telemetry）');
}

console.log('\n=== 5) 必须用 clip.index（航迹点下标），不能用遥测采样下标 ===');
{
  // 踩过的坑（2026-10-13）：imagePointOfGround 的第三个参数是**航迹点下标**
  // （它内部用 track.times[i] 反查时刻再取姿态）。
  // 曾经传 telemetryIndexAt(clip.trackSeconds) —— 那是**遥测采样下标**，
  // 两者差 3 倍，于是取到别的时刻的姿态，标记画错并且随播放一直漂。
  const iFn = html.indexOf('function updateTargetMarker()');
  const seg = html.slice(iFn, iFn + 1600);
  const codeOnly = seg.split('\n')
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .join('\n');
  chk(/imagePointOfGround\(clip\.track,telemetry,clip\.index,/.test(codeOnly),
    '传的是 clip.index（syncDroneMarker 算好的航迹点下标）');
  chk(!/telemetryIndexAt\(/.test(codeOnly),
    '没有再用 telemetryIndexAt（那是采样下标，不是航迹点下标）');
  // clip.index 必须在调用它之前就被赋值（syncDroneMarker 里）
  const iAssign = html.indexOf('clip.index=index');
  const iCall = html.indexOf('updateTargetMarker();     // 地图选的那个点');
  chk(iAssign > 0 && iCall > iAssign,
    'clip.index 先赋值、再调用 updateTargetMarker', `assign@${iAssign} call@${iCall}`);
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
