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
    clientWidth: 0,
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c) },
      remove(c) { this._set.delete(c) },
      contains(c) { return this._set.has(c) },
      toggle(c, on) {
        if (on === undefined) { this._set.has(c) ? this._set.delete(c) : this._set.add(c) }
        else if (on) { this._set.add(c) } else { this._set.delete(c) }
        return this._set.has(c);
      },
    },
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
  markerReportBtn: makeEl('button'),
};

const code = `
${extractFn('formatTime')}
${extractFn('nextMarkerName')}
${extractFn('markerListLayout')}
${extractFn('applyMarkerLayout')}
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
  nextMarkerName, markerListLayout, applyMarkerLayout,
  sortedMarkers, selectedMarkers, updateMarkerBar, renderMarkerList, pickedForExport,
  markerKmlFileName, buildMarkersKml, markersTsv, kmlEscape, deleteMarkers, jumpToMarker,
  getMarkers: () => projectMarkers,
  getChecked: () => markerChecked,
  getActive: () => activeMarkerId
};`;

const calls = { setView: [], opened: [], autoPlay: [], saved: 0, drew: 0, alerts: [], confirmAnswer: true };
const markerList = el.markerList;

const build = new Function(
  'projectMarkers', 'markerChecked', 'activeMarkerId',
  'markerList', 'markerCount', 'markerSelectAll',
  'markerDeleteBtn', 'markerKmlBtn', 'markerCopyBtn',
  'markerReportBtn', 'reportAvailable',
  'videoStatus', 'drawProjectMarkers', 'saveProjectMarkers',
  'map', 'geoFiles', 'videoPathFromGeojson', 'openVideoFromPopup',
  'shortFileName', 'formatTime', 'projectSelect', 'TRACK_FOCUS_ZOOM',
  'alert', 'confirm', 'document',
  code
);

