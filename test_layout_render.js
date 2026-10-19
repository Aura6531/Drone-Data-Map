// 用无头 Edge + DevTools 协议，在不同视口宽度下量真实渲染尺寸。
//
// 为什么必须用真浏览器：媒体查询、flex/grid 的实际分配、溢出，
// 只有渲染引擎说了算 —— Node 里的 DOM 桩量不出来。

const { spawn } = require('child_process');
const os = require('os');
const path = require('path');
const fs = require('fs');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9333;
const PROFILE = path.join(__dirname, '_edgeprobe');
const URL = 'http://127.0.0.1:8000/project_geojson_preview.html';

const WIDTHS = [1920, 1700, 1400, 1280, 1100, 885, 820, 700];

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function fetchJson(p) {
  const res = await fetch(`http://127.0.0.1:${PORT}${p}`);
  return res.json();
}

// 极小 CDP 客户端（Node 22 自带 WebSocket）
class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.waiting = new Map(); }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true });
      ws.addEventListener('error', rej, { once: true });
    });
    const c = new CDP(ws);
    ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data) } catch { return }
      if (msg.id && c.waiting.has(msg.id)) {
        const { resolve, reject } = c.waiting.get(msg.id);
        c.waiting.delete(msg.id);
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
      }
    });
    return c;
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise: true,
    });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' +
      JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description));
    return r.result.value;
  }
}

// 在真页面里量布局
const PROBE = `(() => {
  const d = document, w = window;
  if (!d.getElementById('layout')) return { error: 'no #layout' };
  const rect = (sel) => {
    const el = d.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left) };
  };
  const cs = (sel, prop) => {
    const el = d.querySelector(sel);
    return el ? w.getComputedStyle(el)[prop] : null;
  };
  const root = d.getElementById('layout');
  // 右栏现在会**在没有任何内容时自动收起**（.right-empty，见页面的 syncRightCol）。
  // 所以"地图与视频能不能并排"这件事要在**有内容**的状态下量 ——
  // 先把 .right-empty 摘掉模拟"有内容"，量完再放回。
  const nEmpty = (() => { const r = rect('#colRight'); return { w: r ? r.w : -1 }; })();
  const hadEmpty = root.classList.contains('right-empty');
  root.classList.remove('right-empty');
  const nWithContent = (() => { const r = rect('#colRight'); return { w: r ? r.w : -1 }; })();
  if (hadEmpty) root.classList.add('right-empty');
  return {
    viewport: [w.innerWidth, w.innerHeight],
    layoutDisplay: cs('#layout', 'display'),
    layoutDir: cs('#layout', 'flexDirection'),
    leftW: rect('#colLeft'),
    midW: rect('.col-mid') || rect('.col:nth-of-type(2)'),
    // 两种状态各一份：空（应收起）与有内容（应占宽度）。
    // 都保持 {w,h,x} 对象形状 —— 打印那行是按对象用的（取 .w）。
    // 注意：这一段在模板字符串里，注释里不能出现反引号，否则会提前结束字符串（踩过）。
    rightEmptyW: nEmpty,
    rightContentW: nWithContent,
    rightW: nWithContent,
    rightWasEmpty: hadEmpty,
    leftOpen: root.classList.contains('left-open'),
    railVisible: (() => { const r = d.getElementById('leftRail'); if (!r) return null;
      return w.getComputedStyle(r).display !== 'none'; })(),
    // 按钮字号各自写死，量不出来；select 走的是 --ctrl-font，用它判断密度档
    selFont: cs('#projectSelect', 'fontSize'),
    selH: (() => { const el = d.querySelector('#projectSelect'); return el ? Math.round(el.getBoundingClientRect().height) : null })(),
    headWrap: cs('.row.video-head-tools', 'flexWrap'),
    docScrollW: d.documentElement.scrollWidth,
    docClientW: d.documentElement.clientWidth,
    bodyScrollW: d.body.scrollWidth,
  };
})()`;

