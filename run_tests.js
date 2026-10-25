#!/usr/bin/env node
// 一次跑完全部测试套件；任何一套失败就非零退出。
//
// 为什么需要这个文件：
//   node 只执行命令行里的【第一个】脚本 —— 写 `node check_page.js test_boot.js …`
//   时，后面的文件名会被静默忽略，而且照样打印「全部通过」并 exit 0（假绿）。
//   这个坑在本项目里真实踩过：文档里的两行命令实际只覆盖了 12 套里的 2 套。
//
// 用法：
//   node run_tests.js                # 15 套（不含需要联网的那套）
//   node run_tests.js --with-net     # 额外跑 test_tdt_tiles.py（会请求天地图瓦片）
//   node run_tests.js --list         # 只列清单，不执行
//
// 环境变量：
//   PYTHON=python3   指定 python 解释器（默认 windows 用 python，其它平台 python3）
//
// 所有路径按「脚本所在目录」推导，换机器 / 换盘符都不用改。

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

const NODE_SUITES = [
  'check_page.js',      // 页面静态断言（最全的一套）
  'test_ia_panel.js',    // P2 新左栏：三段结构 / 来源动作 / 内容分组 / ui.items 读写
  'test_boot.js',       // 页面顶层脚本真跑一遍
  'test_sync.js',       // 地图 / 视频同步路径
  'test_telemetry.js',  // 遥测换算
  'test_footprint.js',  // 相机视场几何
  'test_filelist.js',   // 文件列表
  'test_drone.js',      // 飞机箭头朝向
  'test_follow.js',     // 地图跟随
  'test_follow_mode.js',// 跟随模式：记住选择 / 点选点当次不跟随
  'test_nearest.js',    // 按位置检索（用真实 GeoJSON）
  'test_ab.js',         // A+B 检索的数学基础（正/反投影互逆）
  'test_markers.js',    // 标记点列表（排序/勾选/删除/KML/复制/跳转）
  'test_photos.js',     // 照片图层（一组一点 / ⚠ 角标 / 展示区 / 点照片跳视频）
  'test_coverage_ui.js',// 覆盖面板：热力图定位数学 / 缺字段兜底
  'test_coverage_bounds.js', // 热力图定位：原点语义 / 摘要新鲜度 / 换算常数
  'test_frames_ui.js',  // 「这个位置被哪些画面拍到过」图墙：跨架次 / 缩略图 URL / 点图跳播
  'test_gallery_slot.js', // 图墙挂在右栏（不是中栏地图下面）—— 挂错了会"出来了但看不到"
  'test_gallery_subtitle.js', // 图墙副标题：跨架次措辞 / 注释不能变成界面文字
  'test_target_marker.js', // 地图选点标到画面上：投影数学 / y 轴方向 / 画面外隐藏
  'test_layout_breakpoints.js', // 窄屏自适应：左栏 --left-w / 四档断点顺序 / 折叠轨
  'test_layout_render.js', // 窄屏自适应（真浏览器实测，需要开发服务，否则 [SKIP]）
];
const PY_SUITES = [
  'check_py.py',        // 后端静态断言
  'test_geocode.py',    // 地理编码 / key 优先级
  'test_report.py',     // 报告后端：逆地理编码 / 地图截图 / 抽帧 / docx
  'test_coverage.py',   // 视场覆盖栅格：几何 / 收口 / 斜距基准 / 置信度 / 存取往返
  'test_coverage_vector.py',  // 覆盖栅格矢量化：块追踪 / 环方向 / 洞 / 对角缝 / 简化
  'test_coverage_api.py',     // 覆盖接口层：清单 / 构建 / 复用 / 过期 / 查询 / 热力图 / 导出
  'test_pano360.py',          // 360 全景：手性 / 太阳检测的约束 / 地面距离 / 输入校验
  'test_photo_pano.py',       // 全景照片识别：2:1 等距柱状的判定边界（不依赖大素材）
  'test_pano_cover.py',       // 全景透视封面：yaw/pitch/fov 约定（自证，不依赖浏览器）
  'test_pano360_coverage.py', // 360 覆盖几何：径向标度 / 圆环内外半径 / 不落地判据
  'test_pano360_perspective.py', // 360 透视裁剪：方向约定与 stitch 一致（可自证）
  'test_sync_check.py',       // 视频/航迹时长同步自检：能抓到被裁过的视频
  'test_source_ops.py',      // 来源操作：刷新索引 / 重定位预检与确认 / 解除关联
  'test_ui_items.py',        // 内容身份：旧 ui 键迁移 / 离线身份 / 重接盘不丢状态
  'test_sources.py',          // 数据来源：id 稳定 / 只在内存补 / 原子写 / 不误改文件
  'test_i18n.py',             // 双语：键唯一 / zh-en 成对 / 英串当键 / 语言归一 / 线程隔离
  'test_i18n_report.py',      // 双语报告：真的生成 docx 并核对两种语言的模板文字
  'test_flight_profile.py',   // 悬停延时 vs 真实航线：用真实素材标定的判据
  'test_altitude_reference.py', // 相对高度 vs 海拔：山顶起飞飞到侧下方时 rel 为负是正常的
];
const NET_SUITES = [
  'test_tdt_tiles.py',  // 天地图瓦片连通性（需要联网 + 有效 tk）
];