function fresh(markers, reportAvailable = true) {
  const state = {
    projectMarkers: markers,
    markerChecked: new Set(),
    activeMarkerId: '',
  };
  const api = build(
    state.projectMarkers, state.markerChecked, state.activeMarkerId,
    markerList, el.markerCount, el.markerSelectAll,
    el.markerDeleteBtn, el.markerKmlBtn, el.markerCopyBtn,
    el.markerReportBtn, reportAvailable,
    { textContent: '' },
    () => { calls.drew++; },
    async () => { calls.saved++; },
    { setView: (ll, z) => calls.setView.push([ll, z]) },
    geoFiles,
    (p) => String(p).replace(/\.geojson$/i, '.mp4'),
    (enc, autoPlay) => {
      calls.opened.push(JSON.parse(decodeURIComponent(enc)));
      calls.autoPlay.push(autoPlay);
    },
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

  const noDeps = fresh([A], false);
  noDeps.api.renderMarkerList();
  chk(el.markerReportBtn.disabled === true,
    '服务端缺 python-docx/Pillow/ffmpeg 时「生成 Word 报告」停用（其余三个照常可用）');
  chk(el.markerDeleteBtn.disabled === false, '缺报告依赖不影响删除/导出/复制');
  fresh([A]).api.renderMarkerList();
  chk(el.markerReportBtn.disabled === false, '依赖齐全时报告按钮可用');

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
  chk(calls.autoPlay[0] === false,
    '点标记点跳转：明确要求「只定位、不自动播放」', String(calls.autoPlay[0]));

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

console.log('\n=== 8) 一个都没勾就点导出：页面提示 ===');{
  const r = fresh([A, B, C]);
  calls.alerts.length = 0;
  chk(r.api.pickedForExport() === null, '返回 null（调用方不再往下走）');
  chk(calls.alerts.length === 1 && /请先选择要导出的标记点/.test(calls.alerts[0]), '弹出「请先选择要导出的标记点」的提示', calls.alerts[0]);

  r.checked().add('a');
  const picked = r.api.pickedForExport();
  chk(Array.isArray(picked) && picked.length === 1 && picked[0].id === 'a', '勾了就返回勾选的点');
}

console.log('\n=== 9) 右键取点的默认名字：项目名-序号 ===');
{
  const r = fresh([
    { id: 'a', name: '东莞2-1', lat: 23.03, lng: 112.46, created: '2026-10-05T01:00:00Z' },
    { id: 'b', name: '东莞2-3', lat: 23.04, lng: 112.47, created: '2026-10-05T02:00:00Z' },
    { id: 'x', name: '随手起的名字', lat: 23.05, lng: 112.48, created: '2026-10-05T03:00:00Z' },
  ]);
  chk(r.api.nextMarkerName() === '东莞2-4',
    '取已有的最大序号 + 1（删过中间号也不会重号）', r.api.nextMarkerName());

  const empty = fresh([]);
  chk(empty.api.nextMarkerName() === '东莞2-1', '还没有点时从 1 开始', empty.api.nextMarkerName());

  const other = fresh([{ id: 'a', name: '别的项目-9', lat: 23.03, lng: 112.46, created: '' }]);
  chk(other.api.nextMarkerName() === '东莞2-1', '不把别的项目名的点算进来', other.api.nextMarkerName());
}

console.log('\n=== 10) 列表排布：少则一栏 / 多了分栏 / 挤不下只留名称 ===');
{
  const r = fresh([]);
  const cases = [
    [5, 500, 1, false, '5 个点：一栏（每栏 8 行够放）'],
    [8, 500, 1, false, '8 个点：还是一栏'],
    [9, 300, 2, true, '9 个点 + 300px 宽：一栏放不下 -> 降级只留名称、并成 2 栏'],
    [20, 1000, 3, false, '20 个点 + 1000px 宽：3 栏，且不用降级（每栏约 333px）'],
    [40, 1000, 5, true, '40 个点 + 1000px 宽：要 5 栏，带经纬度只放得下 3 栏 -> 降级后 5 栏'],
    [0, 500, 1, false, '没有点时一栏'],
    [5, 0, 1, false, '量不到宽度时退回一栏（不报错）'],
  ];
  for (const [count, width, columns, compact, label] of cases) {
    const got = r.api.markerListLayout(count, width);
    chk(got.columns === columns && got.compact === compact, label,
      `count=${count} width=${width} -> ${got.columns} 栏 compact=${got.compact}`);
  }

  // 真的作用到 DOM 上：网格列数写进 style，密集模式加类
  el.markerList.clientWidth = 500;
  const few = fresh([A, B, C]);
  el.markerList.children = [];
  el.markerList.classList._set.clear();
  few.api.renderMarkerList();
  chk(el.markerList.style.gridTemplateColumns === 'repeat(1,minmax(0,1fr))',
    '5 个点以内不写多栏', el.markerList.style.gridTemplateColumns);
  chk(!el.markerList.classList.contains('marker-compact'), '不降级时不加 marker-compact');

  el.markerList.clientWidth = 300;
  const many = fresh(Array.from({ length: 20 }, (_, i) => ({
    id: 'm' + i, name: '点 ' + i, lat: 23 + i / 1000, lng: 112 + i / 1000, created: '',
  })));
  el.markerList.children = [];
  many.api.renderMarkerList();
  chk(el.markerList.classList.contains('marker-compact'), '点多了 + 栏窄：加上 marker-compact');
  chk(el.markerList.style.gridTemplateColumns === 'repeat(2,minmax(0,1fr))',
    '并成 2 栏', el.markerList.style.gridTemplateColumns);

  el.markerList.clientWidth = 0;
  el.markerList.classList._set.clear();
}

console.log('\n=== 11) 跳过去之后视频停在暂停态（不自动播） ===');
{
  // 抽出真的 startClip()，用假 videoPlayer 跑一遍：
  // 标记点入口（autoPlay=false）必须不调 play()，其它入口照旧自动播。
  const played = [];
  const syncCalls = [];
  let metaHandler = null;

  const videoStatus = { textContent: '' };
  const videoInfo = { textContent: '' };
  let currentTime = -1;

  const player = {
    readyState: 1,
    videoWidth: 1920,
    videoHeight: 1080,
    src: '',
    get currentTime() { return currentTime },
    set currentTime(v) { currentTime = v },
    pause() { played.push('pause') },
    play() { played.push('play'); return Promise.resolve() },
    load() {},
    addEventListener(name, fn) { if (name === 'loadedmetadata') metaHandler = fn },
    removeEventListener() {},
  };

  const buildStart = new Function(
    'clip', 'clipTimer', 'videoStopAt', 'proxyBucketOf', 'PROXY_SECONDS',
    'videoInfo', 'videoStatus', 'videoPlayer', 'syncDroneMarker', 'projectSelect',
    'videoStage', 'formatTime', 'fallbackToProxy', 'setTimeout', 'clearTimeout',
    `${extractFn('startClip')}\nreturn {startClip};`
  );

  function runStart(autoPlay) {
    played.length = 0;
    syncCalls.length = 0;
    metaHandler = null;
    currentTime = -1;
    videoStatus.textContent = '';
    videoInfo.textContent = '';

    const api = buildStart(
      {
        data: { video: 'x.mp4', video_end: 0 },
        start: 90, folderIndex: 0, path: 'a.mp4',
        useProxy: false, allowFallback: false, autoPlay,
      },
      null, null,
      (t) => Math.floor(t / 30) * 30, 30,
      videoInfo, videoStatus, player,
      (t) => syncCalls.push(t), { value: '东莞2' }, null,
      (t) => Number(t).toFixed(3), () => {},
      setTimeout, clearTimeout
    );

    api.startClip();
    if (metaHandler) metaHandler();     // 模拟元数据到达
  }

  runStart(false);
  chk(played.filter(x => x === 'play').length === 0, '标记点入口：play() 一次都没被调用',
    played.join(',') || '（空）');
  chk(currentTime === 90, '但确实定位到了该标记点的时间', String(currentTime));
  chk(/未自动播放/.test(videoStatus.textContent), '状态栏写明未自动播放', videoStatus.textContent);
  chk(/已定位到/.test(videoInfo.textContent), '信息栏也写成「已定位到」，不写「开始播放」',
    videoInfo.textContent);
  chk(syncCalls.length >= 2, '箭头/准星仍然同步到了该时刻', syncCalls.join(','));

  runStart(true);
  chk(played.filter(x => x === 'play').length === 1, '普通入口（从点击位置播放）：照旧自动播放',
    played.join(','));
  chk(currentTime === 90, '起播位置一样是该时刻');

  runStart(undefined);
  chk(played.filter(x => x === 'play').length === 1, '不传第三个参数时默认为自动播放（老调用不受影响）');
}

console.log('\n=== 12) 标记点名字不能跟已有的重复 ===');
{
  const errors = [];
  const added = [];
  let closed = 0;
  let saved = 0;
  const input = { value: '' };

  const buildConfirm = new Function(
    'projectMarkers', 'pendingMark', 'videoMarkName', 'addVideoMark',
    'saveProjectMarkers', 'renderMarkerList', 'closeVideoMarkDialog',
    'showVideoMarkError', 'projectSelect', 'clip', 'videoPlayer',
    `${extractFn('nextMarkerName')}
${extractFn('normalizeMarkerName')}
${extractFn('markerNameTaken')}
${extractFn('confirmVideoMark')}
return {confirmVideoMark, normalizeMarkerName, markerNameTaken, getPending: () => pendingMark};`
  );

  const make = (name) => ({ id: name, name, lat: 23, lng: 112, video: 'a.mp4', time: 1, created: '' });

  function run(existing, typed) {
    errors.length = 0;
    added.length = 0;
    closed = 0;
    saved = 0;
    input.value = typed;

    const markers = existing.slice();

    const api = buildConfirm(
      markers, { lat: 23.1, lng: 112.5 }, input,
      (ll, nm) => added.push(nm),
      async () => { saved++ },
      () => {},
      () => { closed++ },
      (message) => errors.push(message),
      { value: '东莞2' },
      { path: 'a.mp4' },
      { currentTime: 42 }
    );

    api.confirmVideoMark();

    return { markers, api };
  }

  const base = [make('东莞2-1'), make('3 号排水口')];

  let result = run(base, '东莞2-1');
  chk(added.length === 0 && result.markers.length === 2, '重名：不新增、不落库',
    `新增 ${added.length} 个，共 ${result.markers.length} 个`);
  chk(errors.length === 1 && /已经有叫「东莞2-1」的标记点/.test(errors[0]),
    '给出重名提示', errors[0]);
  chk(closed === 0, '重名时不关弹窗（让用户当场改）');
  chk(saved === 0, '重名时也不写回项目');

  result = run(base, '  东莞2-1  ');
  chk(errors.length === 1 && added.length === 0, '带首尾空格也算重名', errors[0]);

  result = run([make('Gate 1')], '  gate   1 ');
  chk(errors.length === 1 && added.length === 0,
    '忽略大小写与多余空白后算重名（Gate 1 / gate  1）', errors[0]);

  result = run(base, '新取水口');
  chk(added.length === 1 && added[0] === '新取水口', '不重名就正常新增', added.join(','));
  chk(errors.length === 0 && closed === 1 && saved === 1, '不重名：无提示、关弹窗、写回项目');
  const fresh = result.markers[result.markers.length - 1];
  chk(fresh.name === '新取水口' && fresh.video === 'a.mp4' && fresh.time === 42,
    '入库的字段照旧（名称 / 视频 / 时间）',
    `name=${fresh.name} video=${fresh.video} time=${fresh.time}`);
  chk(result.api.getPending() === null, '确定后清掉待落点，不会重复打点');

  result = run(base, '   ');
  chk(added.length === 1 && added[0] === '东莞2-2',
    '名字留空：回落到顺序默认名（且是没被占用的那个）', added.join(','));

  const api = run(base, 'x').api;
  chk(api.normalizeMarkerName('  A   B  ') === 'a b', '归一化：去空白 + 压空白 + 转小写',
    api.normalizeMarkerName('  A   B  '));
  chk(api.markerNameTaken('东莞2-1') === true, '查重：命中', 'true');
  chk(api.markerNameTaken('东莞2-1', '东莞2-1') === false,
    '查重：排除自己时不算（给以后改名留着）');
  chk(api.markerNameTaken('') === false, '空名字不算重名');
}

console.log('\n=== 13) 报告地图取景：目标点居中 + 18 级，飞机快出画才降级 ===');
{
  const width = Number((html.match(/REPORT_MAP_WIDTH=(\d+)/) || [])[1]);
  const height = Number((html.match(/REPORT_MAP_HEIGHT=(\d+)/) || [])[1]);
  const maxZoom = Number((html.match(/REPORT_MAP_MAX_ZOOM=(\d+)/) || [])[1]);
  const margin = Number((html.match(/REPORT_MAP_MARGIN=([\d.]+)/) || [])[1]);

  chk(maxZoom === 18, '默认取景 18 级（字看得清）', String(maxZoom));
  chk(width > 0 && height > 0 && margin > 1, '从页面里读到画面尺寸与余量',
    `${width}×${height}px，余量 ×${margin}`);

  const build = new Function(
    'REPORT_MAP_WIDTH', 'REPORT_MAP_HEIGHT', 'REPORT_MAP_MAX_ZOOM', 'REPORT_MAP_MARGIN',
    `${extractFn('reportMetersOffset')}
${extractFn('reportMapZoomForOffset')}
return {reportMetersOffset, reportMapZoomForOffset};`
  )(width, height, maxZoom, margin);

  const offset = build.reportMetersOffset;
  const zoomFor = build.reportMapZoomForOffset;

  // 偏移换算：正北 0.001° ≈ 111.3m，正东要按纬度收窄
  const north = offset({ lat: 23.05, lng: 114 }, { lat: 23.051, lng: 114 });
  const east = offset({ lat: 23.05, lng: 114 }, { lat: 23.05, lng: 114.001 });
  chk(Math.abs(north.north - 111.32) < 0.5 && Math.abs(north.east) < 1e-6,
    '正北偏移算成 north≈111m / east=0', JSON.stringify(north));
  chk(east.east > 90 && east.east < 111 && Math.abs(east.north) < 1e-6,
    '正东偏移按纬度收窄（23° 处 ≈ 102m）', JSON.stringify(east));

  chk(zoomFor(23.05, 0, 0) === 18, '飞机就在目标点：18 级', String(zoomFor(23.05, 0, 0)));
  chk(zoomFor(23.05, 100, 0) === 18, '飞机正北 100m：仍是 18 级（半高约 176m）',
    String(zoomFor(23.05, 100, 0)));
  chk(zoomFor(23.05, 0, 300) === 18, '飞机正东 300m：仍是 18 级（半宽约 440m）',
    String(zoomFor(23.05, 0, 300)));
  chk(zoomFor(23.05, 0, 400) === 17, '飞机正东 400m 超出半宽（440m）：降一级',
    String(zoomFor(23.05, 0, 400)));
  chk(zoomFor(23.05, -400, 0) === 16, '飞机正南 400m 超出半高（176m）：按需降到 16 级',
    String(zoomFor(23.05, -400, 0)));
  chk(zoomFor(23.05, 100000, 100000) === 10, '极远：退到下限 10 级就停',
    String(zoomFor(23.05, 100000, 100000)));

  // 降级之后，飞机在两个方向上确实都还塞得进画面
  for (const [n, e] of [[0, 0], [100, 0], [0, 800], [400, -300], [2000, 1000], [8000, 6000]]) {
    const zoom = zoomFor(23.05, n, e);
    const mpp = 156543.03392 * Math.cos(23.05 * Math.PI / 180) / Math.pow(2, zoom);
    chk(height / 2 * mpp >= Math.abs(n) * margin - 1e-6
      && width / 2 * mpp >= Math.abs(e) * margin - 1e-6,
      `偏移 (${n}, ${e})m 时用 ${zoom} 级：飞机还在画面里`,
      `半高 ${(height / 2 * mpp).toFixed(0)}m / 半宽 ${(width / 2 * mpp).toFixed(0)}m`);
  }
}

console.log(ok ? '\n结果: 全部通过' : '\n结果: 有失败');
process.exit(ok ? 0 : 1);
