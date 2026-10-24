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
// 页面里的 t() 是 i18n 查表（英文原串当键，查不到原样返回）。这里用恒等桩：
// 单测只验"文案是哪个键"，不验译文（译文由 test_i18n.py / 语言切换实测管）。
const t=k=>k;
${extractFn('formatTime')}
${extractFn('nextMarkerName')}
${extractFn('markerListLayout')}
${extractFn('applyMarkerLayout')}
${extractFn('sortedMarkers')}
${extractFn('selectedMarkers')}
${extractFn('updateMarkerBar')}
${extractFn('applyReportCapabilities')}
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
  applyReportCapabilities,
  getMarkers: () => projectMarkers,
  getChecked: () => markerChecked,
  getActive: () => activeMarkerId
};`;

let reportMissingDeps = [];
const calls = { setView: [], opened: [], autoPlay: [], saved: 0, drew: 0, alerts: [], confirmAnswer: true };
const markerList = el.markerList;

const build = new Function(
  'projectMarkers', 'markerChecked', 'activeMarkerId',
  'markerList', 'markerCount', 'markerSelectAll',
  'markerDeleteBtn', 'markerKmlBtn', 'markerCopyBtn',
  'markerReportBtn', 'reportAvailable', 'reportMissingDeps',
  'videoStatus', 'drawProjectMarkers', 'saveProjectMarkers',
  'map', 'geoFiles', 'videoPathFromGeojson', 'openVideoFromPopup',
  'shortFileName', 'formatTime', 'projectSelect', 'TRACK_FOCUS_ZOOM',
  'alert', 'confirm', 'document',
  'trackMatchesPath',
  code
);

function fresh(markers, reportAvailable = true) {
  reportMissingDeps = [];
  const state = {
    projectMarkers: markers,
    markerChecked: new Set(),
    activeMarkerId: '',
  };
  const api = build(
    state.projectMarkers, state.markerChecked, state.activeMarkerId,
    markerList, el.markerCount, el.markerSelectAll,
    el.markerDeleteBtn, el.markerKmlBtn, el.markerCopyBtn,
    el.markerReportBtn, reportAvailable, reportMissingDeps,
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
    { createElement: makeEl, body: { appendChild() {}, removeChild() {} } },
    // 与页面同源：去掉扩展名/.3d/_V|_S|_T 后比较（trackMatchesPath 的最小实现）。
    // jumpToMarker 反查「标记点存的那路视频属于哪份航迹」时用它 ——
    // 合并航迹的文件名没有 _V/_S/_T，不能拿航迹名推视频名去比。
    // 注意：它必须是**最后一个**实参（生成函数的最后一个是 code），
    // 否则整串实参会错位（踩过：openVideoFromPopup 收到了相对路径字符串）。
    (trackPath, want) => {
      const stem = (s) => String(s || '').replace(/\.(mp4|mov|srt|geojson|osv)$/i, '')
        .replace(/\.3d$/i, '').replace(/_[VST]$/i, '').toLowerCase();
      return stem(trackPath) === stem(want);
    }
  );
  // 让函数里对 projectMarkers 的重新赋值能被外面看到（删完要检查）
  return { api, state, markers: () => api.getMarkers(), checked: () => api.getChecked() };
}

const A = { id: 'a', name: '1 号排水口', lat: 23.03441, lng: 112.466997, video: 'DJI_x_0001_V.mp4', time: 608.274, created: '2026-10-05T01:00:00.000Z' };
// 第二个架次（序号不同）。**不能**还用 _0001 的另一路：合并航迹的文件名去掉了
// _V/_S/_T，`DJI_x_0001.geojson` 是「_0001 这次拍摄」的唯一一份，两路都在它里面 ——
// 所以拿同一架次的两路视频去断言「文件夹序号跟着换」是测不出来的（两路必然同属一份航迹）。
const B = { id: 'b', name: '2 号 <桥下> & "涵洞"', lat: 23.040001, lng: 112.470002, video: 'DJI_x_0002_T.mp4', time: 30.5, created: '2026-10-05T02:00:00.000Z' };
const C = { id: 'c', name: '3 号取水口', lat: 23.05, lng: 112.48, video: 'DJI_x_0001_V.mp4', time: 12, created: '2026-10-05T00:30:00.000Z' };

// 两个架次各一份合并航迹（名字不带流后缀），视频名才带 _V/_T
const geoFiles = [
  { relative_path: 'DJI_x_0001.geojson', folder_index: 0 },
  { relative_path: 'DJI_x_0002.geojson', folder_index: 1 },
];

console.log('=== 1) 按创建时间排序：新的在上面 ===');
{
  const r = fresh([A, B, C]);
  const order = r.api.sortedMarkers().map(m => m.id);
  chk(order.join(',') === 'b,a,c', '乱序进、按 created 降序出（新 -> 旧）', order.join(','));
  chk(r.api.sortedMarkers() !== r.markers(), '排序返回副本，不改动原数组');
}

console.log('\n=== 2) 选中语义（以「已加载」的显隐为准）===');
{
  // 2026-10-24：标记点页已删除，勾选状态只剩「已加载 → 位置点」那一处。
  // 沙箱里没有 loadedUiState → 视为「全部可见」→ 选中的就是全部。
  const r = fresh([A, B, C]);
  chk(r.api.selectedMarkers().length === 3, '全部可见时，选中的是全部 3 个',
    String(r.api.selectedMarkers().length));
  r.checked().add('a');   // 旧集合不再影响选中结果
  chk(r.api.selectedMarkers().length === 3, '旧 markerChecked 不再决定导出范围');
}

console.log('\n=== 3) 列表渲染 ===');
{
  const r = fresh([A, B, C]);
  el.markerList.children = [];
  r.api.renderMarkerList();

  const rows = el.markerList.children;
  chk(rows.length === 3, '三条标记点渲染三行', String(rows.length));
  chk(rows[0].className.indexOf('marker-row') === 0, '每行是 .marker-row');
  // 2026-10-16：行里多了「✎ 编辑」按钮（改名 / 移到别的类别），
  // 所以从 5 格变 6 格：[✓] 名称 纬度 经度 [✎] [×]
  chk(rows[0].children.length === 6,
    '每行 6 个元素：[✓] 名称 纬度 经度 [✎] [×]', String(rows[0].children.length));
  chk(rows[0].children[0].type === 'checkbox', '第 1 格是复选框');
  chk(rows[0].children[4].textContent === '✎', '倒数第 2 格是编辑（改名 / 移组）');
  chk(rows[0].children[4].className === 'marker-edit', '编辑按钮用 .marker-edit 样式');
  chk(rows[0].children[5].textContent === '×', '最后一格是单个删除的 ×');
  chk(rows[0].children[1].textContent === B.name, '第 2 格是名称（最新的排最前）', rows[0].children[1].textContent);
  chk(rows[0].children[2].textContent === '23.040001' && rows[0].children[3].textContent === '112.470002',
    '纬度 / 经度各占一格，6 位小数', rows[0].children[2].textContent + ',' + rows[0].children[3].textContent);
  chk(el.markerDeleteBtn.disabled === false, '有标记点时批量按钮可用');

  // 2026-10-24：标记点卡片里的按钮组已删除（导出/复制/报告移到
  // 「已加载 → 位置点」行尾的小图标），这里只验证「依赖是否齐全」仍被正确记录。
  // 2026-10-24：标记点卡片的按钮组已删除（导出/复制/报告移到「已加载 → 位置点」行尾）。
  // 这里只验证「缺依赖时会把缺的项记下来」，供图标按钮的悬停提示用。
  chk(/reportMissingDeps=missing/.test(html),
    '缺依赖时把缺的东西记下来（图标按钮的提示用）');
  chk(/function applyReportCapabilities\(/.test(html) && /reportAvailable=missing\.length===0/.test(html),
    '依赖齐全时不记缺失项');

  const empty = fresh([]);
  el.markerList.children = [];
  empty.api.renderMarkerList();
  chk(el.markerList.children.length === 1 && /No markers yet/.test(el.markerList.children[0].textContent),
    '没有标记点时给出说明文字，而不是空白列表');
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
  chk(lines[0] === 'Name\tLat\tLng', '第一行是表头（制表符分隔，粘 Excel 正好三列）', lines[0]);
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
  chk(/^markers_东莞2_\d{4}-\d{2}-\d{2}\.kml$/.test(fname), '文件名是 markers_<项目名>_<日期>.kml', fname);
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
    '换一个架次（_0002 的热成像）时文件夹序号也跟着换',
    `folder_index=${calls.opened[0].folder_index} path=${calls.opened[0].relative_path}`);

  // 没有视频信息的点：只跳地图，不报错
  calls.opened.length = 0;
  const r2 = fresh([{ id: 'z', name: '地图点', lat: 23, lng: 112, video: '', time: 0, created: '' }]);
  r2.api.jumpToMarker('z');
  chk(calls.opened.length === 0, '没有视频信息的点不会去打开视频');
}

console.log('\n=== 8) 全部隐藏时才提示「请先勾选」===');
{
  // 新语义：选中 = 可见。沙箱里没有 loadedUiState，所以先确认「可见时能导出」。
  const r = fresh([A, B, C]);
  calls.alerts.length = 0;
  chk(r.api.pickedForExport() !== null, '有可见标记点时可以直接导出');
  chk(calls.alerts.length === 0, '不弹提示');
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
  const countdownCalls = [];
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
    // 点照片跳视频那套「倒退 3 秒 + 倒计时」：startClip 里会调它，
    // 标记点这条路（autoPlay=false）用不到，给个空桩即可
    'setPhotoCountdownTarget', 't',
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
      setTimeout, clearTimeout,
      // 标记点这条路不带 photo_pause_at，桩里只记录调用
      (photoAtAbs, bucket) => { countdownCalls.push([photoAtAbs, bucket]) },
      // startClip 里现在会调 t()（状态文案），沙箱里给个直通桩
      (k) => k
    );

    api.startClip();
    if (metaHandler) metaHandler();     // 模拟元数据到达
  }

  runStart(false);
  chk(played.filter(x => x === 'play').length === 0, '标记点入口：play() 一次都没被调用',
    played.join(',') || '（空）');
  chk(countdownCalls.length === 1 && countdownCalls[0][0] === 0,
    '标记点入口不带 photo_pause_at -> 不倒计时（照片那条路才倒计时）',
    JSON.stringify(countdownCalls));
  chk(currentTime === 90, '但确实定位到了该标记点的时间', String(currentTime));
  chk(/not playing/.test(videoStatus.textContent), '状态栏写明未自动播放', videoStatus.textContent);
  chk(/Positioned at/.test(videoInfo.textContent), '信息栏也写成「Positioned at」，不写「Playing」',
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
  // 类别输入框（用户 2026-10-16：建标记点有"名字 + 类别"两项）
  const catInput = { value: '' };
  // 记住"上次用过的类别"
  const catStored = [];

  const buildConfirm = new Function(
    'projectMarkers', 'pendingMark', 'videoMarkName', 'addVideoMark',
    'saveProjectMarkers', 'renderMarkerList', 'closeVideoMarkDialog',
    'showVideoMarkError', 'projectSelect', 'clip', 'videoPlayer',
    'pendingMarkSpot', 'videoMarkCategory', 'storeMarkerCategory',
    `${extractFn('nextMarkerName')}
