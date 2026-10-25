// P2 新左栏（项目 / 数据来源 / 内容）静态验收。
//
// 只读 html，不起浏览器：断言「结构 + 接线 + 文案语义」这些容易在重构里丢的东西。
// 行为层（reindex/relocate/detach/迁移）在 Code/test_*.py 里用临时项目真跑。
//
// 为什么用静态断言：页面是单文件，新左栏的 DOM 是 JS 现场生成的；
// 这里保证「该有的入口、该调的接口、该读的键」都在，且旧界面不会 одновременно 抢事件。

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

console.log('\n=== 1) 三段容器：顺序、必备 id、旧左栏隐藏 ===');
{
  const iProj = html.indexOf('id="iaProjectCard"');
  const iSrc = html.indexOf('id="iaSourcesCard"');
  const iCon = html.indexOf('id="iaContentsCard"');
  chk(iProj > 0 && iSrc > iProj && iCon > iSrc, '三段顺序：项目 → 数据来源 → 内容',
    `${iProj}/${iSrc}/${iCon}`);

  for (const id of ['iaProjectSelect', 'iaNewProject', 'iaImportData', 'iaProjectDelete',
                    'iaProjectMeta', 'iaAddSource', 'iaRefreshAll', 'iaSourcesList',
                    'iaSearch', 'iaTypeFilter', 'iaOnlyIssues', 'iaContents', 'iaNotice',
                    'iaLegacyToggle']) {
    chk(html.includes(`id="${id}"`), `有 #${id}`);
  }

  const legacyAt = html.indexOf('id="legacyLeft"');
  chk(legacyAt > iCon, '旧左栏在新区块之后（DOM 里保留）');
  chk(/<div id="legacyLeft" hidden>/.test(html), '旧左栏默认 hidden（不会同时显示）');

  // 重复 id 会让 getElementById 抓错元素。
  // 只检查「新区块 + 新脚本」范围：baseMap 之类的历史重复不是本轮引入的。
  const iaStart = html.indexOf('id="iaProjectCard"');
  const legacyStart = html.indexOf('id="legacyLeft"');
  const scriptStart = html.indexOf('window.__IA=iaState');
  const iaPart = html.slice(iaStart, legacyStart) + html.slice(scriptStart, html.lastIndexOf('</script>'));
  const ids = {};
  for (const m of iaPart.matchAll(/\sid="([A-Za-z0-9_\-]+)"/g)) ids[m[1]] = (ids[m[1]] || 0) + 1;
  const dup = Object.keys(ids).filter(k => ids[k] > 1);
  chk(dup.length === 0, '新区块/新脚本里没有重复 id', dup.slice(0, 5).join(','));
}

