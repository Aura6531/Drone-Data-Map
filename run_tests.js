#!/usr/bin/env node
// 一次跑完全部测试套件；任何一套失败就非零退出。
//
// 为什么需要这个文件：
//   node 只执行命令行里的【第一个】脚本 —— 写 `node check_page.js test_boot.js …`
//   时，后面的文件名会被静默忽略，而且照样打印「全部通过」并 exit 0（假绿）。
//   这个坑在本项目里真实踩过：文档里的两行命令实际只覆盖了 12 套里的 2 套。
//
// 用法：
//   node run_tests.js                # 12 套（不含需要联网的那套）
//   node run_tests.js --with-net     # 额外跑 test_tdt_tiles.py（会请求天地图瓦片）
//   node run_tests.js --list         # 只列清单，不执行
//
// 环境变量：
//   PYTHON=python3   指定 python 解释器（默认 windows 用 python，其它平台 python3）
//
// 所有路径按「脚本所在目录」推导，换机器 / 换盘符都不用改。

const { spawnSync } = require('child_process');
const path = require('path');

const ROOT = __dirname;
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

const NODE_SUITES = [
  'check_page.js',      // 页面静态断言（最全的一套）
  'test_boot.js',       // 页面顶层脚本真跑一遍
  'test_sync.js',       // 地图 / 视频同步路径
  'test_telemetry.js',  // 遥测换算
  'test_footprint.js',  // 相机视场几何
  'test_filelist.js',   // 文件列表
  'test_drone.js',      // 飞机箭头朝向
  'test_follow.js',     // 地图跟随
  'test_nearest.js',    // 按位置检索（用真实 GeoJSON）
  'test_ab.js',         // A+B 检索的数学基础（正/反投影互逆）
  'test_markers.js',    // 标记点列表（排序/勾选/删除/KML/复制/跳转）
];
const PY_SUITES = [
  'check_py.py',        // 后端静态断言
  'test_geocode.py',    // 地理编码 / key 优先级
];
const NET_SUITES = [
  'test_tdt_tiles.py',  // 天地图瓦片连通性（需要联网 + 有效 tk）
];

const argv = process.argv.slice(2);
const withNet = argv.includes('--with-net');
const listOnly = argv.includes('--list');

const plan = [];
for (const f of NODE_SUITES) plan.push({ file: f, cmd: process.execPath, args: [path.join(ROOT, f)] });
for (const f of PY_SUITES) plan.push({ file: f, cmd: PYTHON, args: ['-B', path.join(ROOT, f)] });
if (withNet) for (const f of NET_SUITES) plan.push({ file: f, cmd: PYTHON, args: ['-B', path.join(ROOT, f)], net: true });

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