${extractFn('normalizeMarkerName')}
${extractFn('markerNameTaken')}
${extractFn('confirmVideoMark')}
return {confirmVideoMark, normalizeMarkerName, markerNameTaken, getPending: () => pendingMark};`
  );

  const make = (name) => ({ id: name, name, lat: 23, lng: 112, video: 'a.mp4', time: 1, created: '' });

  function run(existing, typed, spot, category) {
    errors.length = 0;
    added.length = 0;
    closed = 0;
    saved = 0;
    input.value = typed;
    catInput.value = category === undefined ? '' : category;
    catStored.length = 0;

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
      { currentTime: 42 },
      spot === undefined ? null : spot,
      catInput,
      (c) => catStored.push(c)
    );

    api.confirmVideoMark();

    return { markers, api };
  }

  const base = [make('东莞2-1'), make('3 号排水口')];

  let result = run(base, '东莞2-1');
  chk(added.length === 0 && result.markers.length === 2, '重名：不新增、不落库',
    `新增 ${added.length} 个，共 ${result.markers.length} 个`);
  chk(errors.length === 1 && /already exists/.test(errors[0]),
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

  result = run(base, '带落点', { fx: 0.25, fy: 0.75 });
  {
    const mark = result.markers[result.markers.length - 1];
    chk(mark.fx === 0.25 && mark.fy === 0.75,
      '右键取点时的画面位置随标记点一起入库（fx / fy）',
      `fx=${mark.fx} fy=${mark.fy}`);
  }

  result = run(base, '无落点', null);
  {
    const mark = result.markers[result.markers.length - 1];
    chk(!('fx' in mark) && !('fy' in mark),
      '没有落点就不写 fx/fy（老标记点不会长出编造的位置）',
      JSON.stringify(mark));
  }

  const api = run(base, 'x').api;
  chk(api.normalizeMarkerName('  A   B  ') === 'a b', '归一化：去空白 + 压空白 + 转小写',
    api.normalizeMarkerName('  A   B  '));
  chk(api.markerNameTaken('东莞2-1') === true, '查重：命中', 'true');
  chk(api.markerNameTaken('东莞2-1', '东莞2-1') === false,
    '查重：排除自己时不算（给以后改名留着）');
  chk(api.markerNameTaken('') === false, '空名字不算重名');

  // ---- 类别字段（用户 2026-10-16：建标记点是"名字 + 类别"两项）----
  // 语义：类别是自由文本，作用相当于文件夹 —— 输入新词就是新建类别，
  //       输入已有的词就是复用；空着则不分类。
  result = run(base, '有类别', undefined, '裂缝');
  {
    const mark = result.markers[result.markers.length - 1];
    chk(mark && mark.category === '裂缝', '类别写进标记点', JSON.stringify(mark && mark.category));
    chk(catStored.length === 1 && catStored[0] === '裂缝',
      '记住了"上次用过的类别"（下次预填用）', JSON.stringify(catStored));
  }

  result = run(base, '无类别', undefined, '   ');
  {
    const mark = result.markers[result.markers.length - 1];
    chk(mark && !('category' in mark), '类别留空就不写这个字段（不是空字符串）',
      JSON.stringify(mark));
    chk(catStored.length === 0, '类别留空不覆盖"上次用过的类别"', JSON.stringify(catStored));
  }

  result = run(base, '类别去空格', undefined, '  裂缝  ');
  {
    const mark = result.markers[result.markers.length - 1];
    chk(mark && mark.category === '裂缝', '类别首尾空格被去掉', JSON.stringify(mark && mark.category));
  }
}

console.log('\n=== 13) 报告地图取景：目标点居中 + 18 级，飞机快出画才降级 ===');
{
  const width = Number((html.match(/REPORT_MAP_WIDTH=(\d+)/) || [])[1]);
  const height = Number((html.match(/REPORT_MAP_HEIGHT=(\d+)/) || [])[1]);
  const maxZoom = Number((html.match(/REPORT_MAP_MAX_ZOOM=(\d+)/) || [])[1]);
  const margin = Number((html.match(/REPORT_MAP_MARGIN=([\d.]+)/) || [])[1]);

  chk(maxZoom === 17, '默认取景 17 级（18 级视野太窄，参照物不够）', String(maxZoom));
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

  chk(zoomFor(23.05, 0, 0) === 17, '飞机就在目标点：17 级', String(zoomFor(23.05, 0, 0)));
  chk(zoomFor(23.05, 100, 0) === 17, '飞机正北 100m：仍是 17 级（半高约 352m）',
    String(zoomFor(23.05, 100, 0)));
  chk(zoomFor(23.05, 0, 300) === 17, '飞机正东 300m：仍是 17 级（半宽约 880m）',
    String(zoomFor(23.05, 0, 300)));
  chk(zoomFor(23.05, 0, 800) === 16, '飞机正东 800m 超出半宽（880m）：降一级',
    String(zoomFor(23.05, 0, 800)));
  chk(zoomFor(23.05, -400, 0) === 16, '飞机正南 400m 超出半高（352m）：按需降到 16 级',
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

console.log('\n=== 14) 画面落点换算：右键位置 -> 归一化 0..1 ===');
{
  const makeSpot = new Function(
    'videoPlayer',
    `${extractFn('videoImagePoint')}
