// 标记点列表：排序 / 全选半选 / 列表渲染 / 单个与批量删除 /
//             KML / 复制表格 / 点行跳转（地图 + 视频帧）
//
// 做法和 test_sync.js 一样：把页面里的真函数抽出来，配最小 DOM 桩执行，
// 断言的是真实行为，不是「源码里有没有这行字」。
const fs = require('fs');
const path = require('path');

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

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

// ---------- 最小 DOM 桩 ----------
function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    children: [],
    textContent: '',
    className: '',
    type: '',
    checked: false,
    indeterminate: false,
    disabled: false,
    style: {},
    title: '',
    value: '',
    dataset: {},
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, removeEventListener() {},
    focus() {}, select() {}, click() {},
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return '' },
    set(_v) { this.children = [] },
  });
  return el;
}

const el = {
  markerList: makeEl('div'),
  markerCount: makeEl('span'),
  markerSelectAll: makeEl('input'),
  markerDeleteBtn: makeEl('button'),
  markerKmlBtn: makeEl('button'),
  markerCopyBtn: makeEl('button'),
};

const code = `
${extractFn('formatTime')}
${extractFn('sortedMarkers')}
${extractFn('selectedMarkers')}
${extractFn('updateMarkerBar')}
${extractFn('renderMarkerList')}
${extractFn('pickedForExport')}
${extractFn('markerKmlFileName')}
${extractFn('kmlEscape')}
${extractFn('buildMarkersKml')}
${extractFn('markersTsv')}
async ${extractFn('deleteMarkers')}
${extractFn('jumpToMarker')}
return {
  sortedMarkers, selectedMarkers, updateMarkerBar, renderMarkerList, pickedForExport,
  markerKmlFileName, buildMarkersKml, markersTsv, kmlEscape, deleteMarkers, jumpToMarker,
  getMarkers: () => projectMarkers,
  getChecked: () => markerChecked,
  getActive: () => activeMarkerId
};`;

const calls = { setView: [], opened: [], saved: 0, drew: 0, alerts: [], confirmAnswer: true };
const markerList = el.markerList;

const build = new Function(
  'projectMarkers', 'markerChecked', 'activeMarkerId',
  'markerList', 'markerCount', 'markerSelectAll',
  'markerDeleteBtn', 'markerKmlBtn', 'markerCopyBtn',
  'videoStatus', 'drawProjectMarkers', 'saveProjectMarkers',
  'map', 'geoFiles', 'videoPathFromGeojson', 'openVideoFromPopup',
  'shortFileName', 'formatTime', 'projectSelect', 'TRACK_FOCUS_ZOOM',
  'alert', 'confirm', 'document',
  code
);

function fresh(markers) {
  const state = {
    projectMarkers: markers,
    markerChecked: new Set(),
    activeMarkerId: '',
  };
  const api = build(
    state.projectMarkers, state.markerChecked, state.activeMarkerId,
    markerList, el.markerCount, el.markerSelectAll,
    el.markerDeleteBtn, el.markerKmlBtn, el.markerCopyBtn,
    { textContent: '' },
    () => { calls.drew++; },
    async () => { calls.saved++; },
    { setView: (ll, z) => calls.setView.push([ll, z]) },
    geoFiles,
    (p) => String(p).replace(/\.geojson$/i, '.mp4'),
    (enc) => calls.opened.push(JSON.parse(decodeURIComponent(enc))),
    (s) => String(s),
    (t) => Number(t).toFixed(3),
    { value: '东莞2' },
    16,
    (m) => calls.alerts.push(String(m)),
    () => calls.confirmAnswer,
    { createElement: makeEl, body: { appendChild() {}, removeChild() {} } }
  );
  // 让函数里对 projectMarkers 的重新赋值能被外面看到（删完要检查）
  return { api, state, markers: () => api.getMarkers(), checked: () => api.getChecked() };
}

const A = { id: 'a', name: '1 号排水口', lat: 23.03441, lng: 112.466997, video: 'DJI_x_0001_V.mp4', time: 608.274, created: '2026-10-05T01:00:00.000Z' };
const B = { id: 'b', name: '2 号 <桥下> & "涵洞"', lat: 23.040001, lng: 112.470002, video: 'DJI_x_0001_T.mp4', time: 30.5, created: '2026-10-05T02:00:00.000Z' };
const C = { id: 'c', name: '3 号取水口', lat: 23.05, lng: 112.48, video: 'DJI_x_0001_V.mp4', time: 12, created: '2026-10-05T00:30:00.000Z' };