async function main() {
  // 护栏：这个测试要用**真浏览器**量渲染（媒体查询只有渲染引擎说了算），
  // 所以需要两样东西 —— 开发服务和本机的 Edge。缺任何一样就明确跳过，
  // 不要报成失败（离线/换机器跑测试时不该被它挡住）。
  if (!fs.existsSync(EDGE)) {
    console.log('=== 窄屏布局（真浏览器实测）===');
    console.log(`  [SKIP] 找不到浏览器：${EDGE}`);
    console.log('\n结果: 全部通过（已跳过）');
    return 0;
  }
  try {
    // 用 GET 而不是 HEAD：后端只实现了 GET/POST，HEAD 会返回 501
    // （浏览器控制台里那条 "Unsupported method ('HEAD')" 就是这个）。
    const res = await fetch(URL);
    if (!res.ok) throw new Error(String(res.status));
  } catch (e) {
    console.log('=== 窄屏布局（真浏览器实测）===');
    console.log(`  [SKIP] 开发服务没在跑（${URL}）`);
    console.log('         先启动：cd Code && python -B project_manager.py');
    console.log('\n结果: 全部通过（已跳过）');
    return 0;
  }

  fs.rmSync(PROFILE, { recursive: true, force: true });
  const edge = spawn(EDGE, [
    '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`,
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--disable-gpu', '--window-size=1920,1080', 'about:blank',
  ], { stdio: 'ignore' });

  let ver = null;
  for (let i = 0; i < 40; i++) {
    try { ver = await fetchJson('/json/version'); break } catch { await sleep(300) }
  }
  if (!ver) { console.log('连不上无头浏览器'); edge.kill(); return 1 }
  console.log('浏览器:', ver['Browser']);

  const tabs = await fetchJson('/json/list');
  let page = tabs.find((t) => t.type === 'page');
  if (!page) { console.log('没有可用的标签页'); edge.kill(); return 1 }
  const cdp = await CDP.connect(page.webSocketDebuggerUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');

  const rows = [];
  for (const W of WIDTHS) {
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: W, height: 900, deviceScaleFactor: 1, mobile: false,
    });
    await cdp.send('Page.navigate', { url: URL });
    await sleep(1200);                       // 等 iframe 里的页面建起来
    let out;
    try { out = await cdp.eval(PROBE) } catch (e) { out = { error: e.message } }
    rows.push({ W, ...out });
  }

  console.log('\n' + '视口'.padEnd(7) + '左栏'.padEnd(8) + '中栏'.padEnd(8) + '右栏'.padEnd(8) +
    '折叠'.padEnd(7) + '轨'.padEnd(6) + '方向'.padEnd(9) + '按钮'.padEnd(13) + '标题行'.padEnd(9) +
    '横向溢出');
  console.log('-'.repeat(112));
  for (const r of rows) {
    if (r.error) { console.log(String(r.W).padEnd(7) + 'ERR ' + r.error); continue }
    const overflow = r.docScrollW > r.docClientW
      ? `是 (+${r.docScrollW - r.docClientW}px)` : '否';
    console.log(
      String(r.viewport[0]).padEnd(7) +
      (r.leftW ? r.leftW.w : '-').toString().padEnd(8) +
      (r.midW ? r.midW.w : '-').toString().padEnd(8) +
      (r.rightW ? r.rightW.w : '-').toString().padEnd(8) +
      String(r.leftOpen).padEnd(7) +
      String(r.railVisible).padEnd(6) +
      String(r.layoutDir).padEnd(9) +
      `${r.selH}px/${r.selFont}`.padEnd(13) +
      String(r.headWrap).padEnd(9) +
      overflow);
  }