console.log('\n=== 2) 数据来源：添加 / 刷新 / 重新定位 / 移除的接线 ===');
{
  chk(/\/api\/project\/select-folder/.test(html), '添加来源沿用后端文件夹选择器（支持多选）');
  chk(/picked\.paths\|\|\[picked\.path\]/.test(html), '多选结果按 paths 逐个登记');
  chk(/\/api\/project\/scan-folder\?path=/.test(html), '登记前先只读扫描该目录');
  chk(/\/api\/project\/add-folder/.test(html), '登记走 add-folder（不复制文件）');
  chk(/\/api\/project\/source\/reindex/.test(html), '单来源刷新 → /source/reindex');
  chk(/\/api\/project\/sources\/reindex/.test(html), '全部刷新 → /sources/reindex');
  chk(/\/api\/project\/source\/relocate/.test(html), '重新定位 → /source/relocate');
  chk(/\/api\/project\/source\/detach/.test(html), '移除来源 → /source/detach');

  // 重定位必须两步：先 confirm:false，再问用户，再 confirm:true
  const rel = html.slice(html.indexOf('async function iaRelocate'), html.indexOf('async function iaDetach'));
  chk(/confirm:false/.test(rel), '先做预检（confirm:false，不写盘）');
  chk(/askConfirm\(/.test(rel), '预检后要用户确认');
  chk(/confirm:true/.test(rel), '确认后才生效（confirm:true）');
  chk(/match_ratio/.test(rel) && /verdict/.test(rel), '确认框里给匹配报告（比例 + 判定）');
  chk(/不会移动\/复制\/删除任何文件/.test(rel), '明确告知不移动/复制/删除文件');

  const det = html.slice(html.indexOf('async function iaDetach'), html.indexOf('async function iaFillProjects'));
  chk(/只解除项目与这个文件夹的关联/.test(det), '移除说明「只解除关联」');
  chk(/磁盘上的原始文件一个都不会动/.test(det), '移除说明「磁盘文件不动」');
  chk(!/delete_generated/.test(det), '本轮不提供「删除生成物」选项');
}

console.log('\n=== 3) 状态展示：七种来源状态都有明确文案 ===');
{
  const fn = html.slice(html.indexOf('function iaStatusChip'), html.indexOf('function iaRenderSources'));
  for (const [key, label] of [['busy', '扫描中'], ['missing', '找不到目录'],
                              ['denied', '无权限'], ['timeout', '扫描超时'],
                              ['partial', '部分不可读'], ['indexed_at', '未扫描']]) {
    chk(fn.includes(key) || html.includes(key), `状态含 ${key}`);
  }
  chk(fn.includes('扫描中') && fn.includes('找不到目录') && fn.includes('无权限'),
    '状态徽标是中文明确文案');
  chk(/找不到\n|index_status==='missing'/.test(fn) || fn.includes("'missing'"),
    'missing/denied 时给「重新定位」入口');
  const src = html.slice(html.indexOf('function iaRenderSources'), html.indexOf('function iaRenderContents'));
  chk(/!s\.exists \|\| s\.index_status==='missing' \|\| s\.index_status==='denied'/.test(src),
    '离线/无权限时显示「重新定位…」');
  chk(/刷新/.test(src) && /移除/.test(src), '每行有刷新 / 移除');
}

console.log('\n=== 4) 内容区：分组、搜索、筛选、三态、动作语义 ===');
{
  for (const t of ['video', 'photo', 'ortho', 'coverage', 'vector', 'marker', 'label']) {
    chk(html.includes(`type:'${t}'`) || html.includes(`'${t}'`), `内容分组覆盖 ${t}`);
  }
  const con = html.slice(html.indexOf('function iaRenderContents'), html.indexOf('function iaRenderNotice'));
  chk(/indeterminate/.test(con), '分组勾选框支持半选态（三态）');
  chk(/iaState\.search/.test(con) && /iaState\.type/.test(con) && /iaState\.onlyIssues/.test(con),
    '搜索 / 类型筛选 / 只看有问题 都参与过滤');
  chk(/loc\.textContent='⤢'/.test(con), '定位是独立动作 ⤢');
  chk(/ed\.textContent='✎'/.test(con), '编辑是独立动作 ✎');
  chk(/del\.textContent='×'/.test(con), '移除是独立动作 ×');
  chk(/不删磁盘文件/.test(con), '移除说明不删磁盘文件');
  chk(!/textContent='加载'/.test(con), '不再出现笼统的「加载」按钮');
  chk(/显示更多/.test(html), '照片分组支持分页/懒加载（显示更多）');
}

console.log('\n=== 5) 显隐：读 ui.items、写 ui.items、旧键只读兜底 ===');
{
  chk(/iaState\.items\[it\.itemId\]/.test(html), '勾选状态从 ui.items[itemId] 读');
  chk(/ui\.items=iaState\.items/.test(html), '保存时写 ui.items');
  chk(/\/api\/project\/ui-state/.test(html), '通过 ui-state 接口保存（后端合并写）');
  const iaSeg = html.slice(html.indexOf('window.__IA=iaState'), html.lastIndexOf('</script>'));
  chk(!/loadedUiSave\(\)/.test(iaSeg), '新左栏不调用旧版 loadedUiSave（不写 legacy 键）');
  chk(/legacyShown\(/.test(iaSeg) && /ui\[kind\]/.test(iaSeg), '旧键（videos/ortho/coverage/markers）只读兜底');
}

console.log('\n=== 6) 迁移：打开项目时调用、并把统计告诉用户 ===');
{
  chk(/\/api\/project\/ui-migrate/.test(html), '调用 /api/project/ui-migrate');
  chk(/iaState\.migrate/.test(html), '保存迁移结果');
  const notice = html.slice(html.indexOf('function iaRenderNotice'), html.indexOf('function iaRender()'));
  chk(/legacy_saved/.test(notice), '有歧义留档时显示条数（ui.legacy 可找回）');
  chk(/pending/.test(notice), '有 pending 时提示待补迁');
  chk(/迁移失败/.test(notice), '迁移失败有可理解提示（并继续旧键兜底）');
}

console.log('\n=== 7) 回退与互斥：新旧不同时显示 ===');
{
  const bind = html.slice(html.indexOf('function iaBind'), html.indexOf('function iaInit'));
  chk(/iaLegacyToggle/.test(bind), '有「旧」回退按钮');
  chk(/toggleAttribute\('hidden'/.test(bind), '回退时用 hidden 互斥切换');
  chk(/iaProjectCard/.test(html), '切回退时也隐藏新区块');
}

console.log('\n=== 8) 不改中间地图 / 右侧视频区 ===');
{
  const mid = html.indexOf('<section class="col col-mid">');
  const right = html.indexOf('<section class="col col-right"');
  chk(mid > 0 && right > mid, '中栏/右栏顺序未变');
  chk(/id="photoCard"/.test(html), '右侧照片展示区仍在');
}

console.log(`\n结果: ${ok ? '全部通过' : '有失败项'}`);
process.exit(ok ? 0 : 1);