const geoFiles = [
  { relative_path: 'DJI_x_0001_V.geojson', folder_index: 0 },
  { relative_path: 'DJI_x_0001_T.geojson', folder_index: 1 },
];

console.log('=== 1) 按创建时间排序：新的在上面 ===');
{
  const r = fresh([A, B, C]);
  const order = r.api.sortedMarkers().map(m => m.id);
  chk(order.join(',') === 'b,a,c', '乱序进、按 created 降序出（新 -> 旧）', order.join(','));
  chk(r.api.sortedMarkers() !== r.markers(), '排序返回副本，不改动原数组');
}

console.log('\n=== 2) 全选 / 半选态 ===');
{
  const r = fresh([A, B, C]);
  r.api.renderMarkerList();
  chk(el.markerSelectAll.checked === false && el.markerSelectAll.indeterminate === false,
    '一个都没勾：既不是全选也不是半选');

  r.checked().add('a');
  r.api.updateMarkerBar();
  chk(el.markerSelectAll.indeterminate === true && el.markerSelectAll.checked === false,
    '勾 1/3：半选态');
  chk(String(el.markerCount.textContent).indexOf('已选 1 / 共 3') >= 0,
    '计数写成「已选 n / 共 m」', String(el.markerCount.textContent));

  r.checked().add('b'); r.checked().add('c');
  r.api.updateMarkerBar();
  chk(el.markerSelectAll.checked === true && el.markerSelectAll.indeterminate === false,
    '全勾：全选态、无半选');
}

console.log('\n=== 3) 列表渲染 ===');
{
  const r = fresh([A, B, C]);
  el.markerList.children = [];
  r.api.renderMarkerList();

  const rows = el.markerList.children;
  chk(rows.length === 3, '三条标记点渲染三行', String(rows.length));
  chk(rows[0].className.indexOf('marker-row') === 0, '每行是 .marker-row');
  chk(rows[0].children.length === 5, '每行 5 个元素：[✓] 名称 纬度 经度 [×]', String(rows[0].children.length));
  chk(rows[0].children[0].type === 'checkbox', '第 1 格是复选框');
  chk(rows[0].children[4].textContent === '×', '最后一格是单个删除的 ×');
  chk(rows[0].children[1].textContent === B.name, '第 2 格是名称（最新的排最前）', rows[0].children[1].textContent);
  chk(rows[0].children[2].textContent === '23.040001' && rows[0].children[3].textContent === '112.470002',
    '纬度 / 经度各占一格，6 位小数', rows[0].children[2].textContent + ',' + rows[0].children[3].textContent);
  chk(el.markerDeleteBtn.disabled === false, '有标记点时批量按钮可用');

  const empty = fresh([]);
  el.markerList.children = [];
  empty.api.renderMarkerList();
  chk(el.markerList.children.length === 1 && /还没有标记点/.test(el.markerList.children[0].textContent),
    '没有标记点时给出说明文字，而不是空白列表');
  chk(el.markerDeleteBtn.disabled === true, '没有标记点时批量按钮禁用');
}

console.log('\n=== 4) 单个删除 / 批量删除 ===');
{
  // deleteMarkers 是 async，但「改数组 + 重画 + 写回」都在第一个 await 之前完成，
  // 所以直接同步断言；写回用的是一个 async 桩，调用发生在同步段里。
  const r = fresh([A, B, C]);
  r.api.renderMarkerList();
  calls.confirmAnswer = true;
  r.api.deleteMarkers(['b'], true);
  chk(r.markers().length === 2 && !r.markers().some(m => m.id === 'b'),
    '单个 × 删除：确认后少一个', r.markers().map(m => m.id).join(','));
  chk(calls.saved === 1, '删除后写回项目（saveProjectMarkers 被调用）');
  chk(calls.drew === 1, '删除后重画地图上的点');

  const r0 = fresh([A, B, C]);
  calls.confirmAnswer = false;
  r0.api.deleteMarkers(['b'], true);
  chk(r0.markers().length === 3, '单个 × 删除点「取消」：不删（和批量一样要二次确认）');

  const r2 = fresh([A, B, C]);
  calls.confirmAnswer = false;
  r2.api.deleteMarkers(['a', 'b'], true);
  chk(r2.markers().length === 3, '批量删除时点「取消」：一个都不删');
  calls.confirmAnswer = true;

  const r3 = fresh([A, B, C]);
  r3.checked().add('a');
  r3.checked().add('c');
  r3.api.deleteMarkers(['a', 'c'], true);
  chk(r3.markers().length === 1 && r3.markers()[0].id === 'b',
    '批量删除：勾中的都删掉，没勾的留下', r3.markers().map(m => m.id).join(','));
  chk(r3.checked().size === 0, '删掉的点从勾选集合里一并清掉');
}