let fail = 0;
  const chk = (cond, label, extra = '') => {
    if (!cond) fail++;
    console.log(`  ${cond ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
  };
  const at = (w) => rows.find((r) => r.W === w) || {};

  console.log('\n=== 断言：任何宽度下都不能横向溢出 ===');
  for (const r of rows) {
    if (r.error) { chk(false, `${r.W}px 能量到布局`, r.error); continue }
    chk(r.docScrollW <= r.docClientW,
      `${r.W}px 没有横向溢出`,
      `scrollW=${r.docScrollW} clientW=${r.docClientW}`);
  }

  console.log('\n=== 断言：左栏宽度按档位收 ===');
  chk(at(1920).leftW && at(1920).leftW.w === 380, '1920px 左栏 380',
    at(1920).leftW ? String(at(1920).leftW.w) : '');
  chk(at(1700).leftW && at(1700).leftW.w < 380, '1700px 左栏已经比 380 小（clamp 生效）',
    at(1700).leftW ? String(at(1700).leftW.w) : '');
  chk(at(1400).leftW && at(1400).leftW.w <= 320, '1400px 左栏收到 <=320',
    at(1400).leftW ? String(at(1400).leftW.w) : '');
  chk(at(1280).leftW && at(1280).leftW.w === 46, '1280px 左栏折成 46px 窄条',
    at(1280).leftW ? String(at(1280).leftW.w) : '');
  chk(at(885).leftW && at(885).leftW.w === 46, '885px（用户的 14 寸）左栏是窄条',
    at(885).leftW ? String(at(885).leftW.w) : '');

  console.log('\n=== 断言：885px 下地图与视频仍能并排 ===');
  {
    const r = at(885);
    chk(r.midW && r.midW.w > 340, '中栏（地图）> 340px',
      r.midW ? String(r.midW.w) : '');
    // 有内容时右栏要够宽（这才是"并排放得下"）
    chk(r.rightContentW && r.rightContentW.w > 340, '右栏（视频+图墙）有内容时 > 340px',
      r.rightContentW ? String(r.rightContentW.w) : '');
  }

  console.log('\n=== 断言：右栏空时把宽度让给地图 ===');
  {
    // 用户 2026-10-16：「选择文件阶段，右侧全是地图」。
    // 没加载/没播放时右栏只有一个占位提示，应当收起（宽度 0）。
    for (const W of [1400, 1280, 885]) {
      const r = at(W);
      chk(r.rightWasEmpty === true && r.rightEmptyW && r.rightEmptyW.w === 0,
        W + 'px 右栏空时收起（宽度 0）',
        'wasEmpty=' + r.rightWasEmpty + ' w=' + (r.rightEmptyW ? r.rightEmptyW.w : '-'));
    }
  }

  console.log('\n=== 断言：堆叠档 ===');
  chk(at(820).layoutDir === 'column', '820px 改成上下堆叠',
    String(at(820).layoutDir));
  chk(at(820).midW && at(820).midW.w === at(820).viewport[0] - 0 ||
      (at(820).midW && at(820).midW.w > 700),
    '堆叠后每栏占满整幅宽', at(820).midW ? String(at(820).midW.w) : '');

  console.log('\n=== 断言：折叠轨 ===');
  chk(at(1920).railVisible === false, '宽屏不显示折叠轨');
  chk(at(885).railVisible === true, '窄屏显示折叠轨');
  chk(at(885).leftOpen === false, '窄屏默认已折叠（把宽度让给地图和视频）');
  chk(at(1920).leftOpen === true, '宽屏默认展开');

  console.log('\n=== 断言：密度档 ===');
  chk(at(1920).selFont === '13px', '宽屏控件字号 13px', String(at(1920).selFont));
  // 字号是 clamp 连续缩放：宽屏 13、窄屏 12，中间是小数（1280px 时约 12.2）
  {
    const f = parseFloat(at(1280).selFont);
    chk(f > 12 && f < 13, '1280px 字号落在 12~13 之间（连续缩放，不是跳变）',
      String(at(1280).selFont));
  }
  chk(at(885).selFont === '12px', '885px 到达下限 12px', String(at(885).selFont));
  chk(parseFloat(at(1400).selFont) >= 12, '1400px 不低于下限', String(at(1400).selFont));
  chk(at(1920).headWrap === 'nowrap', '宽屏视频标题栏不换行', String(at(1920).headWrap));
  chk(at(1400).headWrap === 'wrap',
    '1400px 起标题栏 CSS 兜底换行（不等 JS 的 narrow-tools）',
    String(at(1400).headWrap));

  console.log('\n结果:', fail === 0 ? '全部通过' : `有 ${fail} 项失败`);

  cdp.ws.close();
  edge.kill();
  await sleep(400);
  fs.rmSync(PROFILE, { recursive: true, force: true });
  return fail === 0 ? 0 : 1;
}

main().then((c) => process.exit(c)).catch((e) => { console.error(e); process.exit(1) });
