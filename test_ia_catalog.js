// P3c 接线验证：勾选语义 / 运行时映射 / 不可上图禁用 / 生成入口 / 计数口径。
//
// 静态断言为主（DOM 是 JS 现场生成），但**关键状态用真跑函数**：
// iaCatalogRow / IA_TYPE_GROUP 抽不出来（依赖大量闭包），
// 所以这里验证「结构 + 文案 + 守卫」，行为由 test_content_index.py（后端）与
// test_ia_group.js（分组勾选纯函数）覆盖。

const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const HTML = process.argv[2] || path.join(ROOT, 'Code', 'project_geojson_preview.html');
const html = fs.readFileSync(HTML, 'utf8');

let ok = true;
const chk = (c, label, extra = '') => {
  if (!c) ok = false;
  console.log(`  [${c ? 'OK' : 'FAIL'}] ${label}${extra ? ' -> ' + extra : ''}`);
};
const seg = (a, b) => {
  const i = html.indexOf(a);
  const j = b ? html.indexOf(b, i + 1) : html.length;
  return i >= 0 && j > i ? html.slice(i, j) : '';
};

console.log('\n=== 1) 成员来自 catalog，不再由内存集合决定 ===');
{
  const build = seg('function iaBuild(){', 'async function iaRemoveMarker(');
  chk(/iaState\.catalog&&iaState\.catalog\.items/.test(build), 'iaBuild 读 catalog.items 作为成员来源');
  chk(/IA_TYPE_ORDER\.forEach/.test(build), '按类型顺序分组');
  // 旧的「直接遍历 loadedTracks 生成视频行」必须消失
  chk(!/loadedTracks'\)\.forEach/.test(build), '不再遍历 loadedTracks 生成视频行');
  chk(!/photoGroups\?photoGroups:\[\]\)\.forEach/.test(build), '不再遍历 photoGroups 生成照片行');
  const reload = seg('async function iaReload', 'async function iaAddSource');
  chk(/content-index\?name=/.test(reload), 'iaReload 拉取 /api/project/content-index');
  chk(/iaState\.catalog=cat/.test(reload), 'catalog 存进 iaState');
}

console.log('\n=== 2) 运行时只回答"能不能画" ===');
{
  chk(/function iaFindTrack\(/.test(html), '视频/航迹按 relative_path 匹配运行时航迹');
  chk(/function iaFindPhotoIndex\(/.test(html), '照片按成员文件名找组下标（不是数组下标当身份）');
  chk(/function iaFindOrtho\(/.test(html) && /function iaFindCoverage\(/.test(html),
    '正射/覆盖按名字匹配运行时条目');
  const apply = seg('function iaApply(kind, it, shown){', 'function iaSetShown');
  chk(/const rt=it\.runtime\|\|kind/.test(apply), '显隐应用按 runtime 分派');
  chk(/rt==='track-group'/.test(apply), '航迹/视频 -> 图层组');
  chk(/rt==='photo-index'/.test(apply), '照片 -> photoHidden + renderPhotoLayer');
  chk(/iaShowOrthoItem\(it, shown\)/.test(apply) && /iaShowCoverageItem\(it, shown\)/.test(apply),
    '正射/覆盖复用单图层按条函数（含互斥与幂等）');
}

console.log('\n=== 3) 不可上图的行禁用勾选并解释 ===');
{
  const row = seg('function iaCatalogRow(it){', 'async function iaGenerateTracks');
  for (const t of ['subtitle', 'unknown', 'meta', 'coverage_export', 'vector']) {
    chk(new RegExp(`${t}`).test(row), `类型 ${t} 有判定分支`);
  }
  chk(/暂不可上图/.test(row) || /不能单独上图/.test(row), '禁用文案说明原因');
  chk(/勾选不触发生成/.test(row), '明确「勾选不触发生成」');
  const render = seg('function iaRenderContents(){', 'function iaRenderNotice');
  chk(/canToggle=it\.canToggle!==false/.test(render), '渲染时按 canToggle 决定是否可勾选');
  chk(/cb\.disabled=true/.test(render), '不可上图时 checkbox 禁用');
  chk(/cb\.title=it\.disabledTitle/.test(render), '禁用时给出 title 解释');
  const setShown = seg('function iaSetShown(it){', 'async function iaShowOrthoItem');
  chk(/it\.canToggle===false/.test(setShown), 'iaSetShown 有守卫（不会静默改变）');
}

console.log('\n=== 4) 生成入口：复用现有 Build tracks（项目级）===');
{
  chk(/function iaGenerateTracks\(/.test(html), '有生成入口函数');
  const gen = seg('async function iaGenerateTracks', 'function iaBuild(){');
  chk(/runAutoPipeline/.test(gen), '调用现有 runAutoPipeline（Build tracks）');
  chk(!/srt|geojson.*write|build_tracks/i.test(gen.replace(/runAutoPipeline/g, '')),
    '不复制生成算法（没有自造 SRT/GeoJSON 逻辑）');
  chk(/整个项目/.test(gen), '明确告知是项目级');
  chk(/askConfirm/.test(gen), '生成前要确认');
  chk(/!\(it\.artifacts&&it\.artifacts\.track\)/.test(html), '只在缺航迹时给生成入口');
  const render = seg('function iaRenderContents(){', 'function iaRenderNotice');
  chk(/gen\.textContent='⚙'/.test(render), '行内有 ⚙ 生成按钮');
}

console.log('\n=== 5) 计数口径 ===');
{
  chk(/unique_files/.test(html), '用 catalog 的 unique_files');
  chk(/唯一文件/.test(html), '文案说明「唯一文件」');
  chk(/项目对象：位置点/.test(html), '项目对象单独计数');
  chk(/组）/.test(html) || /groupCount/.test(html), '分组数也标出来');
}

console.log('\n=== 6) 地图/播放器与回退入口未被破坏 ===');
{
  chk(/id="legacyLeft" hidden/.test(html), '旧左栏回退入口仍在');
  chk(/iaLegacyToggle/.test(html), '回退按钮仍在');
  chk(html.indexOf('<section class="col col-mid">') < html.indexOf('<section class="col col-right"'),
    '中栏/右栏顺序未变');
}

console.log(`\n结果: ${ok ? '全部通过' : '有失败项'}`);
process.exit(ok ? 0 : 1);