console.log('\n=== 5) 复制「名称 + 纬度 + 经度」表格 ===');
{
  const r = fresh([A, B, C]);
  const tsv = r.api.markersTsv(r.api.sortedMarkers());
  const lines = tsv.split('\r\n');
  chk(lines.length === 4, '表头 + 3 行', String(lines.length));
  chk(lines[0] === '名称\t纬度\t经度', '第一行是表头（制表符分隔，粘 Excel 正好三列）', lines[0]);
  chk(lines[1] === '2 号 <桥下> & "涵洞"\t23.040001\t112.470002', '数据行按创建时间倒序（最新在前）', lines[1]);
  chk(lines[1].split('\t').length === 3, '每行三列');
}

console.log('\n=== 6) 导出 KML ===');
{
  const r = fresh([A, B]);
  const kml = r.api.buildMarkersKml(r.api.sortedMarkers());
  chk((kml.match(/<Placemark>/g) || []).length === 2, '每个点一个 Placemark',
    String((kml.match(/<Placemark>/g) || []).length));
  chk(/<coordinates>112\.466997,23\.03441,0<\/coordinates>/.test(kml),
    '坐标是 经度,纬度,0（KML 的顺序，写反了会飞到南极）');
  chk(kml.indexOf('&lt;桥下&gt;') > 0 && kml.indexOf('&amp;') > 0 && kml.indexOf('&quot;涵洞&quot;') > 0,
    '名称里的 < > & " 都转义了（否则 KML 直接是坏 XML）');
  chk (/<name>东莞2<\/name>/.test(kml), 'Document 名字用当前项目名');
  chk(kml.indexOf('<?xml') === 0, '带 XML 声明');

  const fname = r.api.markerKmlFileName();
  chk(/^标记点_东莞2_\d{4}-\d{2}-\d{2}\.kml$/.test(fname), '文件名是 标记点_<项目名>_<日期>.kml', fname);
}

console.log('\n=== 7) 点一行：地图跳 16 级 + 视频跳到那一帧 ===');
{
  const r = fresh([A, B, C]);
  calls.setView.length = 0; calls.opened.length = 0;
  r.api.jumpToMarker('a');
  chk(calls.setView.length === 1, '地图跳了一次');
  chk(calls.setView[0][0][0] === A.lat && calls.setView[0][0][1] === A.lng, '跳到该点坐标');
  chk(calls.setView[0][1] === 16, '缩放级别 16', String(calls.setView[0][1]));
  chk(r.api.getActive() === 'a', '该行被记为当前行（列表里高亮）');

  chk(calls.opened.length === 1, '打开了视频');
  const p = calls.opened[0];
  chk(p.relative_path === A.video, '视频用标记点里存的那一路', p.relative_path);
  chk(p.video_start === A.time, '从该点的时间开始播（不是从 0）', String(p.video_start));
  chk(p.folder_index === 0, '文件夹序号是从已扫到的文件列表反查的', String(p.folder_index));

  calls.opened.length = 0;
  r.api.jumpToMarker('b');
  chk(calls.opened[0].folder_index === 1 && calls.opened[0].relative_path === B.video,
    '换一路视频（热成像）时文件夹序号也跟着换');

  // 没有视频信息的点：只跳地图，不报错
  calls.opened.length = 0;
  const r2 = fresh([{ id: 'z', name: '地图点', lat: 23, lng: 112, video: '', time: 0, created: '' }]);
  r2.api.jumpToMarker('z');
  chk(calls.opened.length === 0, '没有视频信息的点不会去打开视频');
}

console.log('\n=== 8) 一个都没勾就点导出：页面提示 ===');
{
  const r = fresh([A, B, C]);
  calls.alerts.length = 0;
  chk(r.api.pickedForExport() === null, '返回 null（调用方不再往下走）');
  chk(calls.alerts.length === 1 && /请先选择要导出的标记点/.test(calls.alerts[0]), '弹出「请先选择要导出的标记点」的提示', calls.alerts[0]);

  r.checked().add('a');
  const picked = r.api.pickedForExport();
  chk(Array.isArray(picked) && picked.length === 1 && picked[0].id === 'a', '勾了就返回勾选的点');
}

console.log(ok ? '\n结果: 全部通过' : '\n结果: 有失败');
process.exit(ok ? 0 : 1);
