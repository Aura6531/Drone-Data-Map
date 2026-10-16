// 窄屏自适应布局的测试。
//
// 背景：这套尺寸是在 42 寸 4K 上定的，而那块屏缩放到 200% 时视口约 1920 CSS px；
// 用户换到 14 寸笔记本（同样 200%）视口只有 885 —— 三栏彻底放不下：
//   左栏固定 380px 独占 43%、中栏只剩 208px（按钮挤成竖排单字）、右栏被切。
//
// 这里钉住的是"档位设计"和"CSS 层叠顺序"：
//   · 断点必须都写出来且顺序正确（后来的覆盖先前的）
//   · 左栏宽度必须只用 --left-w 一个变量控制
//   · 宽的断点必须排在窄的前面，否则窄档会被宽档覆盖
//
// 注意：媒体查询要真在浏览器里才算数，所以这里断言的是"规则写对了"，
// 真实渲染仍要人工在窗口里拉宽度验证。

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'Code', 'project_geojson_preview.html'), 'utf8');
const css = (html.match(/<style>([\s\S]*?)<\/style>/) || [])[1] || '';

let ok = true;
const chk = (c, label, extra = '') => {
  ok = ok && !!c;
  console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
};

console.log('=== 1) 左栏宽度只由 --left-w 一处控制 ===');
{
  const m = css.match(/\.layout\{([^}]*)\}/);
  chk(!!m, '找到 .layout 基础规则');
  if (m) {
    const body = m[1].replace(/\s+/g, ' ');
    chk(/--left-w/.test(body), 'grid 里用的是 var(--left-w)', body.slice(0, 80));
    chk(!/grid-template-columns:\s*380px/.test(body),
      '不再是硬编码 380px（那是窄屏挤爆的根因）');
    chk(/clamp\(/.test(body), '有 clamp 兜底（宽屏仍是 300~380 之间）');
  }
}

console.log('\n=== 2) 四个断点都在，且顺序由宽到窄 ===');
{
  const bps = [];
  const re = /@media\s*\(max-width:\s*(\d+)px\)/g;
  let m;
  while ((m = re.exec(css))) bps.push({ px: Number(m[1]), at: m.index });
  const ours = [1900, 1400, 1280, 820];
  for (const w of ours) {
    chk(bps.some((b) => b.px === w), `有 @media (max-width:${w}px)`);
  }
  // 关键：CSS 里后写的同权重规则覆盖先写的 —— 宽的必须在前面
  const idx = ours.map((w) => (bps.find((b) => b.px === w) || {}).at ?? -1);
  chk(idx.every((v) => v >= 0), '四个断点都能定位到');
  let ordered = true;
  for (let i = 1; i < idx.length; i++) if (idx[i] < idx[i - 1]) ordered = false;
  chk(ordered, '按 1900 -> 1400 -> 1280 -> 820 的顺序排列（否则窄档会被覆盖）',
    idx.join(' < '));
}

console.log('\n=== 3) 1280 档：左栏变窄条 + 可折叠轨 ===');
{
  const i = css.indexOf('@media (max-width:1280px)');
  const seg = i < 0 ? '' : css.slice(i, css.indexOf('@media (max-width:820px)', i));
  chk(i > 0, '找到 1280 档');
  chk(/--left-w:\s*46px/.test(seg), '默认窄条 46px');
  chk(/\.left-open\{[^}]*--left-w/.test(seg), '展开时用 .left-open 改 --left-w');
  chk(/\.left-rail\{display:none\}/.test(seg), '宽屏时轨条隐藏');
  chk(/\.left-rail\{display:flex\}/.test(seg), '折叠时才显示轨条');
  chk(/invalidateSize/.test(html), '切换后有 invalidateSize（地图要重算）');
}

console.log('\n=== 4) 1400 档：不依赖 JS 的换行兜底 ===');
{
  const i = css.indexOf('@media (max-width:1400px)');
  const seg = i < 0 ? '' : css.slice(i, css.indexOf('@media (max-width:1280px)', i));
  chk(i > 0, '找到 1400 档');
  // .narrow-tools 是 JS 按"面板宽度"加的，面板宽度是延迟知道的；
  // 这一档必然太窄，所以要用 CSS 兜底，不能等 JS。
  chk(/\.row\.video-head-tools\{[^}]*flex-wrap:wrap/.test(seg),
    '视频标题栏按钮行 CSS 兜底换行（不等 JS 的 narrow-tools）');
  chk(/--ctrl-h:32px/.test(seg), '控件高度收到 32px');
  // 字号必须只在 1900 档用 clamp 连续控制 —— 这一档再写死会把它盖掉
  chk(!/--ctrl-font/.test(seg),
    '这一档不重复写 --ctrl-font（写了会盖掉 1900 档的 clamp）');
}

console.log('\n=== 4b) 字号是连续缩放（clamp），不是断点跳变 ===');
{
  const m = css.match(/--ctrl-font:clamp\(([^)]*)\)/);
  chk(!!m, '有 --ctrl-font:clamp(...)');
  if (m) {
    const parts = m[1].split(',').map((s) => s.trim());
    chk(parts.length === 3, '三参数 clamp(min, 偏好, max)', m[1]);
    const minPx = parseFloat(parts[0]);
    const maxPx = parseFloat(parts[2]);
    chk(minPx >= 12, `下限不低于 12px（再小不好读）-> ${minPx}px`);
    chk(maxPx === 13, `上限 13px（与基准一致）-> ${maxPx}px`);
    chk(/vw/.test(parts[1]), '中间项用 vw（窗口越窄字越小）', parts[1]);
    // 关键：min/max 必须是 px —— 纯 vw 会让浏览器缩放失效
    chk(/px/.test(parts[0]) && /px/.test(parts[2]),
      'min/max 是 px（纯 vw 会让 Ctrl+/- 缩放失效）');
  }
}

console.log('\n=== 5) 820 档：三栏改上下堆叠 ===');
{
  const i = css.indexOf('@media (max-width:820px)');
  chk(i > 0, '找到 820 档');
  const tail = i < 0 ? '' : css.slice(i, i + 1400);
  chk(/\.layout\{[^}]*display:flex/.test(tail), '改成 flex 竖排');
  chk(/flex-direction:column/.test(tail), '方向是纵向');
  chk(/height:auto/.test(tail), '高度改 auto（不再锁 100vh，否则内容被切）');
  chk(/min-height:100vh/.test(tail), '用 min-height 保底');
  // 堆叠时地图必须有确定高度，否则 flex 里塌成 0
  chk(/\.map-wrap\{[^}]*height/.test(tail), '地图给了确定高度（堆叠时不会塌成 0）');
}

console.log('\n=== 6) 折叠状态会被记住，且不抢 layout 这个名字 ===');
{
  chk(/droneMap\.leftOpen/.test(html), '折叠状态写进 localStorage');
  chk(/function readLeftOpen/.test(html), '有读取函数');
  chk(/function initLeftRail/.test(html), '有初始化函数');
  chk(/initLeftRail\(\)/.test(html), 'boot 里调用了它');
  // 页面里已有一个局部 const layout（标记点分栏），全局别再抢这个名字
  chk(!/^const layout=/m.test(html), '没有顶层 const layout（那个名字已被占用）');
  chk(/function layoutRoot\(\)/.test(html), '用 layoutRoot() 取容器');
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