${extractFn('videoImageSpot')}
return videoImageSpot;`
  );

  // 画面区 800×400，左上角在 (100, 50)
  const spot = makeSpot({
    getBoundingClientRect: () => ({ left: 100, top: 50, width: 800, height: 400 })
  });

  const at = (clientX, clientY) => spot({ clientX, clientY });
  const show = value => JSON.stringify(value);

  chk(show(at(100, 50)) === show({ fx: 0, fy: 0 }), '左上角 -> (0, 0)', show(at(100, 50)));
  chk(show(at(900, 450)) === show({ fx: 1, fy: 1 }), '右下角 -> (1, 1)', show(at(900, 450)));
  chk(show(at(500, 250)) === show({ fx: 0.5, fy: 0.5 }), '正中 -> (0.5, 0.5)', show(at(500, 250)));
  chk(show(at(300, 150)) === show({ fx: 0.25, fy: 0.25 }), '四分之一处 -> 0.25',
    show(at(300, 150)));
  chk(show(at(300, 350)) === show({ fx: 0.25, fy: 0.75 }), '左下 -> (0.25, 0.75)',
    show(at(300, 350)));

  chk(at(50, 250) === null && at(500, 10) === null && at(950, 250) === null,
    '点在画面外 -> null（不记落点）');
}

console.log(ok ? '\n结果: 全部通过' : '\n结果: 有失败');
process.exit(ok ? 0 : 1);