const argv = process.argv.slice(2);
const withNet = argv.includes('--with-net');
const listOnly = argv.includes('--list');

const plan = [];
// 套件可能放在仓库根，也可能放在 Code/ 下（例如 coverage 相关的新模块）。
// 按「根 -> Code/」的顺序找，找到哪个用哪个。
function resolveSuite(f) {
  const atRoot = path.join(ROOT, f);
  if (fs.existsSync(atRoot)) return atRoot;
  const inCode = path.join(ROOT, 'Code', f);
  if (fs.existsSync(inCode)) return inCode;
  return atRoot;   // 都不在就交给它自己报「找不到」
}
for (const f of NODE_SUITES) plan.push({ file: f, cmd: process.execPath, args: [resolveSuite(f)] });
for (const f of PY_SUITES) plan.push({ file: f, cmd: PYTHON, args: ['-B', resolveSuite(f)] });
if (withNet) for (const f of NET_SUITES) plan.push({ file: f, cmd: PYTHON, args: ['-B', resolveSuite(f)], net: true });

console.log(`测试根目录：${ROOT}`);
console.log(`node：${process.execPath}  (${process.version})`);
console.log(`python：${PYTHON}`);
console.log(`套件：${plan.length} 套${withNet ? '' : '（未含需要联网的 test_tdt_tiles.py，加 --with-net 可跑）'}`);

if (listOnly) {
  for (const p of plan) console.log('  - ' + p.file + (p.net ? '  [需要联网]' : ''));
  process.exit(0);
}

const results = [];
for (const p of plan) {
  console.log(`\n──────── ${p.file} ────────`);
  const t0 = Date.now();
  // stdio: 'inherit' —— 让每套测试自己打印与自己的断言明细，顺便避免管道
  const res = spawnSync(p.cmd, p.args, { cwd: ROOT, stdio: 'inherit' });
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  let ok = res.status === 0;
  let note = '';
  if (res.error) {
    ok = false;
    note = p.cmd !== process.execPath ? `找不到解释器 ${p.cmd}（可用 PYTHON=… 指定）` : String(res.error.message);
  } else if (res.signal) {
    ok = false;
    note = '被信号中断 ' + res.signal;
  }
  results.push({ file: p.file, ok, secs, note, net: !!p.net });
}

console.log('\n=== 汇总 ===');
for (const r of results) {
  const mark = r.ok ? '[OK]  ' : '[FAIL]';
  console.log(`${mark} ${r.file.padEnd(20)} ${r.secs}s${r.net ? '  [联网]' : ''}${r.note ? '  ' + r.note : ''}`);
}
const pass = results.filter(r => r.ok).length;
const failed = results.filter(r => !r.ok);
console.log(`\n通过 ${pass}/${results.length}`);
if (failed.length) {
  console.log('未通过：' + failed.map(r => r.file).join('、'));
  process.exit(1);
}
console.log('全部通过。');
