const fs = require('fs');
const path = require('path');
// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');
const html = fs.readFileSync(HTML, 'utf8');

let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

const m = html.match(/<script>\s*([\s\S]*?)<\/script>/);
chk(!!m, '找到 <script> 块');
const body = m[1];
console.log(`  script 正文 ${body.split('\n').length} 行 / ${body.length} 字符`);

console.log('\n=== 整页 JS 语法（只编译不执行）===');
try { new Function(body); chk(true, '编译通过'); }
catch (e) { chk(false, '语法错误', e.message); }

console.log('\n=== 括号配平 ===');
for (const [o, c, label] of [['{', '}', '花括号'], ['(', ')', '圆括号'], ['[', ']', '方括号']]) {
  const d = body.split(o).length - body.split(c).length;
  chk(d === 0, label, `差 ${d}`);
}
chk((body.split('`').length - 1) % 2 === 0, '反引号成对');

console.log('\n=== 函数齐备 ===');
for (const f of ['setProbe', 'clearProbe', 'clearHighlight', 'doPlaceSearch', 'pickPoi',
                 'nearestPerStream', 'pickNearestGroup', 'searchNearby', 'renderNearbyResult',
                 'ensureAllLoaded', 'payloadFor', 'streamLabelOf', 'videoPathFromGeojson',
                 'showProbePanel', 'streamKeyOf', 'is3dTrack', 'isVisibleStream',
                 'openVideoFromPopup', 'proxyBucketOf', 'proxyMode', 'startClip', 'fallbackToProxy',
                 'serverAlive', 'indexAtTime', 'bearingAt', 'bearingBetween', 'trackForClip',
                 'syncDroneMarker', 'hideDroneMarker', 'followViewport', 'trackLatLngs',
                 'applyVideoPanelLayout',
                 'setBaseMap', 'initBaseMap', 'clearBaseLayers', 'lensInfoOf', 'opticalFocalOf',
                 'telemetryIndexAt']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
chk(!/function\s+findNearestTrackPoint\s*\(/.test(body), '旧函数 findNearestTrackPoint() 已移除');

console.log('\n=== 代理播放接线 ===');
chk(/PROXY_SECONDS\s*=\s*90/.test(body), 'PROXY_SECONDS = 90（与后端一致）');
chk(/PROXY_BUCKET_SECONDS\s*=\s*30/.test(body), 'PROXY_BUCKET_SECONDS = 30（与后端一致）');
chk(body.includes('/api/project/proxy?'), '转码片段接口已接线');
chk(body.includes('/api/project/video?'), '原片直出接口保留');
chk(/function\s+proxyMode\s*\(/.test(body), '存在播放模式判定');
chk(/return 'auto'/.test(body), '默认 auto：先试原片，失败自动转码');
chk(/function\s+fallbackToProxy\s*\(/.test(body), '存在自动回退');
chk(/function\s+serverAlive\s*\(/.test(body), '失败时先探测服务端是否活着');
chk(/服务端没有响应/.test(body), '服务端不可达时给出明确指引');
chk(/服务端已连上，因此是文件或编码问题/.test(body), '服务端正常时才归因到编码');
chk(/fallbackToProxy\(`原片无法播放/.test(body), '原片播放失败时自动回退');
chk(/currentTime=seekTo/.test(body), '按 bucket 偏移换算 currentTime');
chk(/q\.set\('start'/.test(body) && /q\.set\('duration'/.test(body), '带上 start/duration 参数');
chk(/videoPlayer\.error/.test(body), '失败时读取媒体错误码');
chk(/MEDIA_ERROR_TEXT/.test(body), '错误码有中文解释');
chk(/networkState/.test(body) && /readyState/.test(body), '同时报出网络/就绪状态');
chk(/word-break:break-all/.test(body), '失败时显示完整地址便于排查');

console.log('\n=== 无人机跟随箭头接线 ===');
chk(/drone-div-icon/.test(body), '箭头图标样式已定义');
chk(/drone-arrow/.test(body), '箭头 SVG 元素已定义');
chk(/fill="#1e88e5"/.test(body) && /stroke="#ffffff"/.test(body), '蓝底白边，与截图一致');
chk(/viewBox="0 0 40 40"/.test(body), '用 SVG 矢量绘制（不是位图）');
chk(/zIndexOffset:1000/.test(body), '箭头压在航迹之上');
chk(/L\.divIcon/.test(body), '用 divIcon 承载 SVG');
chk(/transform-origin:50% 50%/.test(html), '旋转以图标中心为轴');
chk(/querySelector\('\.drone-arrow'\)/.test(body), '只改内层 transform，不重建 DOM');
chk(/proxyBucketOf\(clip\.start\)\+vs/.test(body), '代理播放时补上 bucket 时间偏移');
chk(/addEventListener\('seeked'/.test(body), '拖动进度条也同步');
chk(/addEventListener\('pause'/.test(body), '暂停时同步（停住不动）');
chk(/syncDroneMarker\(seekTo\)/.test(body), '打开视频时先落到起播位置');
chk(/hideDroneMarker\(\)/.test(body), '关闭视频/清空/切项目时收掉箭头');

console.log('\n=== 地图跟随 ===');
chk(/function\s+followViewport\s*\(/.test(body), 'function followViewport()');
chk(/function\s+trackLatLngs\s*\(/.test(body), 'function trackLatLngs()');
for (const k of ['FOLLOW_LOOKAHEAD', 'FOLLOW_HEADROOM', 'FOLLOW_PADDING', 'FOLLOW_MARGIN', 'FOLLOW_MIN_INTERVAL']) {
  chk(new RegExp('const ' + k + '=').test(body), `常量 ${k}`);
}
chk(/id="followMode"/.test(html), '视频窗口里有跟随模式选择框');
chk((html.match(/<option value="(fit|center|off)"/g) || []).length === 3, '提供 fit / center / off 三种模式');
chk(/followModeSelect\.addEventListener\('change'/.test(body), '切换模式立刻生效');
chk(/initFollowMode/.test(body) && /get\('follow'\)/.test(body), '支持 ?follow= 网址参数');
chk(/map\.panTo\(drone/.test(body), 'center 模式用 panTo 平移');
chk(/maxZoom:TRACK_FIT_MAX_ZOOM/.test(body),
  'fitBounds 限制最大缩放，避免贴太近（用常量，原来是写死的 17）');
chk(/coreBounds\.getSouthWest\(\)/.test(body), '触发条件只看核心点（不含前方航迹）');
chk(/pad\(FOLLOW_HEADROOM\)/.test(body), '调整时预留余量，减少调整次数');
chk(/Date\.now\(\)-\(clip\.lastFollowAt\|\|0\)<FOLLOW_MIN_INTERVAL/.test(body), '有最小调整间隔节流');
chk(/followViewport\(\);\s*\n\s*syncMapPip\(\);\n}/.test(body),
  'syncDroneMarker 结束时先跟随视野、再刷地图小窗');

console.log('\n=== 视频面板固定在右栏，不悬浮、不可拖动 ===');
{
  chk(/id="videoDialog"/.test(html) && /id="videoDialogHead"/.test(html), '对话窗口与标题栏都在');
  chk(!/id="videoResize"/.test(html), '右下角的缩放手柄已删除');
  chk(!/id="dockBtn"/.test(html), '「归位」按钮已删除（没有可归位的东西了）');
  chk(!/video-resize/.test(html) && !/cursor:nwse-resize/.test(html), '缩放手柄的样式也删了');
  // 「cursor:move」只允许出现在说明注释里，不能是生效的样式
  chk(!/cursor:move/.test(html.replace(/\/\*[\s\S]*?\*\//g, '')), '标题栏不再显示可拖动光标');
  chk(!/pointerdown/.test(body), '所有拖动/缩放的指针处理已删除');
  chk(!/setPointerCapture/.test(body), '指针捕获也一并删除');

  // 面板必须在右栏里（不再是覆盖全屏的悬浮层）
  const col = html.indexOf('id="colRight"');
  const panel = html.indexOf('id="videoModal"');
  chk(col > 0 && panel > col, '视频面板写在右栏内部');
  const slotEnd = html.indexOf('</div>', html.indexOf('id="videoSlot"'));
  chk(panel > slotEnd, '面板紧跟在占位说明之后');

  chk(/\.video-panel\{display:none;flex:1;min-height:0;flex-direction:column/.test(html),
    '面板作为栏内 flex 子项撑满右栏');
  chk(/\.video-panel \.video-dialog\{width:100%;max-width:100%/.test(html),
    '对话框宽度 100% 跟着栏走（不再有写死的像素宽）');
  chk(!/position:fixed;inset:0;background:transparent/.test(html), '不再是覆盖全屏的固定浮层');
  chk(/function applyVideoPanelLayout\(/.test(body), 'function applyVideoPanelLayout()（只管控件换行）');
  chk(!/function applyDialogPlacement/.test(body), '旧的偏移定位函数已删除');
  chk(!/function dialogBaseRect/.test(body), '旧的基准测量函数已删除');
  // 用「赋值语句」判断，而不是裸词 —— 说明注释里会提到这些名字
  chk(!/dialogOffset\s*[.=]/.test(body), '没有任何偏移量残留（赋值/取值都查）');
  chk(!/videoMaxH\s*=/.test(body), '没有播放器高度上限的残留赋值');
  chk(!/dockVideoToColumn|resetVideoPlacement/.test(body.replace(/\/\/[^\n]*/g, '')),
    '停靠/归位相关的函数与调用都已删除');

  // 打开/关闭时占位说明的显隐
  chk(/hide\(videoSlot\);/.test(body), '打开视频时收起右栏的占位说明');
  chk(/videoSlot\.style\.display=''/.test(body), '关闭视频后把占位说明放回来');
  chk(/if\(clip\)\{\s*\n\s*show\(mapNotice,'视频窗口打开时/.test(body), '播放中点地图不会打乱选点');
}

console.log('\n=== 视频实时信息栏 ===');
chk(/id="videoTelemetry"/.test(html), '信息栏元素存在');
chk(/video-telemetry/.test(html) && /\.video-telemetry b\{/.test(html), '信息栏样式已定义');
for (const f of ['compassText', 'groundCenterDistance', 'isInfraredPath', 'loadTelemetry', 'renderTelemetry']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
for (const k of ['BASE_FOCAL', 'M4T_LENS_BANDS', 'GROUND_MIN_PITCH']) {
  chk(new RegExp('const ' + k + '=').test(body), `常量 ${k}`);
}
chk(/M4T 是四摄/.test(body), '注释里写明 M4T 是四摄');
chk(/function\s+lensInfoOf\s*\(/.test(body), 'function lensInfoOf()');
chk(/function\s+opticalFocalOf\s*\(/.test(body), 'function opticalFocalOf()');
chk(/广角开数码变焦会被误判|必须用「光学焦距」/.test(body), '注释说明了为何要用光学焦距');
chk(!/WIDE_FOCAL_MAX/.test(body) && !/lensNameOf/.test(body), '旧的两档逻辑已完全移除');
chk(/name:'广角',\s*base:1/.test(body) && /name:'中长焦',\s*base:3/.test(body)
  && /name:'长焦',\s*base:7/.test(body), 'DJI 标称倍率 1× / 3× / 7× 已写入');
chk(/DJI App 的写法/.test(body), '镜头显示采用 DJI App 写法');
chk(/Number\.isInteger\(total\)\?total:total\.toFixed\(1\)/.test(body),
  '整数倍率不带小数（“7×”而非“7.0×”）');
chk(/数码变焦 \$\{lens\.digital\.toFixed\(2\)\}×/.test(body), '悬停里说明数码变焦倍数');
chk(/精确比值 \$\{\(70\/BASE_FOCAL\)\.toFixed\(2\)\}×/.test(body),
  '悬停里说明中长焦精确比值 2.92×（DJI 标称 3×）');
chk(/可见光 3840×2160/.test(body) && /可见光 1920×1080/.test(body)
  && /热成像 1280×1024/.test(body),
  '三种视频类型标签用数字分辨率（可见光/热成像字样保留）');
// 只看函数真正 return 出去的标签；注释里提到旧叫法不算问题
chk(!/return '(可见光 4K|可见光 1080P|热成像 1024P)'/.test(body),
  '函数返回的标签不再用 4K / 1080P / 1024P 这种叫法');
chk(/热成像传感器 640×512，机内超分 2×/.test(body), '悬停里说明 640×512 传感器超分 2×');

console.log('\n=== 文件列表：类型标签与排序 ===');
{
  const start = body.indexOf('function renderFiles(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/const typeBadge=/.test(fn) && /badge-type/.test(fn), '列表项带视频类型徽标');
  chk(/esc\(streamNoteOf\(f\.relative_path\)\)/.test(fn), '徽标悬停显示画幅/相机说明');
  chk(/\.sort\(\(a,b\)=>a\.rank-b\.rank\|\|a\.index-b\.index\)/.test(fn),
    '按类型归拢排序，同类型内保持原顺序（稳定排序）');
  chk(/const f=geoFiles\[index\]/.test(fn) && /dataset\.index=index/.test(fn)
    && /loadOne\(index\)/.test(fn),
    '排序只改显示顺序：索引仍指向 geoFiles，否则「加载」会加载错文件');
  chk(!/geoFiles\.forEach\(\(f,i\)/.test(fn), '旧的未排序 forEach 已移除');
}
{
  // 排序权重必须直接看后缀，不能靠标签文字查表（改文案就会失配）
  const start = body.indexOf('function streamRankOf(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/if\(\/_v\\\.\/\.test\(v\)\)return 0/.test(fn)
    && /if\(\/_s\\\.\/\.test\(v\)\)return 1/.test(fn)
    && /if\(\/_t\\\.\/\.test\(v\)\)return 2/.test(fn),
    '排序权重直接看文件名后缀（_V -> _S -> _T）');
  chk(!/STREAM_ORDER/.test(body), '去掉了按标签文字查表的老写法');
}
chk(/\.badge-type\{background:#0f766e/.test(html), '类型徽标有独立配色，便于一眼分辨');

console.log('\n=== 去掉冗余 point_heights 后的高度读取 ===');
chk(/function heightsOfTrack\(/.test(body), 'function heightsOfTrack()');
{
  const start = body.indexOf('function heightsOfTrack(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/props\.point_heights/.test(fn), '有 point_heights 时优先用它（兼容旧文件）');
  chk(/c\.length>2\?c\[2\]:null/.test(fn), '没有时退回读坐标第三维（新文件就是这样）');
  chk(/heights:heightsOfTrack\(props,coords\)/.test(body), '航迹登记改用 heightsOfTrack');
  chk(!/heights:props\.point_heights\|\|\[\]/.test(body), '旧的直接读法已移除');
  chk(/const coords=geometry\.coordinates\|\|\[\];/.test(body), '坐标先取出来复用，避免取两遍');
}
chk(/const COMPASS_NAMES=\['北','东','南','西'\]/.test(body), '方位名称表已定义');
chk(/api\/project\/telemetry/.test(body), '请求遥测接口');
chk(/telemetryCache\[path\]/.test(body), '遥测结果按视频缓存');
chk(/alt\/Math\.tan\(down\*Math\.PI\/180\)/.test(body), '地面距离用 h/tan(俯角)，不是空中直线');
chk(/clip\.trackSeconds!=null/.test(body), '转码播放时用带 bucket 偏移的时间轴');
chk(/clip=null;\s*\n\s*telemetry=null;\s*\n\s*renderTelemetry\(\)/.test(body), '关闭视频时清空信息栏');
chk(body.includes('/_t\\.(mp4|mov)$/i.test('), '按文件名后缀判定红外');

console.log('\n=== 画面中心准星 ===');
chk(/id="crosshairToggle"/.test(html), '准星开关按钮存在');
chk(/class="row video-head-tools"/.test(html), '视频标题栏右侧控件有专门的类');
chk(/\.video-dialog-head\{[^}]*flex-wrap:nowrap/.test(html), '标题栏本身也不换行');
chk(/\.video-dialog-head>div:first-child\{min-width:0/.test(html), '标题区可被压缩');
chk(/\.video-title\{[^}]*text-overflow:ellipsis/.test(html), '标题过长用省略号收尾');
{
  // 关闭按钮：全局 button 的 padding(13px 22px) 会渗透进来，必须清掉
  const closeRule = (html.match(/\.video-close\{([^}]*)\}/) || [])[1] || '';
  const basePad = (html.match(/(?:^|\n)button\{([^}]*)\}/) || [])[1] || '';
  chk(/padding:0/.test(closeRule),
    '关闭按钮显式清掉了内边距（否则 36px 方框装不下 44px 内边距，× 会歪）',
    '全局 padding=' + ((basePad.match(/padding:([^;]*)/) || [])[1] || '?'));
  chk(/display:flex/.test(closeRule) && /justify-content:center/.test(closeRule)
    && /align-items:center/.test(closeRule), '关闭按钮用 flex 把 × 居中');
  chk(/\.video-close svg\{display:block\}/.test(html), '× 用 SVG 绘制，不受字体度量影响（必定居中）');
  chk(/M5 5 L19 19 M19 5 L5 19/.test(html), '× 路径关于中心对称');
}
chk((html.match(/<option value="(fit|center|off)"/g) || []).length === 3,
  '跟随模式仍是 fit / center / off 三种');
chk(/id="videoCrosshair"/.test(html), '视频画面准星元素存在');
chk(/class="video-stage"/.test(html), '视频外面套了定位容器（准星才能居中）');
for (const f of ['centerGroundLatLng', 'syncCrosshair', 'hideMapCrosshair',
                 'applyCrosshairVisibility', 'currentTelemetryTime']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
chk(/function ensureMapIcons\(\)/.test(body), '地图图标统一在 ensureMapIcons() 里创建');

console.log('\n=== Leaflet 缺失时的降级（断网/内网）===');
chk(/function leafletReady\(\)/.test(body), '用函数判断 Leaflet 是否就绪（不能开头算一次常量）');
chk(!/LEAFLET_OK/.test(body),
  '没有残留的 LEAFLET_OK 常量（本地缺失时 CDN 是异步到的，常量会一直是 false）');
chk(/async|function/.test(body) && /function ensureMapIcons\(\)/.test(body),
  'function ensureMapIcons()（图标懒创建，等 Leaflet 到位再建）');
{
  const start = body.indexOf('function ensureMapIcons(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  for (const n of ['droneIcon', 'crosshairIcon', 'probeIcon']) {
    chk(new RegExp('if\\(!' + n + '\\)\\{').test(fn), `图标 ${n} 按需创建（不是顶层常量）`);
  }
  chk(/if\(!leafletReady\(\)\)return false;/.test(fn), 'Leaflet 没到位时不建图标');
}
chk(/let droneIcon=null;/.test(body) && /let crosshairIcon=null;/.test(body)
  && /let probeIcon=null;/.test(body), '三个图标变量声明为 null');
{
  const start = body.indexOf('function boot(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/loadProjects\(\);/.test(fn), '即使没有 Leaflet 也照常加载项目列表');
  chk(/if\(!leafletReady\(\)\)\{/.test(fn), '没有 Leaflet 时走降级分支');
  chk(/show\(\s*\n?\s*mapNotice,/.test(fn) && /未加载/.test(fn), '降级分支在地图区给出明确原因');
  chk(/ensureMapIcons\(\)/.test(fn), 'boot 里先建图标再建地图（否则建 marker 时 icon 为 null）');
  chk(fn.indexOf('ensureMapIcons()') < fn.indexOf('initMap()'),
    '建图标在建地图之前');
  chk(/initMap\(\);\s*\n\s*initBaseMap\(\);/.test(fn), '有 Leaflet 时才初始化地图');
}
chk(/LEAFLET_WAIT_MAX/.test(body) && /setTimeout\(waitLeaflet,100\)/.test(body),
  '轮询等 Leaflet 就绪（本地缺失时会动态插入 CDN 脚本，可能稍晚到）');
chk(/(^|\n)href="\/vendor\/leaflet\.css"/.test(html) || /href="\/vendor\/leaflet\.css"/.test(html),
  'CSS 优先用本地 vendor 副本');
chk(/src="\/vendor\/leaflet\.js"/.test(html), 'JS 优先用本地 vendor 副本');
chk(/this\.onerror=null;this\.href='https:\/\/unpkg\.com\/leaflet/.test(html),
  '本地 CSS 缺失时退回 CDN（并清掉 onerror 防止死循环）');
chk(/this\.onerror=null;var s=document\.createElement\('script'\)/.test(html),
  '本地 JS 缺失时动态插入 CDN');
chk((html.match(/unpkg\.com\/leaflet@1\.9\.4/g) || []).length === 2,
  'CDN 只作兜底、且不再重复引入',
  String((html.match(/unpkg\.com\/leaflet@1\.9\.4/g) || []).length) + ' 处');
{
  const reticle = 'M20 14 v-10 M20 26 v10 M14 20 h-10 M26 20 h10';
  const esc = reticle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  chk((html.match(new RegExp(esc, 'g')) || []).length === 2,
    '地图与视频用同一套准星造型（四段短线+中间留空，各一处）');
  chk(!/stroke="rgba\(0,0,0,\.55\)"/.test(html),
    '准星不带深色描边（按反馈改成纯青色短线，更简洁）');
  chk((html.match(/stroke="currentColor" stroke-width="2.6"/g) || []).length === 2,
    '准星只有一层青色描线（无黑边），地图与视频各一处');
  chk(!/stroke="#ffffff" stroke-width="2.6"/.test(html), '旧的白色圆环准星已移除');
  chk(!/cx="20" cy="20" r="9"/.test(html), '旧的“外圈+中心点”准星已移除');
}
chk(/--reticle:#5eead4/.test(html), '准星颜色由 --reticle 一处控制');
chk(/stroke="currentColor"/.test(html), '准星用 currentColor 取色（改一处即变色）');
chk(/\.crosshair-svg\{width:30px/.test(html) && /\.video-crosshair\{[^}]*width:42px/.test(html),
  '地图 30px / 视频 42px（CS 风格偏小巧）');
console.log('\n=== 变焦变色特效 ===');
chk(/--reticle-zoom:#f87171/.test(html), '变焦色为浅红 #f87171（不刺眼）');
chk(/\.video-crosshair\.zoomed svg\{color:var\(--reticle-zoom\)\}/.test(html),
  '视频准星：变焦时变红');
chk(/\.crosshair-div-icon\.zoomed \.crosshair-svg\{color:var\(--reticle-zoom\)\}/.test(html),
  '地图准星：变焦时变红');
chk(/transition:color \.18s ease/.test(html), '变色有过渡（不突兀）');
chk(/const zoomed=\(lens\.total!=null&&lens\.total>1\)/.test(body),
  '规则：总倍率 > 1× 即变红（中长焦3×/长焦7×/广角叠数码变焦都算）');
chk(/lensInfoOf\(clip\.path,telemetry\.focal\[i\],telemetry\.dzoom\[i\]\)/.test(body),
  '复用同一套镜头判定，不会和「镜头」栏显示不一致');
chk(/videoCrosshair\.classList\.toggle\('zoomed',zoomed\)/.test(body), '视频准星接上变焦状态');
chk(/el\.classList\.toggle\('zoomed',zoomed\)/.test(body), '地图准星接上变焦状态');
{
  // 结构断言：syncCrosshair 里必须先算 zoomed，再做「无有效落点」的提前返回，
  // 否则镜头接近水平（地图准星隐藏）时视频准星就不会变色了
  const start = body.indexOf('function syncCrosshair(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  const iZoom = fn.indexOf('const zoomed=');
  const iEarly = fn.indexOf('if(!drone)');
  chk(iZoom >= 0 && iEarly >= 0 && iZoom < iEarly,
    '变焦状态在「无有效落点」提前返回之前就算好（近水平时视频准星也能变色）',
    `zoomed@${iZoom} earlyReturn@${iEarly}`);
}
chk(/\.video-crosshair\{position:absolute;left:50%;top:50%/.test(html), '视频准星固定在画面正中');
chk(/\.video-crosshair\{[^}]*pointer-events:none/.test(html), '视频准星不挡点击（不影响播放/暂停）');
chk(/crosshairOn=!crosshairOn/.test(body), '按钮点击切换显示/关闭');
chk(/function setToggleState\(/.test(body), 'function setToggleState()');
chk(/setToggleState\(crosshairToggle,crosshairOn\)/.test(body)
  && /setToggleState\(footprintToggle,footprintOn\)/.test(body)
  && /setToggleState\(thermalToggle,thermalOn\)/.test(body)
  && /setToggleState\(mapPipToggle,mapPipOn\)/.test(body),
  '四个开关都走同一个状态函数');
chk(/button\.classList\.toggle\('off',!on\)/.test(body), '状态只靠 .off 类切换');
chk(/setAttribute\('aria-pressed',on\?'true':'false'\)/.test(body), '同时维护 aria-pressed');
chk(!/textContent=(crosshairOn|footprintOn|thermalOn|mapPipOn|compareOn)\?/.test(body),
  '开关按钮里不再写「开/关」字样');
{
  // 按钮字面只保留功能名，且不带「：开 / ：关」
  const labels = [...html.matchAll(/<button id="(crosshair|footprint|thermal|mapPip)Toggle"[^>]*>([^<]*)<\/button>/g)]
    .map((m) => m[2]);
  chk(labels.length === 4, '数到 4 个开关按钮', labels.join(' / '));
  chk(labels.every((t) => t && !/开|关/.test(t)), '按钮字面不含「开/关」', labels.join(' / '));
  chk(labels.includes('小地图') && !labels.includes('小窗'), '地图小窗按钮改叫「小地图」', labels.join(' / '));
  chk(labels.join(',') === '准星,视场,红外,小地图', '四个开关字面如预期', labels.join(' / '));
  chk(!/id="dockBtn"/.test(html),
    '工具栏里没有「归位」（面板固定，不需要归位）');
}
chk(/\.toggle-btn\{[^}]*background:#dbeafe/.test(html), '开：蓝底蓝字加粗');
chk(/\.toggle-btn\.off\{background:#fff;border-color:#e5eaf1;color:#a8b3c2;font-weight:400\}/.test(html),
  '关：白底浅灰字且不加粗（底色就是状态指示）');
chk(/transition:background \.15s ease/.test(html), '切换底色有过渡');
chk(/hideMapCrosshair\(\);/.test(body), 'hideDroneMarker 时一并收掉准星');
chk(/镜头接近水平时没有有效的地面交点/.test(body), '接近水平时不显示假位置');
chk(/zIndexOffset:900/.test(body), '准星压在航迹之上、飞机箭头之下');

console.log('\n=== 飞机箭头朝向 ===');
chk(/function\s+telemetryIndexAt\s*\(/.test(body), 'function telemetryIndexAt()');
{
  const start = body.indexOf('function syncDroneMarker(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  const iYaw = fn.indexOf('telemetry.yaw[telemetryIndex]');
  const iFallback = fn.indexOf('bearingAt(track.coords,index)');
  chk(iYaw >= 0, '箭头朝向取字幕里的云台朝向 gb_yaw', `@${iYaw}`);
  chk(iFallback >= 0, '没有字幕数据时退回航迹航向', `@${iFallback}`);
  chk(iYaw >= 0 && iFallback >= 0 && iYaw < iFallback, '云台朝向优先，航迹航向只是兜底');
  chk(/else\{\s*\n\s*bearing=bearingAt\(track\.coords,index\);\s*\n\s*\}/.test(fn),
    '航迹航向确实放在 else 分支里（不是无条件覆盖）');
  chk(/SRT 里只有云台姿态/.test(fn), '注释写明了 SRT 没有机体朝向这件事');
}
chk(/M20 3 L34 34 L20 26 L6 34 Z/.test(body), '箭头 0° 时朝上（正北），顺时针为正');

console.log('\n=== 镜头视场范围 ===');
chk(/id="footprintToggle"/.test(html), '视场开关按钮存在');
chk(/const FOOTPRINT_MAX_DISTANCE=300/.test(body), '模糊边界距离常量存在');
chk(/let footprintOn=true/.test(body), '默认开启（方便直接看到效果）');
for (const f of ['fovOf', 'groundPointForImage', 'edgePointAtDistance', 'footprintGeometry',
                 'ensureFootprintLayers', 'hideFootprint', 'syncFootprint',
                 'applyFootprintVisibility', 'cssVar', 'offsetLatLng', 'currentTelemetryIndex']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
chk(/上边缘不画/.test(body), '注释写明了「上边缘不画」的原因');
chk(/1° 误差 ≈ 112 m/.test(body), '注释记录了远边不适定的量化依据');
chk(/画面下边缘 \+ 左右两条边缘|只画「画面下边缘 \+ 左右两条边缘」/.test(body),
  '画的确实是下边缘 + 左右边缘');
chk(/dashArray:'7,7'/.test(body), '远边用虚线收口（表示模糊边界）');
chk(/fillOpacity:0\.12/.test(body), '覆盖区域有淡填充（看得清范围）');
chk(/solid\.setLatLngs\(\[\s*\n\s*geometry\.left,geometry\.bl,geometry\.br,geometry\.right/.test(body),
  '实线顺序：左端 -> 左下 -> 右下 -> 右端（正好跳过上边缘）');
chk(/dashed\.setLatLngs\(\[geometry\.right,geometry\.left\]\)/.test(body), '虚线只连左右两端');
{
  const start = body.indexOf('function syncDroneMarker(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/renderTelemetry\(\);\s*\n\s*syncCrosshair\(\);\s*\n\s*syncFootprint\(\);\s*\n\s*followViewport\(\);\s*\n\s*syncMapPip\(\)/.test(fn),
    '每帧依次刷新：信息栏 -> 准星 -> 视场 -> 跟随视野 -> 地图小窗');
  chk(/hideFootprint\(\)/.test(body.slice(body.indexOf('function hideDroneMarker('),
    body.indexOf('\n}', body.indexOf('function hideDroneMarker(')))),
    'hideDroneMarker 时一并收掉视场');
}
chk(!/fovOf\(optical/.test(body), '视场用报告焦距而非光学焦距（数码变焦是裁切画面，视场确实变窄）');
chk(/const fov=fovOf\(focal\);/.test(body), 'fovOf 收到的就是报告焦距');
chk(/cssVar\('--reticle'\)/.test(body), '视场颜色跟准星同一个变量，改一处一起变');
chk(/function currentFootprintGeometry\(/.test(body), 'function currentFootprintGeometry()');
chk(/function applyFootprintToLayers\(/.test(body), 'function applyFootprintToLayers()（主图与小窗共用）');
chk(/footprintGeoKey/.test(body) && /if\(key===footprintGeoKey\)return footprintGeo;/.test(body),
  '同一时刻的几何只算一次（两个地图都调用，避免重复做几十次射线求交）');

console.log('\n=== 地图小窗里的视场 ===');
chk(/function ensureMapPipFootprintLayers\(/.test(body), 'function ensureMapPipFootprintLayers()');
chk(/let mapPipFootprintLayers=null;/.test(body), '小窗视场图层变量存在');
{
  const start = body.indexOf('function ensureMapPipFootprintLayers(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/fillOpacity:0\.22/.test(fn), '小窗填充比主图浓（0.22 vs 0.12）——窗口小，太淡看不见');
  chk(/weight:2,opacity:0\.95/.test(fn) && /weight:1\.6/.test(fn), '小窗线条比主图细');
  chk((fn.match(/bringToBack\(\)/g) || []).length === 3,
    '三层都 bringToBack：视场要压在航迹和箭头下面',
    String((fn.match(/bringToBack\(\)/g) || []).length) + ' 次');
  chk(/addTo\(mapPip\)/.test(fn), '图层加在小地图实例上（不是主地图）');
}
{
  const start = body.indexOf('function syncMapPip(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/footprintOn\?ensureMapPipFootprintLayers\(\):mapPipFootprintLayers/.test(fn),
    '小窗视场跟随「视场」开关');
  chk(/footprintOn\?currentFootprintGeometry\(\):null/.test(fn),
    '开关关掉时传 null，图层被清空');
  chk(fn.indexOf('ensureMapPip()') < fn.indexOf('ensureMapPipFootprintLayers()'),
    '先建小地图实例、再加视场图层（否则 mapPip 还是 null）');
  chk(/if\(footprintOn\)\{\s*\n\s*const geo=currentFootprintGeometry\(\);\s*\n\s*if\(geo\)points\.push\(geo\.left,geo\.bl,geo\.br,geo\.right\);/.test(fn),
    '小窗视野把视场范围也框进来（否则视场会被裁在窗口外）');
  chk(/const bounds=L\.latLngBounds\(points\)\.pad\(0\.25\)/.test(fn), '用点集统一定视野，留 0.25 边距');
  chk(/if\(points\.length<2\)/.test(fn), '只剩飞机一个点时退回跟着它定高');
  chk(/const points=\[drone\];/.test(fn), '点集从飞机开始，准星和视场按需加入');
}
{
  const start = body.indexOf('function applyFootprintVisibility(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/syncMapPip\(\)/.test(fn), '切换视场开关时同步刷新地图小窗');
}
chk(/applyFootprintToLayers\(\s*\n?\s*ensureFootprintLayers\(\)/.test(body),
  '主图也用同一个 applyFootprintToLayers（两条路径不会画得不一样）');

console.log('\n=== 红外同步小窗 ===');
chk(/id="videoThermal"/.test(html), '红外视频元素存在');
chk(/id="thermalPip"/.test(html), '红外小窗容器存在');
chk(/id="thermalToggle"/.test(html), '红外开关按钮存在');
chk(/id="thermalToggle"[^>]*hidden/.test(html), '按钮默认隐藏（没有红外录像时不出现）');
chk(/<video id="videoThermal" muted playsinline/.test(html), '红外视频静音 + playsinline');
{
  const stageStart = html.indexOf('<div class="video-stage">');
  const stageEnd = html.indexOf('</div>\n    <div id="videoTelemetry"');
  const stage = stageStart < 0 ? '' : html.slice(stageStart, stageEnd > 0 ? stageEnd : stageStart + 2000);
  chk(/id="thermalPip"/.test(stage), '小窗放在视频容器里（才能叠在画面上）');
}
chk(/\.thermal-pip\{position:absolute;left:12px;bottom:56px/.test(html),
  '小窗定位在左下角，底边抬高 56px 让开播放器控制条');
chk(/\.thermal-pip\{[^}]*pointer-events:none/.test(html), '小窗不挡主视频的点击');
chk(/class="thermal-pip-label">红外</.test(html), '小窗带「红外」角标');
for (const f of ['thermalAvailable', 'mainAbsoluteTime', 'thermalSeekTarget', 'stopThermal',
                 'startThermal', 'syncThermal', 'applyThermalVisibility']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
chk(/thermalToggle\.hidden=!available/.test(body), '没有配对红外时开关自动隐藏');
chk(/clip&&!isInfraredPath\(clip\.path\)/.test(body), '只对可见光视频开小窗（红外片不自己配自己）');
chk(/thermalSource=d\.thermal\|\|null/.test(body), '红外路径来自遥测接口（后端已确认文件存在）');
chk(/thermalOffset=clip\.useProxy\?proxyBucketOf\(clip\.start\):0/.test(body),
  '主视频走转码片段时，小窗放原片并用同一 bucket 对齐');
chk(/Math\.abs\(videoThermal\.currentTime-target\)>0\.3/.test(body),
  '漂移超过 0.3 秒才纠正（避免频繁 seek 卡顿）');
chk(/videoThermal\.playbackRate=videoPlayer\.playbackRate/.test(body), '倍速同步');
chk(/\['play','pause','seeked','seeking','ratechange','ended'\]/.test(body),
  '播放/暂停/拖动/倍速/结束都同步');
chk(/videoThermal\.addEventListener\('error'/.test(body), '原片解不了时退回转码片段');
chk(/duration:String\(PROXY_SECONDS\)/.test(body), '兜底转码用与主视频相同的片段长度');
chk(/stopThermal\(\)/.test(body.slice(body.indexOf('function closeVideo('),
  body.indexOf('\n}', body.indexOf('function closeVideo(')))), '关闭视频时停掉小窗');

console.log('\n=== 标题栏排布（修竖排）===');
chk(/\.follow-label,\.ctrl-label\{[^}]*white-space:nowrap/.test(html),
  '标签强制不换行（否则中文会一个一个字竖排）');
chk(/\.follow-label,\.ctrl-label\{[^}]*flex:0 0 auto/.test(html),
  '标签不参与收缩（被挤窄就是竖排的根因）');
chk(/\.toggle-btn\{[^}]*flex:0 0 auto/.test(html), '开关按钮不参与收缩');
chk(!/for="followMode"/.test(html),
  '去掉了独立的「地图跟随」标签，改把说明写进选项（少占约 64px）');
chk(/<option value="fit">跟随·都可见<\/option>/.test(html), '选项自带「跟随」前缀，去掉标签也不歧义');
chk(/\.row\.video-head-tools\{flex:0 0 auto;flex-wrap:nowrap;gap:6px\}/.test(html),
  '右侧控件单行、间距收紧到 6px');

console.log('\n=== 检索结果卡的备选视频排布 ===');
chk(/class="alt-video-label"/.test(body), '「同一位置还有其他视频」有专门的类');
chk(/class="row alt-video-row"/.test(body), '备选按钮有自己的行容器');
chk(/<div class="alt-video-label">同一位置还有其他视频：<\/div>\s*\n\s*<div class="row alt-video-row">/.test(body),
  '说明文字单独一行，按钮另起一行（不再是同一行挤着）');
chk(!/<div class="row"[^>]*>\s*\n\s*<span[^>]*>同一位置还有其他视频/.test(body),
  '旧写法（文字和按钮同一行）已移除');
chk(/\.alt-video-label\{[^}]*margin:0 0 8px\}/.test(html), '标签与按钮之间有 8px 间距');
chk(/\.row\.alt-video-row\{gap:8px/.test(html), '按钮之间 8px 间距，且可自行换行');

console.log('\n=== 地图小窗 + 地图对照 ===');
chk(/id="mapPip"/.test(html) && /id="mapPipCanvas"/.test(html), '地图小窗容器与画布存在');
chk(/id="mapPipCanvas" class="map-pip-canvas"><\/div>/.test(html),
  'Leaflet 挂在独立画布上（角标不会被 Leaflet 清掉）');
chk(/id="mapPipToggle"/.test(html), '地图小窗开关存在');
chk(!/id="dockBtn"/.test(html), '「归位」按钮已删除（面板固定，没有可归位的）');
for (const f of ['ensureMapPip', 'applyMapPipBase', 'syncMapPip', 'applyMapPipVisibility',
                 'applySideCollapsed',
                 'refreshMapPipSize', 'applyThermalVisibility']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
chk(/\.map-pip\{position:absolute;right:12px;bottom:56px/.test(html),
  '小窗在右下角，底边同样抬高 56px 让开控制条');
chk(/\.map-pip\{[^}]*aspect-ratio:4\/3/.test(html), '小窗按 4:3 自适应高度');
chk(/\.map-pip\{[^}]*pointer-events:none/.test(html), '小窗不挡主视频点击');
chk(/\.map-pip-label\{[^}]*z-index:700/.test(html),
  '角标 z-index 高于 Leaflet 各 pane（200/400/600），否则会被地图盖住');
chk(/zoomControl:false,attributionControl:false/.test(body), '小窗关掉缩放控件和版权条');
chk(/dragging:false,scrollWheelZoom:false/.test(body), '小窗不可交互（纯显示）');
chk(/mapPipLayer\.bringToBack\(\)/.test(body), '小窗底图置于航迹之下');
chk(/const coords=trackLatLngs\(clip\.track\)/.test(body), '小窗复用主图的航迹坐标');
chk(/rotate\(\$\{droneBearing\}deg\)/.test(body), '小窗箭头朝向与大地图一致');
chk(/pip\.fitBounds\(/.test(body) === false,
  '不再每帧 fitBounds（改成变化明显才重设视野）');
chk(/function refreshMapPipSize\(\)/.test(body) && /width===mapPipSizedFor/.test(body),
  'invalidateSize 只在容器宽度真的变了才调（否则每帧触发一次重排）');
chk(/center\.distanceTo\(targetCenter\)>15/.test(body),
  '视野移动超过 15 m 才重设（标记仍然每帧移动，只有视野被节流）');
chk(/getBoundsZoom\(bounds,false\)/.test(body), '用 getBoundsZoom 判断目标缩放级');
chk(/pip\.panTo\(drone,\{animate:false\}\)/.test(body), '没有准星时用 panTo 跟飞机，不重设缩放');
console.log('\n=== 全屏要保留小地图 / 红外 / 上方开关 ===');
{
  // 自带控件的全屏按钮只把 <video> 全屏，而浮层都在 video 外面 —— 必须让整个对话框铺满
  // 需求变更：自制「全屏」按钮已删除 —— 它与 <video> 自带控件里那个重复，
  // 而原生那个是真铺满、零黑边（自制的 theater 布局始终有黑边）。
  chk(!/id="fullscreenToggle"/.test(html), '自制的「全屏」按钮已删除');
  const bar = html.slice(html.indexOf('class="row video-head-tools"'), html.indexOf('id="videoClose"'));
  chk(!/id="fullscreenToggle"/.test(bar) && /id="mapPipToggle"/.test(bar),
    '工具栏里保留准星/视场/红外/小地图，只去掉全屏');

    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
  const fs = body.slice(body.indexOf('function toggleFullscreen('), body.indexOf("if(fullscreenToggle)fullscreenToggle"));
  // 需求变更：实测「对话框铺满」在全屏下始终有黑边，而原生 <video> 全屏
  // 是真正铺满、零黑边。所以「全屏」按钮改为走同一条路（video 全屏），
  // 浮层由 fullscreenchange 里的 native-fs 类隐藏。
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
  chk(!/videoDialog\.requestFullscreen/.test(fs),
    '不再对对话框请求全屏（那条路有黑边）');
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）

    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
  chk(/function syncFullscreenBtn\(/.test(body), 'function syncFullscreenBtn()（按钮状态用底色表示）');

  // 关键：对话框平时靠 inline transform 定位，普通 CSS 规则盖不住，必须 !important。
  // 定位用「起点 + 固定长度」，比找结束锚点稳（同名选择器在文件里可能出现得更早）。
  const fsCssStart = html.indexOf('.video-dialog:fullscreen');
  const css = fsCssStart < 0 ? '' : html.slice(fsCssStart, fsCssStart + 700);
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）

  // 自带控件那个全屏按钮：拦截它，改成铺满模式
  const fc = body.slice(body.indexOf("['fullscreenchange','webkitfullscreenchange']"));
  chk(/document\.fullscreenElement===videoPlayer/.test(fc),
    '识别出「浏览器把 video 单独全屏了」这种情况');
  // 需求变更（用户实测：地图界面盖住了全屏视频）：
  // 原生全屏改成「只显示视频本身」，不再退出全屏转铺满模式。
  chk(/videoDialog\.classList\.add\('native-fs'\)/.test(fc),
    '原生全屏时加 native-fs 类');
  chk(/\.video-dialog\.native-fs \.video-dialog-head/.test(html)
     && /\.video-dialog\.native-fs \.map-pip/.test(html),
    'native-fs 下工具栏 / 小地图 / 红外 / 信息栏全部隐藏');
  chk(!/document\.exitFullscreen\(\)[\s\S]{0,80}setTheater\(true\)/.test(fc),
    '不再把原生全屏转成铺满模式');

  // Esc：先退全屏 -> 再退铺满 -> 最后才关窗口。
  // 按「Esc 判断那一行」定位，别去拼整段多行字符串（换行/缩进一变就找不到）。
  const escLine = body.indexOf("if(e.key!=='Escape')return;");
  const escBody = escLine < 0 ? '' : body.slice(escLine, escLine + 700);
  chk(escLine > 0, '找到 Esc 处理（按优先级分支的那处）');
    // 断言已随 theater 死代码删除（全屏统一走 <video> 原生 + native-fs）
  chk(escBody.indexOf('isTheater()') < escBody.indexOf('closeVideo()'),
    '两种全屏都退掉之后才关闭视频窗口');

  const close = body.slice(body.indexOf('function closeVideo('), body.indexOf('videoClose.addEventListener'));
  chk(/classList\.remove\('theater'\)/.test(close), '关窗口时清掉铺满状态（否则下次打开还是铺满）');
  chk(/exitFullscreen/.test(close), '关窗口时也退出全屏');
}
console.log('\n=== 左栏项目流程（创建 / 追加 / 删除 / 检测 / 生成）===');
{
  // 四步要按顺序排在左栏，GeoJSON 文件列表在最后
  const idx = {};
  for (const [key, needle] of [
    ['新建', 'id="createProjectBtn"'],
    ['追加', 'id="addFolderBtn"'],
    ['删除', 'id="deleteProjectBtn"'],
    ['检测', 'id="detectBtn"'],
    ['生成', 'id="makeSrtBtn"'],
    ['列表', 'id="fileList"'],
  ]) {
    idx[key] = html.indexOf(needle);
    chk(idx[key] > 0, `左栏有「${key}」控件`);
  }
  // 收敛成两个动作：新建项目（用项目名）/ 导入数据（加进当前项目，再点就是追加）
  chk(idx['删除'] < idx['新建'], '× 在顶部（贴在项目下拉框右侧）');
  chk(idx['新建'] < idx['追加'], '「新建项目」在「导入数据」左边');
  {
    const rowStart = html.indexOf('class="row proj-actions"');
    const row = html.slice(rowStart, html.indexOf('</div>', rowStart));
    chk(/id="createProjectBtn"/.test(row) && /id="addFolderBtn"/.test(row),
      '两个动作在同一排');
    chk(/<button id="createProjectBtn">新建项目<\/button>/.test(html), '按钮叫「新建项目」');
    chk(/<button id="addFolderBtn" class="secondary">导入数据<\/button>/.test(html),
      '按钮叫「导入数据」（原来叫「添加数据文件夹」）');
    // 用「具体元素/文案」判断，别用裸词 —— JS 注释里也会出现「追加数据」这类词
    chk(!/2 · 给当前项目追加数据/.test(html), '不再有单独的「追加数据」步骤标题');    chk(!/添加数据文件夹/.test(html), '旧的「添加数据文件夹」按钮文案已删除');
    chk(/<h2>项目数据<\/h2>/.test(html), '标题改成「项目数据」（与「轨迹文件」同为 h2，字号一致）');
    chk(!/<div class="desc">按/.test(html), '那行「按 1 → N 走一遍」的说明已删除');
  }
  // 项目名改成弹窗里输入，卡片里不再有常驻输入框
  {
    const card = html.slice(html.indexOf('class="card-head"'), html.indexOf('class="row proj-actions"'));
    chk(!/id="newProjectName"/.test(card), '卡片里不再有常驻的项目名输入框');
    chk(/id="newProjectModal"/.test(html), '有「新建项目」弹窗');
    const modalStart = html.indexOf('id="newProjectModal"');
    const modal = html.slice(modalStart, modalStart + 800);
    chk(/id="newProjectName"/.test(modal), '输入框在弹窗里');
    chk(/id="newProjectOk"/.test(modal) && /id="newProjectCancel"/.test(modal),
      '弹窗里有「确定 / 取消」');
    chk(/class="mini-modal"/.test(html) && /\.mini-modal\{position:fixed/.test(html),
      '弹窗是居中遮罩样式');
    chk(/function openNewProjectDialog\(/.test(body) && /function closeNewProjectDialog\(/.test(body),
      '有打开/关闭弹窗的函数');
    chk(/createProjectBtn\.addEventListener\('click',openNewProjectDialog\)/.test(body),
      '点「新建项目」先弹窗，不直接建');
    chk(/showNewProjectError\('请填项目名称。'\)/.test(body), '名称为空时报错，不提交');
    chk(/e\.key==='Enter'/.test(body), '回车即确认');
    chk(/e\.target===newProjectModal/.test(body), '点遮罩空白处取消');
    chk(/if\(newProjectModal&&newProjectModal\.style\.display!=='none'\)\{closeNewProjectDialog\(\);return\}/
      .test(body), 'Esc 先关弹窗（优先于关视频窗口）');
  }
  chk(idx['检测'] < idx['生成'] && idx['生成'] < idx['列表'],
    '检测与生成排在文件列表之前（先准备数据，再看文件）');

  for (const id of ['newProjectName', 'createProjectBtn', 'addFolderBtn',
                    'deleteProjectBtn', 'detectBtn', 'detectResult', 'makeSrtBtn',
                    'makeGeoBtn']) {
    chk(new RegExp(`const ${id}=document\\.getElementById\\('${id}'\\)`).test(body),
      `取了 #${id} 的引用`);
  }
}

console.log('\n=== 全自动流水线 ===');
{
  chk(/async function runAutoPipeline\(/.test(body), 'function runAutoPipeline()');
  const start = body.indexOf('async function runAutoPipeline(');
  const fn = body.slice(start, body.indexOf('\n}', start));

  chk(/collectPending\(name\)/.test(fn), '先检测（收集缺 SRT / 缺 GeoJSON 的清单）');
  chk(/extract-srt/.test(fn), '再生成 SRT');
  chk(/generate-geojson/.test(fn), '再生成 GeoJSON');
  chk(/await scanGeoJSON\(\)/.test(fn), '重新扫描文件列表');
  chk(/await loadAll\(\)/.test(fn), '最后全部加载到地图');

  // 顺序：SRT 必须在 GeoJSON 之前（GeoJSON 依赖 SRT）
  chk(fn.indexOf('/api/project/extract-srt') < fn.indexOf('/api/project/generate-geojson'),
    'SRT 在 GeoJSON 之前生成（GeoJSON 依赖 SRT）');
  chk(fn.indexOf('await scanGeoJSON()') < fn.indexOf('await loadAll()'), '先扫描再加载');
  // GeoJSON 那步要重新算一次「现在缺哪些」，否则刚生成 SRT 的视频会被漏掉
  chk((fn.match(/collectPending\(name\)/g) || []).length >= 2,
    'GeoJSON 之前重新算一次待办（刚生成 SRT 的视频这时才能生成）',
    String((fn.match(/collectPending\(name\)/g) || []).length) + ' 次');

  // 「全自动」开关已删除：新建/导入后一律自动跑，不再有勾选项与说明文字
  chk(!/autoPipeline/.test(body) && !/id="autoPipeline"/.test(html),
    '「全自动」复选框已删除');
  // 剥掉 CSS 注释再判 —— 说明「已不再使用」的注释里也会写出这些类名
  const cssClean = html.replace(/\/\*[\s\S]*?\*\//g, '');
  chk(!/flow-auto/.test(cssClean), '复选框的样式与说明文字也删了');
  chk(!/dsh-auto-pipeline/.test(body), '记住勾选状态的 localStorage 逻辑已删除');
  // 两处：新建项目、导入数据（原来还有第三处「补齐」按钮，已按需求去掉）
  chk((body.match(/await runAutoPipeline\(\);/g) || []).length === 2,
    '新建项目与导入数据之后都直接跑流水线（不再判断勾选）',
    String((body.match(/await runAutoPipeline\(\);/g) || []).length) + ' 处');
  chk(!/autoPipeline&&autoPipeline\.checked/.test(body), '没有残留的勾选判断');
  chk(/hide\(projectNotice\);/.test(body),
    '选中项目后不再重复显示「当前项目：xxx」（下拉框已经写着是哪个项目）');
  chk(!/当前项目：\$\{name\}/.test(body), '「当前项目：」那行提示已删除');
  chk(/show\(projectNotice,`已创建项目 \$\{name\}`\)/.test(body),
    'projectNotice 仍留给真正的消息（创建/删除/出错）');
  chk(!/视频结构检测/.test(body), '不再指向已不在流程里的「视频结构检测」页面');
}

console.log('\n=== 只处理 DJI 标准素材，其它如实跳过 ===');
{
  chk(/const DJI_VIDEO_RE=/.test(body), '用正则识别 DJI 标准素材名');
  const start = body.indexOf('async function collectPending(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  chk(/if\(!DJI_VIDEO_RE\.test\(stem\)\)return;/.test(fn),
    '非 DJI 素材（如「10 右岸-珠海市.mp4」）不进待办清单');
  chk(/if\(!video\.srt\)srt\.push/.test(fn), '缺 SRT 的进 SRT 清单');
  chk(/if\(!have\.has/.test(fn), '缺 GeoJSON 的进 GeoJSON 清单');
  const jobs = body.slice(body.indexOf('async function runJobs('), body.indexOf('async function runAutoPipeline('));
  chk(/failed\.push\(/.test(jobs) && /catch\(e\)/.test(jobs), '单个失败不影响其它（记下来继续跑）');
}

console.log('\n=== 三个步骤按钮排一排，做完变绿 ===');
{
  const start = html.indexOf('class="row flow-actions"');
  const row = html.slice(start, html.indexOf('</div>', start));
  for (const id of ['detectBtn', 'makeSrtBtn', 'makeGeoBtn']) {
    chk(new RegExp(`id="${id}"`).test(row), `#${id} 在同一排`);
  }
  chk(/<button id="detectBtn" class="secondary">检测字幕<\/button>/.test(html),
    '按钮改名「检测字幕」（原来是「开始检测」）');
  chk(!/开始检测/.test(html), '旧名字已不存在');

  const css = (html.match(/\.flow-actions[^{]*\{[^}]*\}/) || [''])[0];
  chk(/flex-wrap:nowrap/.test(css), '这一排不允许换行（三个挤在一行）');
  const btnCss = (html.match(/\.flow-actions button\{[^}]*\}/) || [''])[0];
  chk(/padding:0 8px/.test(btnCss) && /font-size:12px/.test(btnCss),
    '按钮收紧（全局 13px 22px 内边距会把它们撑到换行）');
  // 关键：不能等分宽度，否则最长的「生成 GeoJSON」被压到换行、✓ 掉到第二行
  chk(/flex:1 1 0/.test(btnCss),
    '三个按钮等分占满整行（需求：刚好占完格子长度，字号与下面那排一致）');
  chk(/white-space:nowrap/.test(btnCss), '文字与 ✓ 始终同一行');
  chk(/button\.done\{background:#dcfce7/.test(html), '完成态用绿色底色表示');
  chk(/button\.done::after\{content:' ✓'\}/.test(html), '完成态加一个 ✓');

  // 标题文字省掉：按钮自己说明了做什么。
  // 先去掉注释再匹配 —— 说明「已删除」的注释里也会出现这些字样（踩过好几次了）。
  const noComment = html.replace(/<!--[\s\S]*?-->/g, '');
  chk(!/<h2>数据准备<\/h2>/.test(noComment), '「数据准备」标题已删除');
  chk(!/3 · 检测与生成/.test(noComment), '「3 · 检测与生成」小标题已删除');
  const cardStart = noComment.indexOf('class="row flow-actions"');
  chk(/<h2>轨迹文件<\/h2>/.test(noComment.slice(Math.max(0, cardStart - 200), cardStart)),
    '合并后这张卡以「轨迹文件」标题开头（标题在步骤按钮上方）');

  chk(/function markDone\(/.test(body), 'function markDone()');
  chk(/function resetFlowButtons\(/.test(body), 'function resetFlowButtons()');
  chk(/async function refreshFlowStates\(/.test(body), 'function refreshFlowStates()');

  // 全自动流程里逐步点亮
  const auto = body.slice(body.indexOf('async function runAutoPipeline('), body.indexOf('\n}', body.indexOf('async function runAutoPipeline(')));
  chk(/markDone\(detectBtn,/.test(auto), '自动流程：检测完点亮「检测字幕」');
  chk(/markDone\(makeSrtBtn,/.test(auto), '自动流程：SRT 完点亮「生成 SRT」');
  chk(/markDone\(makeGeoBtn,/.test(auto), '自动流程：GeoJSON 完点亮「生成 GeoJSON」');
  chk(auto.indexOf('markDone(detectBtn') < auto.indexOf('markDone(makeSrtBtn')
    && auto.indexOf('markDone(makeSrtBtn') < auto.indexOf('markDone(makeGeoBtn'),
    '点亮顺序与执行顺序一致');

  // 没有待办也算做完（绿），否则"本来就没得做"会一直不亮
  chk(/markDone\(makeSrtBtn,srtResult\.failed\.length===0\)/.test(auto),
    '没待办时也标为完成（不是只有生成了才绿）');

  // 换项目要重置，否则上一轮的绿会留到下一个项目
  chk(/resetFlowButtons\(\);/.test(body.slice(body.indexOf("projectSelect.addEventListener('change'"))),
    '切换项目时先重置三个按钮');
  chk(/refreshFlowStates\(\)/.test(body.slice(body.indexOf('async function loadProjects('), body.indexOf('async function loadProjects(') + 600)),
    '载入项目后按实际情况刷新按钮状态');
}
{
  chk(/const DJI_VIDEO_RE=/.test(body), '用正则识别 DJI 标准素材名');
  const start = body.indexOf('async function collectPending(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  chk(/if\(!DJI_VIDEO_RE\.test\(stem\)\)return;/.test(fn),
    '非 DJI 素材（如「10 右岸-珠海市.mp4」）不进待办清单');
  chk(/if\(!video\.srt\)srt\.push/.test(fn), '缺 SRT 的进 SRT 清单');
  chk(/if\(!have\.has/.test(fn), '缺 GeoJSON 的进 GeoJSON 清单');
  const jobs = body.slice(body.indexOf('async function runJobs('), body.indexOf('async function runAutoPipeline('));
  chk(/failed\.push\(/.test(jobs) && /catch\(e\)/.test(jobs), '单个失败不影响其它（记下来继续跑）');
}

console.log('\n=== 删除项目 = 只清出项目列表，不删数据 ===');
{
  const start = body.indexOf('if(deleteProjectBtn)deleteProjectBtn.addEventListener');
  const fn = body.slice(start, start + 1600);
  chk(/window\.confirm\(/.test(fn), '删除前要确认');
  chk(/只会移除这个项目在列表里的那一项/.test(fn), '确认框说明：只移除项目列表里那一项');
  chk(/Data 里的原始视频、SRT、GeoJSON 全部保留在磁盘上，一个都不会删/.test(fn),
    '确认框说明：Data 里的文件全部保留、一个都不删');
  chk(/数据文件夹归哪个项目由你自己决定/.test(fn),
    '确认框说明：数据文件夹归哪个项目由用户决定');
  chk(/'\/api\/project\/delete'/.test(fn), '调删除接口');
  chk(/loadedTracks=\[\];/.test(fn), '删完把地图上的轨迹清掉');
  chk(/await loadProjects\(\)/.test(fn), '刷新项目列表');

  chk(/<button id="deleteProjectBtn" class="proj-del"/.test(html),
    '「移出项目列表」是下拉框右侧的小 ×（不再是单独一块按钮）');
  chk(/class="proj-row"/.test(html) && html.indexOf('id="projectSelect"') < html.indexOf('id="deleteProjectBtn"'),
    '× 紧跟在项目下拉框之后');
  chk(/title="把当前项目从项目列表里移除（不会删除任何数据文件）"/.test(html),
    '× 上的悬停说明写明不会删数据');
  // 同样要剥注释：说明「已不再使用」的注释里写了 .flow-hint
  chk(!/flow-hint/.test(body) && !/flow-hint/.test(html.replace(/\/\*[\s\S]*?\*\//g, '')),
    '原来那块常驻小字说明已移除（说明只在确认框里出现）');
  {
    const del = (html.match(/\.proj-del\{[^}]*\}/) || [''])[0];
    chk(/padding:0/.test(del), '× 的按钮内边距清零（全局 button 有 13px 22px，会把它挤扁）');
    chk(/width:44px;height:52px/.test(del), '× 是 44x52，和下拉框（height:52px）同高');
    chk(/align-items:center/.test(del) && /justify-content:center/.test(del), '× 居中');
  }
}

console.log('\n=== 追加数据要先扫描再提交 ===');
{
  // 导入数据有两个入口（选文件夹 / 选文件），共用一个提交函数
  const start = body.indexOf('async function pickFolder(');
  const fn = body.slice(start, body.indexOf('function closeImportDialog('));
  chk(/select-folder/.test(fn), '「选择文件夹」调 select-folder 让服务端弹原生选择框');
  chk(/scan-folder\?path=/.test(fn), '先调 scan-folder 扫描该文件夹');
  chk(/select-files/.test(fn), '「选择文件」调新的 select-files（可多选文件）');
  chk(/importScannedFolder\(scanned\.folder/.test(fn)
     && /importScannedFolder\(picked\.folder\)/.test(fn),
    '两个入口共用同一个提交函数');
  // 多选：一次挑多个文件夹时逐个扫描+提交，最后只提示一次汇总
  chk(/const paths=\(picked&&picked\.paths\)\|\|\(\(picked&&picked\.path\)\?\[picked\.path\]:\[\]\)/.test(fn),
    '「选择文件夹」兼容多选（paths 数组）与单选（path）两种返回');
  chk(/for\(const path of paths\)/.test(fn), '多个文件夹逐个导入');
  chk(/importScannedFolder\(scanned\.folder,paths\.length>1\)/.test(fn),
    '多选时走「安静模式」，不逐个弹提示');
  chk(/已导入 \$\{done\} 个文件夹/.test(fn), '多选时给一条汇总提示');

  // 地图跟随：用户手动动过地图后要宽限 5 秒，不能立刻把视野抢回去
  chk(/const FOLLOW_USER_GRACE=5000;/.test(body), '定义「用户操作后宽限 5 秒」常量');
  chk(/let lastUserMapAction=0;/.test(body), '记录用户最后一次操作地图的时间');
  chk(/watchUserMapActions/.test(body) && /container\.addEventListener\(ev,mark/.test(body),
    '监听用户对地图的直接操作（拖动 / 滚轮 / 缩放按钮 / 双击 / 触摸）');
  chk(/map\.on\('dragstart',mark\)/.test(body), '拖动同样计入用户操作');
  // 注意用带引号的精确匹配：boxzoomstart 里也含 zoomstart 这几个字母，
  // 早先这里用包含判断，一加 boxzoomstart 就误报了。
  chk(!/'zoomstart'/.test(body),
    '不用 Leaflet 的 zoomstart 判断用户操作（程序化 fitBounds 也会触发它，会把自动跟随误判成用户操作）');
  {
    const followBody = body.slice(body.indexOf('function followViewport('));
    const graceAt = followBody.indexOf('lastUserMapAction<FOLLOW_USER_GRACE');
    chk(graceAt > -1
       && graceAt < followBody.indexOf('map.panTo(drone')
       && graceAt < followBody.indexOf('map.fitBounds(target'),
      '宽限期判断排在「居中平移」与「重设视野」之前（center 与 fit 两种模式都受保护）');
    chk(/const restoring=followRestorePending;/.test(followBody),
      '宽限到期后主动收回跟随视野（而不是只恢复安全区判断）');
    chk(/if\(!restoring&&/.test(followBody) && followBody.indexOf('!restoring&&') < followBody.indexOf('inner.contains'),
      '收回这一次跳过「装得下就一动不动」，否则缩远了永远不跟回来');
    chk(/if\(restoring\|\|offX>0\.25/.test(followBody), 'center 模式同样会被收回视野');
  }
  chk(/followRestoreTimer=setTimeout\(/.test(body),
    '定时兜底：视频暂停时没有 tick，也能在宽限期后收回视野');

  // 手动缩放 -> 跟随改为「居中」，保持用户当前缩放级别
  chk(/function isZoomGesture\(ev\)/.test(body), '能判断「这次用户操作是缩放」');
  chk(/type==='wheel'\|\|type==='dblclick'\|\|type==='boxzoomstart'/.test(body),
    '滚轮 / 双击 / Shift 框选都算缩放');
  chk(/closest\('\.leaflet-control-zoom'\)/.test(body), '点 +/− 缩放控件算缩放');
  chk(/function switchFollowToCenter\(\)/.test(body) && /followModeSelect\.value='center'/.test(body),
    '手动缩放后跟随切到「跟随·居中」');
  chk(/followModeSelect\.value!=='fit'\)return;/.test(body),
    '只在 fit 模式自动切换，不覆盖用户明确选的「不跟随」');
  chk(/if\(isZoomGesture\(ev\)\)switchFollowToCenter\(\);/.test(body), '记用户操作时顺手切模式');
  chk(/map\.on\('boxzoomstart',mark\)/.test(body), 'Shift 框选缩放也计入用户操作');

  // 2 倍速按钮：放在「小地图」右边（按钮在 HTML 段里，不是 script 段 —— 用 html）
  chk(/id="mapPipToggle"[^>]*>小地图<\/button>\s*<button id="speedToggle"/.test(html),
    '「2×」按钮紧挨在「小地图」右边');
  chk(/id="speedToggle"[^>]*>2×<\/button>/.test(html), '按钮文案就是 2×');
  chk(/const FAST_PLAYBACK_RATE=2;/.test(body) && /const NORMAL_PLAYBACK_RATE=1;/.test(body),
    '1 倍 / 2 倍两个档位');
  chk(/speedToggle\.addEventListener\('click'/.test(body) && /fastSpeedOn=!fastSpeedOn/.test(body),
    '点一下在 1× 与 2× 之间切换');
  chk(/\[videoPlayer,videoThermal\]\.forEach/.test(body), '可见光与热成像小窗一起变速');
  chk(/el\.defaultPlaybackRate=rate;/.test(body),
    '同时设 defaultPlaybackRate —— load() 会把 playbackRate 复位成它，否则切视频就掉回 1×');
  chk(/addEventListener\('loadedmetadata',applyPlaybackRate\)/.test(body),
    '切换视频后自动重新应用倍速');
  chk(/setToggleState\(speedToggle,fastSpeedOn\)/.test(body), '按钮按下状态跟着走');
  chk(/if\(restoring\|\|offX>0\.25/.test(body) && !/fitBounds/.test(
      body.slice(body.indexOf("if(mode==='center')"), body.indexOf('// fit 模式'))),
    '「居中」模式只平移不改缩放 —— 这正是「跟随当前缩放等级」');
  chk(/async function pickFolder\(quiet\)/.test(fn), 'pickFolder 支持 quiet（自动弹出时取消不报错）');
  chk(/if\(pickFolderBtn\)pickFolderBtn\.addEventListener\('click',\(\)=>pickFolder\(\)\)/.test(body),
    '手动点「选文件夹」用箭头函数包一层（否则事件对象会被当成 quiet，提示被吃掉）');

  // 新建项目 -> 立刻弹文件夹选择框
  const create = body.slice(body.indexOf('async function doCreateProject('),
                            body.indexOf('if(createProjectBtn)'));
  chk(/await pickFolder\(true\)/.test(create), '新建项目后自动弹出数据文件夹选择框');
  chk(create.indexOf("jsonPost('/api/project/create'") >= 0
     && create.indexOf("jsonPost('/api/project/create'") < create.indexOf('await pickFolder(true)'),
    '先建好项目再弹选择框（顺序不能反）');
  chk(create.indexOf('await pickFolder(true)') < create.indexOf('await runAutoPipeline()'),
    '弹框选完再跑后续流程');

  const submit = body.slice(body.indexOf('async function importScannedFolder('),
                            body.indexOf('if(addFolderBtn)addFolderBtn.addEventListener'));
  chk(/folder,?\}/.test(submit.replace(/\s+/g, ' ')) || /folder\b/.test(submit),
    '提交时带上整个扫描结果对象');
  chk(/jsonPost\('\/api\/project\/add-folder',\{project_name:name,folder\}\)/.test(submit),
    'add-folder 提交完整 folder 对象（它原样存下，只传 path 会没有文件清单）');
  chk(/async function importScannedFolder\(folder,quiet\)/.test(submit),
    '提交函数支持安静模式（多选时不逐个提示）');
  chk(/r\.updated\?/.test(submit), '后端返回 updated=true 时提示「已更新」而不是「已导入」');
  // 只比真实调用，不比裸字符串 —— 注释里也出现了 add-folder 字样
  chk(fn.indexOf('scan-folder?path=') >= 0
     && fn.indexOf('scan-folder?path=') < fn.indexOf("importScannedFolder(scanned.folder"),
    '扫描在提交之前');
}

console.log('\n=== 画面右键取点 -> 地图标记 ===');
{
  // 左键必须保持浏览器自己的播放/暂停：只接管 contextmenu
  chk(/videoPlayer\.addEventListener\('contextmenu'/.test(body), '监听视频的右键菜单');
  chk(/e\.preventDefault\(\)/.test(body.slice(body.indexOf("addEventListener('contextmenu'"),
    body.indexOf("addEventListener('contextmenu'") + 200)), '右键时屏蔽浏览器菜单');
  chk(!/'click',\s*e=>[\s\S]{0,80}videoImagePoint/.test(body),
    '没有接管左键点击（左键仍然是播放/暂停）');

  chk(/function videoImagePoint\(e\)/.test(body), 'function videoImagePoint() —— 像素转归一化画面坐标');
  chk(/xImg:px\*2-1,yImg:1-py\*2/.test(body),
    'x 右为正、y 上为正（图像 y 向下，要翻转）');
  chk(/function groundPointAtEvent\(e\)/.test(body), 'function groundPointAtEvent() —— 画面点求地面坐标');
  // 跨行调用用「子串」判断，别拿正则去啃换行（这里已经栽过好几次）
  {
    const fn = body.slice(body.indexOf('function groundPointAtEvent('),
                          body.indexOf('// 在地图上打一个带名称的点'));
    const flat = fn.replace(/\s+/g, ' ');
    chk(flat.includes('groundPointForImage( drone,alt,yaw,pitch,0, pt.xImg,pt.yImg,fov[0],fov[1] )'),
      '复用已有的 groundPointForImage（和视场框同一套数学）', flat.slice(-90));
  }
  chk(/const fov=fovOf\(focal\)/.test(body) && !/fovOf\(focal\/dzoom\)/.test(body),
    '视场用「报告焦距」（含数码变焦），和视场框一致');
  chk(/if\(!Number\.isFinite\(pitch\)\|\|pitch>=0\)return null;/.test(body),
    '平视/朝上时不算（射线打不到地面）');
  chk(/if\(!Number\.isFinite\(alt\)\|\|alt<=0\)return null;/.test(body), '高度无效时不算');
  chk(/const i=currentTelemetryIndex\(\)/.test(body),
    '取的是「当前播放时刻」的遥测（和视场框同一个索引）');

  chk(/function addVideoMark\(latlng,name\)/.test(body), 'function addVideoMark() —— 在地图上打点');
  chk(/L\.circleMarker\(latlng/.test(body), '用圆点标记');
  chk(/bindTooltip\(name,\{[\s\S]{0,80}permanent:true/.test(body),
    '名称常驻显示（不用悬停才看得到）');
  chk(/function ensureVideoMarkLayer\(\)/.test(body), '标记放在独立图层组里，且懒建（L 可能异步到）');

  chk(/id="videoMarkModal"/.test(html) && /id="videoMarkName"/.test(html),
    '有命名弹窗与输入框');
  chk(/function openVideoMarkDialog\(/.test(body) && /function confirmVideoMark\(/.test(body),
    '有打开/确认函数');
  {
    const k = body.indexOf("videoMarkName.addEventListener('keydown'");
    chk(k > 0 && /e\.key==='Enter'/.test(body.slice(k, k + 220)), '回车即确认');
  }
  chk(/if\(videoMarkModal&&videoMarkModal\.style\.display!=='none'\)/.test(body),
    'Esc 也能关掉命名框');
}

console.log('\n=== 遥测信息与播放状态合并到一行 ===');
{
  chk(/<div class="video-foot">/.test(html), '有一个 .video-foot 容器把两者裹在一起');
  const footStart = html.indexOf('class="video-foot"');
  const foot = html.slice(footStart, html.indexOf('</div>', html.indexOf('id="videoStatus"')));
  chk(/id="videoTelemetry"/.test(foot) && /id="videoStatus"/.test(foot),
    '遥测信息与播放状态在同一个容器里');

  // 注意：全屏那几条规则的选择器也以 .video-foot{ 结尾，会先被 match 抓到，
  // 所以这里必须锚定基础规则本身（display:flex 开头那条）。
  const css = (html.match(/\.video-foot\{display:flex[^}]*\}/) || [''])[0];
  chk(/display:flex/.test(css), '.video-foot 是 flex 行');
  chk(/gap:10px 18px/.test(css), '两者之间有间距');
  chk(/border-top:1px solid #eef2f7/.test(css) && /background:#f8fafc/.test(css),
    '整条保留原来的分隔线与底色（原来挂在遥测那块上）');
  // 遥测那块原来带 padding/border/background，现在由容器统一负责，否则会双重内边距
  const tel = (html.match(/\.video-telemetry\{[^}]*\}/) || [''])[0];
  chk(!/padding:/.test(tel) && !/border-top:/.test(tel) && !/background:/.test(tel),
    '遥测块不再自带 padding/border/background（避免和容器叠加）');
  chk(/\.video-status\{[^}]*margin-left:auto/.test(html), '播放状态推到最右');
  chk(/\.video-status\{[^}]*white-space:nowrap/.test(html), '状态文字不换行');
}

console.log('\n=== 俯仰角用带符号的数字 ===');
{
  const start = body.indexOf('let pitchText=');
  const fn = body.slice(start, start + 400);
  chk(/pitch<0\?'-':'\+'/.test(fn), '俯角显示负号、仰角显示 +（不再写「俯角/仰角」两个字）');
  chk(/Math\.abs\(pitch\)\.toFixed\(1\)/.test(fn), '数值取绝对值后再带符号（不会出现「--27.2°」）');
  chk(/Math\.abs\(pitch\)<1/.test(fn) && /'水平'/.test(fn), '接近水平时仍显示「水平」');
  chk(!/'俯角 '|'仰角 '/.test(body), '「俯角 xx°」「仰角 xx°」的旧写法已删除');
  chk(/<b>俯仰角<\/b>/.test(body), '标题写全「俯仰角」');
}

console.log('\n=== 底图瓦片提示改成小字放地图下面 ===');
{
  chk(/id="tileHint"/.test(html), '有独立的 #tileHint 小字元素');
  const mapIdx = html.indexOf('id="map"');
  const legendIdx = html.indexOf('id="legend"');
  const hintIdx = html.indexOf('id="tileHint"');
  chk(hintIdx > mapIdx && hintIdx > legendIdx, '它在 DOM 里位于地图和图例之后（地图下面）');

  const start = body.indexOf("layer.on('tileerror'");
  const fn = body.slice(start, start + 900);
  chk(!/show\(/.test(fn), '不再用醒目的大红框（show(mapNotice,...)）');
  chk(/tileHint\.textContent=/.test(fn), '改写成小字元素的内容');
  chk(/tileHint\.style\.display='block'/.test(fn), '显示小字提示');
  chk(/refreshMapSizeSoon\(\)/.test(fn), '提示出现后让地图重算尺寸');
  chk(/baseMapWarned===kind/.test(fn), '同一底图只提示一次（不会每片瓦片都刷）');

  chk(/layer\.on\('tileload'/.test(body), '有瓦片取到就把提示收掉（底图其实可用）');
  const load = body.slice(body.indexOf("layer.on('tileload'"), body.indexOf("layer.on('tileload'") + 300);
  chk(!/baseMapWarned/.test(load), '	收提示时不动 baseMapWarned（否则底图不稳会反复弹）');

  const sb = body.slice(body.indexOf('function setBaseMap('), body.indexOf('function setBaseMap(') + 400);
  chk(/tileHint\.style\.display='none'/.test(sb), '换底图时把上一条提示清掉');

  chk(/\.tile-hint\{[^}]*font-size:12px/.test(html), '小字（12px）');
  chk(/\.tile-hint\{[^}]*color:#64748b/.test(html), '灰色，不抢眼');
  chk(/const tileHint=document\.getElementById\('tileHint'\)/.test(body), '取了 #tileHint 的引用');
}

console.log('\n=== 底图切换 ===');
chk(/currentBaseMapKind=kind;/.test(body), '切换底图时记录当前底图');
chk(/applyMapPipBase\(\);\s*\/\/ 地图小窗跟着换底图/.test(body), '小窗底图跟着主图切换');

console.log('\n=== 顶栏删除、标签名更改 ===');
{
  chk(!/class="header"/.test(html), '顶部深色标题栏已删除');
  chk(!/无人机巡查数据管理/.test(html.replace(/<!--[\s\S]*?-->/g, '')),
    '顶栏文字已删除（注释里的说明另计）');
  chk(!/\.header\{/.test(html.replace(/\/\*[\s\S]*?\*\//g, '')), '.header 样式也已删除');
  chk(/<title>视频地图<\/title>/.test(html), '浏览器标签名改成「视频地图」');

  // 顶栏原来是 76px，布局高度按它算过；删了顶栏必须改成整屏，否则底部空 76px
  const grid = (html.match(/\.layout\{([^}]*)\}/) || [])[1] || '';
  chk(/height:100vh/.test(grid), '布局高度改成 100vh（顶栏没了，不能再减 76px）', grid.slice(-60));
  chk(!/calc\(100vh - 76px\)/.test(grid), '不再有按 76px 顶栏计算的残留');
}

console.log('\n=== 地图默认光标改成箭头（原来是抓手）===');
{
  chk(/\.leaflet-container\.leaflet-grab\{cursor:default\}/.test(html),
    '地图默认光标是普通箭头（原来 Leaflet 给的是抓手）');
  chk(/\.leaflet-dragging \.leaflet-grab\{cursor:grabbing\}/.test(html),
    '按住拖动时仍是「抓住」的手感（拖动要有反馈）');
  // 先剥掉 CSS 注释再判 —— 说明「不动它」的注释里也会写出这条选择器
  const cssOnly = html.replace(/\/\*[\s\S]*?\*\//g, '');
  chk(!/\.leaflet-interactive\s*\{[^}]*cursor/.test(cssOnly),
    '没有去改指到轨迹线上的那个 pointer（按要求保持原样）');
  // 选择器必须两个类：Leaflet CSS 万一从 CDN 后插进来，同优先级会把单类规则压回去
  const rule = (html.match(/\.leaflet-container\.leaflet-grab\{[^}]*\}/) || [''])[0];
  chk(/\.leaflet-container\.leaflet-grab/.test(rule) === true, '选择器用两个类，压得住 Leaflet 自己的规则');
}

console.log('\n=== 轨迹线点不中：叠一条隐形粗线接鼠标 ===');
{
  chk(/const TRACK_LINE_WEIGHT=5;/.test(body), '有 TRACK_LINE_WEIGHT 常量（可见线宽）');
  chk(/const TRACK_HIT_WEIGHT=18;/.test(body), '有 TRACK_HIT_WEIGHT 常量（点选范围）');

  const start = body.indexOf('function addGeo(');
  const fn = body.slice(start, body.indexOf('\n}', start));

  // Leaflet 的 SVG 没有独立热区：能不能点中取决于描边宽度本身。
  // 所以必须画两条 —— 可见线 + 隐形粗线。
  chk((fn.match(/L\.geoJSON\(/g) || []).length === 2, 'addGeo 建了两条线（可见 + 隐形）',
    String((fn.match(/L\.geoJSON\(/g) || []).length) + ' 条');
  chk(/interactive:false/.test(fn), '可见线不接鼠标（判定只走隐形线，避免两套打架）');
  chk(/className:'track-hit'/.test(fn), '隐形线带 track-hit 类名（供 CSS 命中设置用）');
  chk(/weight:TRACK_HIT_WEIGHT/.test(fn) && /opacity:0/.test(fn),
    '隐形线：粗、透明（透明仍然能被命中，因为描边是「有」的）');
  chk(/weight:TRACK_LINE_WEIGHT/.test(fn), '可见线沿用原来的宽度（外观不变）');

  // 关键：航迹只能登记一次，否则检索结果会重复
  chk((fn.match(/loadedTracks\.push\(/g) || []).length === 1,
    'loadedTracks 只登记一次（两条线都登记会让检索出现重复轨迹）',
    String((fn.match(/loadedTracks\.push\(/g) || []).length) + ' 次');
  chk(/layer\.addTo\(layerGroup\)/.test(fn) && /hit\.addTo\(layerGroup\)/.test(fn),
    '两条线都进 layerGroup（清空图层时一起清掉）');
  // 弹窗与点击挂到隐形线上，点选范围才生效
  chk(/layer\.bindPopup\(/.test(fn) && /layer\.on\('click'/.test(fn),
    '弹窗与点击挂在隐形线上（这样才能在 18px 范围内点中）');
  chk(!/interactive:true/.test(fn), '不需要显式 interactive:true（Leaflet 默认就是可交互）');

  chk(/\.leaflet-interactive\.track-hit\{pointer-events:stroke\}/.test(html),
    'CSS 用 pointer-events:stroke 保证透明线也能命中（与是否填充/透明度无关）');
}

console.log('\n=== 轨迹地图的缩放上限 ===');
{
  chk(/const TRACK_FIT_MAX_ZOOM=15;/.test(body), '有 TRACK_FIT_MAX_ZOOM 常量（自动缩放的上限）');
  chk(/const TRACK_FOCUS_ZOOM=16;/.test(body), '有 TRACK_FOCUS_ZOOM 常量（定位到点的级别）');

  // 关键：fitBounds 不带 maxZoom 时，一小段轨迹会被放到很高一级，元素就出框了
  const code = body.replace(/\/\/[^\n]*/g, '');
  const fits = code.split('fitBounds(').slice(1);
  let capped = 0;
  for (const chunk of fits) {
    if (/maxZoom\s*:\s*TRACK_FIT_MAX_ZOOM/.test(chunk.slice(0, 260))) capped++;
  }
  chk(capped === fits.length && fits.length >= 4,
    '每一处 fitBounds 都带了 maxZoom 上限',
    `${capped}/${fits.length} 处`);
  chk(!/maxZoom\s*:\s*17/.test(code), '不再有写死的 maxZoom:17');
  chk(/setView\(hitFocusLatLng,TRACK_FOCUS_ZOOM\)/.test(body),
    '「地图定位到该点」用 TRACK_FOCUS_ZOOM（原来是 17）');
  chk(/const TRACK_FIT_MAX_ZOOM=15;[\s\S]{0,200}?const TRACK_FOCUS_ZOOM=16;/.test(body),
    '两个常量放在一起，方便以后调（数字越小看得越广）');
}

console.log('\n=== 视频面板顶边对齐 / 黑边 / 默认开关 ===');
{
  // 面板顶边要和左、中栏齐平：不能有 margin-top
  const panel = (html.match(/\.video-panel\{[^}]*\}/) || [''])[0];
  chk(!/margin-top/.test(panel), '视频面板不带 margin-top（否则顶边比左/中栏低一截）');

  // 黑边：画面区域按视频画幅定高，而不是固定撑满整栏 + contain
  const stage = (html.match(/\.video-panel \.video-stage\{[^}]*\}/) || [''])[0];
  chk(/aspect-ratio:16\/9/.test(stage), '画面区域有默认画幅比例（16:9）');
  chk(/flex:0 0 auto/.test(stage),
    '不再撑满整栏（那会让 16:9 的画面在更高的容器里留上下黑边）');
  chk(/max-height:calc\(100vh - 210px\)/.test(stage), '仍有高度上限，画幅很高时不会溢出');
  chk(/\.video-panel #videoPlayer\{display:block;width:100%;height:100%\}/.test(html),
    '播放器不再需要 object-fit:contain（容器比例已和画幅一致）');
  chk(/videoStage\.style\.aspectRatio=`\$\{videoPlayer\.videoWidth\} \/ \$\{videoPlayer\.videoHeight\}`/
    .test(body.replace(/\s+/g, ' ')) || /videoStage\.style\.aspectRatio/.test(body),
    '画幅在 loadedmetadata 里按实际分辨率动态设置（可见光 16:9、热成像 5:4 都对）');
  chk(/const videoStage=document\.querySelector\('\.video-stage'\)/.test(body), '取了画面区域的引用');

  chk(/let thermalOn=false;/.test(body), '红外小窗默认关');
  chk(/let mapPipOn=false;/.test(body), '地图小地图默认关');
}

console.log('\n=== 三栏并列布局 ===');
chk(/<div class="layout" id="layout">/.test(html), '页面用 .layout 承载三栏');
chk(/class="col col-left"/.test(html), '左栏：检索 / 加载');
chk(/class="col col-mid"/.test(html), '中栏：轨迹地图');
chk(/class="col col-right"/.test(html), '右栏：视频');
chk(/id="videoSlot"/.test(html), '右栏有未播放时的占位说明');
{
  const grid = (html.match(/\.layout\{([^}]*)\}/) || [])[1] || '';
  chk(/display:grid/.test(grid), '三栏用 grid 布局');
  chk(/grid-template-rows:minmax\(0,1fr\)/.test(grid),
    '显式栅格行高 1fr —— 三栏严格等高，底部才会对齐', grid.slice(0, 130));
  chk(/380px minmax\(0,1fr\) minmax\(0,1\.12fr\)/.test(grid),
    '列宽：左固定 380px，中/右按比例（地图略窄、视频略宽）', grid.slice(0, 90));
  chk(/height:100vh/.test(grid), '占满整个视口高度（顶栏已删除）');
  chk(/body\.side-collapsed \.layout\{grid-template-columns:40px/.test(html),
    '收起后左栏缩成 40px 窄轨');
}
// 卡片自带 margin-bottom:22px，会和 flex gap 叠加 ——
// 上面出现 38px 大缝、下面把卡片顶起来对不齐。而且在左栏里卡片是 .col-body 的
// 子元素、不是 .col 的直接子元素，只写 :last-child 盖不住。
chk(/\.col \.card,\s*\n\.col-body \.card\{margin-bottom:0\}/.test(html),
  '栏内卡片的下边距清零（间距只由 flex gap 控制）');
chk(/\.map-stack\{position:relative;flex:1;min-height:240px/.test(html),
  '撑满中栏高度的责任在 .map-stack（地图只负责填满它），最小 240px');
chk(/\.map-stack \.map-wrap\{flex:1;min-height:0;height:auto;margin-top:0\}/.test(html),
  '地图填满 .map-stack');

console.log('\n=== 图例改成地图左下角的小浮层 ===');
{
  chk(/<div class="map-stack">\s*\n\s*<div id="map"[^>]*><\/div>\s*\n\s*<div id="legend"/.test(html),
    '图例和地图包在同一个 .map-stack 里（这样才能绝对定位到地图上）');
  const lg = (html.match(/\.legend\{[^}]*\}/) || [''])[0];
  chk(/position:absolute/.test(lg), '图例绝对定位（浮在地图上）');
  chk(/left:10px/.test(lg) && /bottom:10px/.test(lg), '贴在地图左下角');
  chk(/z-index:\d+/.test(lg), '有 z-index', (lg.match(/z-index:(\d+)/) || [])[1] || '');
  chk(Number((lg.match(/z-index:(\d+)/) || [0, 0])[1]) > 700,
    'z-index 高于 Leaflet 的 pane（popup 是 700）',
    (lg.match(/z-index:(\d+)/) || [])[1] || '');
  chk(/font-size:11px/.test(lg), '字号 11px（原来 14px）');
  chk(/max-height:46%/.test(lg) && /overflow:auto/.test(lg), '内容多了可滚动，不会盖满地图');
  chk(/\.legend:empty\{display:none\}/.test(html), '没有轨迹时整个框不显示');
  chk(/\.legend-item\{[^}]*font-size:11px/.test(html), '每一项也是 11px');
  chk(/\.line\{width:18px;height:3px/.test(html), '色条缩小（原来 30x4）');
  // 图例不再单独占一行，所以「地图 -> 图例」的 DOM 关系变了
  chk(html.indexOf('id="legend"') < html.indexOf('id="hitDetail"'),
    '图例仍在该点信息之前');
}

console.log('\n=== 重要按钮合并成一条操作栏，其余挪到地图下面 ===');
{
  const probeIdx = html.indexOf('id="probePanel"');
  const mapIdx = html.indexOf('id="map"');
  const detailIdx = html.indexOf('id="hitDetail"');
  const statsIdx = html.indexOf('id="stats"');
  const altIdx = html.indexOf('id="altVideos"');
  const legendIdx = html.indexOf('id="legend"');

  chk(probeIdx > 0 && probeIdx < mapIdx, '操作栏在地图上面');
  chk(statsIdx > mapIdx && detailIdx > mapIdx && altIdx > mapIdx,
    '统计 / 其他视频 / 该点信息都在地图下面',
    `地图@${mapIdx} 统计@${statsIdx} 其他视频@${altIdx} 该点信息@${detailIdx}`);
  chk(detailIdx > legendIdx, '顺序：地图 -> 图例 -> 该点信息');

  // 4 个重要按钮在同一栏、同一行
  const bar = html.slice(probeIdx, mapIdx);
  for (const id of ['searchNearbyBtn', 'clearProbeBtn', 'playHitBtn', 'resultFlyBtn']) {
    chk(new RegExp(`id="${id}"`).test(bar), `操作栏里有 #${id}`);
  }
  const rowStart = bar.indexOf('class="row action-row"');
  const rowEnd = bar.indexOf('</div>', rowStart);
  const row = bar.slice(rowStart, rowEnd);
  for (const id of ['searchNearbyBtn', 'clearProbeBtn', 'playHitBtn', 'resultFlyBtn']) {
    chk(new RegExp(`id="${id}"`).test(row), `#${id} 在同一个 .row 里`);
  }
  // 只断言「元素没了」，不断言字符串 —— 文件里还留着说明它已移除的注释
  chk(!/id="nearbyResult"/.test(html) && !/nearbyResult/.test(body),
    '旧的 #nearbyResult 卡片已移除（注释另计）');
  chk(!/nearbyResult/.test(body), 'JS 里不再引用 nearbyResult');
}

console.log('\n=== 结果按钮改成常驻按钮（不再每次重建 DOM）===');
{
  const start = body.indexOf('function renderNearbyResult(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  chk(/playHitBtn\.style\.display=''/.test(fn), '渲染时显示「播放此处视频」');
  chk(/resultFlyBtn\.style\.display=''/.test(fn), '渲染时显示「地图定位到该点」');
  chk(/hitPayload=encoded;/.test(fn) && /hitFocusLatLng=hit\.pointLatLng;/.test(fn),
    '把载荷存起来给按钮用');
  chk(!/nearbyResult\.innerHTML/.test(fn), '不再往卡片里灌 HTML');
  chk(!/document\.getElementById\('resultFlyBtn'\)\.addEventListener/.test(fn),
    '不在渲染里挂一次性监听（每次渲染都挂会累积）');
  chk(/altVideos\.innerHTML=othersHtml;/.test(fn), '其他视频写进地图下面的容器');
  chk(/hitDetail\.innerHTML=/.test(fn), '该点信息写进地图下面的容器');
  chk(/refreshMapSizeSoon\(\);/.test(fn), '渲染后让地图重算尺寸');
}
{
  const init = body.slice(body.indexOf('clearProbeBtn.addEventListener'));
  chk(/playHitBtn\.addEventListener\('click'/.test(init.slice(0, 400)),
    '「播放此处视频」在初始化时挂一次监听');
  chk(/resultFlyBtn\.addEventListener\('click'/.test(init.slice(0, 400)),
    '「地图定位到该点」在初始化时挂一次监听');
}

console.log('\n=== 地图下面的次要内容要缩小 ===');
chk(/\.stats-compact \.stat\{padding:7px 12px;min-width:112px/.test(html),
  '统计格子缩小（原来 padding 12px 18px / min-width 150px）');
chk(/\.stats-compact \.stat-value\{font-size:17px/.test(html), '统计数值 17px（原 23px）');
chk(/\.alt-videos button\{height:30px;padding:0 11px;font-size:12px/.test(html),
  '其他视频按钮缩小');
chk(/\.below-map\{display:flex;flex-direction:column;gap:10px/.test(html), '地图下面用统一容器排布');

console.log('\n=== 该点信息用哪种排布 ===');
{
  const chunk = body.slice(body.indexOf('hitDetail.innerHTML'), body.indexOf('hitDetail.innerHTML') + 1500);
  chk(/class="hit-chips"/.test(chunk), '用小标签排布（一行一个字段）');
  chk(!/class="result-grid"/.test(body), '旧的 7 行网格已移除');
  // 距离字段标签固定为「水平距离」；命中画面时在数值后加「（画面中心）」区分语义
  for (const k of ['水平距离', '命中方式', '画面位置', '视频类型', '轨迹段', '该点视频时间', '轨迹段结束', '该点相对高度', '视频文件']) {
    chk(new RegExp('<span class="k">' + k + '</span>').test(chunk), `字段「${k}」在地图下面`);
  }
  chk(/id="hitHeight"/.test(chunk), '异步补高度用的 #hitHeight 也一起搬了（否则补不上）');
}

console.log('\n=== 地图容器尺寸失效的处理 ===');
chk(/function refreshMapSizeSoon\(\)/.test(body), 'function refreshMapSizeSoon()');
{
  const start = body.indexOf('function refreshMapSizeSoon(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  chk(/map\.invalidateSize\(\)/.test(fn), '会调用 map.invalidateSize()');
  chk((fn.match(/setTimeout/g) || []).length >= 2, '分两次调用，等布局稳定后再确认一次');
  chk(/if\(!map\)return;/.test(fn), '地图还没建就跳过');
}
chk(/function hideNearbyResult\(\)/.test(body), 'function hideNearbyResult()（结果相关的一起收）');
{
  const start = body.indexOf('function hideNearbyResult(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  chk(/playHitBtn\.style\.display='none'/.test(fn), '收起「播放此处视频」按钮');
  chk(/resultFlyBtn\.style\.display='none'/.test(fn), '收起「地图定位到该点」按钮');
  chk(/hitPayload=null;/.test(fn) && /hitFocusLatLng=null;/.test(fn), '清掉载荷');
  chk(/hide\(altVideos\)/.test(fn), '同时收起地图下面的其他视频');
  chk(/hide\(hitDetail\)/.test(fn), '同时收起地图下面的该点信息');
  chk(/refreshMapSizeSoon\(\)/.test(fn), '收起后让地图重算尺寸');
  // 注意：函数声明 `hideNearbyResult(){` 本身就含有 `hideNearbyResult()` 这段子串，
  // 直接用子串判断会把声明误判成递归调用。所以按「整行调用」来匹配。
  chk(!/^\s*hideNearbyResult\(\);/m.test(fn), '没有递归调用自己（批量替换时容易踩）');
  chk(!/probePanel/.test(fn), '不动选点/搜索按钮（它们属于选点流程，和检索结果无关）');
}
chk((body.match(/hideNearbyResult\(\)/g) || []).length >= 8,
  '原来 8 处 hide(nearbyResult) 都换成了 hideNearbyResult()',
  String((body.match(/hideNearbyResult\(\)/g) || []).length) + ' 处');
chk(/refreshMapSizeSoon\(\);\s*\n\s*\/\/ 只有 2D GeoJSON/.test(body)
  || /hitDetail\.style\.display='block';[\s\S]{0,400}?refreshMapSizeSoon\(\);/.test(body),
  '渲染结果后立即让地图重算（飞机/选点位置才不会偏）');
chk(/\.col\{[^}]*overflow:auto/.test(html), '每栏各自滚动（页面本身不滚，地图和视频才能固定对照）');
chk(/\.col-left \.file-list\{max-height:none;flex:1;min-height:220px/.test(html),
  '左栏文件列表撑满卡片（原来限高 330px，窄列里只剩两三条）');
console.log('\n=== 文件列表：只留必要信息 ===');
{
  const start = body.indexOf('function renderFiles(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));

  chk(/esc\(shortFileName\(f\.relative_path\)\)/.test(fn),
    '文件名用简化后的形式显示（年月日 时间 · 编号 · 后缀）');
  chk(!/file-meta/.test(fn) && !/数据文件夹：\$\{esc/.test(fn),
    '不再渲染「数据文件夹 / 相对路径」那行（太长会把窄列撑出横向滚动条）');
  chk(/item\.title=/.test(fn) && /相对路径：\$\{f\.relative_path\}/.test(fn),
    '完整路径挪到悬停提示里，信息没丢');
  chk(/class="file-badges"/.test(fn), '徽标放进独立容器，可整组换行');
  chk(/badge-type/.test(fn) && /formatSize\(f\.size\)/.test(fn)
    && /记录 \$\{f\.record_count/.test(fn) && /轨迹段 \$\{f\.segment_count/.test(fn),
    '保留：类型 / 大小 / 记录数 / 轨迹段');

  chk(/function parseDjiName\(/.test(body), 'function parseDjiName()（拆文件名，供显示和筛选共用）');
  chk(/function shortFileName\(/.test(body), 'function shortFileName()');
  {
    const p0 = body.indexOf('function parseDjiName(');
    const pFn = body.slice(p0, body.indexOf('\n}', p0));
    // 用子串比对而不是「正则套正则」—— 转义层级太容易写错，
    // 之前就在这里误报过：\\d（字面量反斜杠+d）和 \d（数字类）混用。
    chk(pFn.includes('base.match(/^(.+?)_(\\d{8})(\\d{6})_(\\d+)_([A-Za-z]+)$/)'),
      '按 前缀_年月日时分秒_编号_后缀 解析');
    chk(/if\(!m\)return null;/.test(pFn), '不符合命名规则返回 null（调用方原样显示，不硬拆）');
    chk(/date:`\$\{d\.slice\(0,4\)\}-\$\{d\.slice\(4,6\)\}-\$\{d\.slice\(6,8\)\}`/.test(pFn),
      '日期拆成 YYYY-MM-DD');
    chk(/time:`\$\{t\.slice\(0,2\)\}:\$\{t\.slice\(2,4\)\}:\$\{t\.slice\(4,6\)\}`/.test(pFn),
      '时间拆成 HH:MM:SS');
  }
}

console.log('\n=== 按年月日 / 视频类型筛选 ===');
chk(/id="filterDate"/.test(html) && /id="filterType"/.test(html), '日期和类型两个筛选框存在');
chk(/let fileFilterDate='';/.test(body) && /let fileFilterType='';/.test(body),
  '两个筛选状态默认都是空（不筛）');
for (const f of ['fileMatchesFilter', 'filteredGeoFiles', 'buildFileFilters', 'updateLoadAllLabel',
                 'dateOfFile']) {
  chk(new RegExp('function\\s+' + f + '\\s*\\(').test(body), `function ${f}()`);
}
{
  const start = body.indexOf('function filteredGeoFiles(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/\.map\(\(f,index\)=>\(\{f,index\}\)\)/.test(fn),
    '筛选结果保留原始下标（否则「加载」会加载错文件）');
}
{
  const start = body.indexOf('function buildFileFilters(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/new Set\(geoFiles\.map\(f=>dateOfFile/.test(fn), '日期选项来自实际文件名');
  chk(/new Set\(/.test(fn) && /streamLabelOf\(f\.relative_path\)/.test(fn), '类型选项来自实际文件名');
  chk(/\.sort\(\(a,b\)=>streamRankOf\(a\)-streamRankOf\(b\)\)/.test(fn),
    '类型选项按 4K -> 1080P -> 热成像 排序，与列表一致');
  chk(/if\(fileFilterDate&&!dates\.includes\(fileFilterDate\)\)fileFilterDate='';/.test(fn),
    '选项里没有的选中值要清掉（换项目后不会残留）');
  chk(/filterDate\.value=fileFilterDate/.test(fn), '刷新后回填当前选中值');
}
{
  const start = body.indexOf('function renderFiles(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/const entries=filteredGeoFiles\(\);/.test(fn), '列表按筛选结果渲染');
  chk(/if\(!entries\.length\)\{/.test(fn) && /没有符合筛选条件的文件/.test(fn),
    '筛不出东西时给出提示，而不是空白');
  chk(/const f=geoFiles\[index\];/.test(fn), '仍然用 geoFiles 的下标取数据');
}
{
  const start = body.indexOf('function updateLoadAllLabel(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/加载筛选（\$\{n\}）/.test(fn), '有筛选时按钮写明加载几条');
  chk(/'加载全部'/.test(fn), '没筛选时显示「加载全部」（缩短以放进一行）');
}
// 按钮文字必须禁止换行，否则窄栏里会被挤成「重新扫/描」两行
chk(/\.card-tools button\{[^}]*white-space:nowrap/.test(html),
  '卡片头部按钮禁止文字换行（原来会被挤成两行）');
chk(/\.card-tools button\{[^}]*height:32px;padding:0 10px;font-size:12px/.test(html),
  '卡片头部按钮收紧到 12px/32px（全局 button 是 16px + 13px 22px）');
chk(/<button id="refreshBtn" class="secondary">刷新<\/button>/.test(html),
  '「重新扫描」改叫「刷新」（更短，一行放得下）');
chk(/<button id="loadAllBtn">加载全部<\/button>/.test(html), '「加载全部轨迹」改叫「加载全部」');
{
  const start = body.indexOf('function ensureAllLoaded(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/const entries=filteredGeoFiles\(\);/.test(fn), '「加载全部」只加载筛选出来的');
  chk(/for\(const \{f,index\} of entries\)/.test(fn), '用原始下标作配色索引（颜色不随筛选变）');
  chk(/updateLoadAllLabel\(\)/.test(fn), '加载完恢复按钮文字用统一函数');
}
chk(/if\(filterDate\)filterDate\.addEventListener\('change'/.test(body)
  && /if\(filterType\)filterType\.addEventListener\('change'/.test(body),
  '两个筛选框都会触发重绘');
chk((body.match(/allLoaded=false;renderFiles\(\);/g) || []).length === 2,
  '改筛选时清掉 allLoaded（否则再点加载会以为已经加载过）',
  String((body.match(/allLoaded=false;renderFiles\(\);/g) || []).length) + ' 处');
chk(/buildFileFilters\(\);\s*\n\s*renderFiles\(\);/.test(body), '扫描后先建选项再渲染');
chk(/\.file-filter\{display:grid;grid-template-columns:auto minmax\(0,1fr\)/.test(html),
  '筛选区用两列网格（标签 + 下拉框两行），窄列也放得下');
chk(/\.file-filter \.ctrl-select\{width:100%;max-width:none\}/.test(html),
  '筛选框撑满可用宽度（不受 .ctrl-select 的 max-width 限制）');

{
  const fn = (html.match(/\.file-name\{[^}]*\}/) || [''])[0];
  chk(/font-size:12px/.test(fn), '文件名 12px（与下面徽标一致；原来是 15px→13px→12px）');
  chk(/white-space:nowrap/.test(fn) && !/word-break:break-all/.test(fn),
    '强制不换行（原来 word-break:break-all 会把「V」折到第二行）');
  chk(/overflow:hidden/.test(fn) && /text-overflow:ellipsis/.test(fn),
    '实在放不下就用省略号，而不是折行');
  chk(/background:#eef2f7/.test(fn), '文件名也带一层底色框（和下面的徽标一致）');
  chk(/width:fit-content/.test(fn) && /max-width:100%/.test(fn),
    '底色框贴着文字宽度，不撑满整行');

  // 名字和按钮是 flex 里的两个独立项：按钮不会盖住名字，名字也不会被按钮压到换行。
  // 这里断言「给名字让宽度」的几个数值，它们决定了名字能不能完整显示。
  chk(/\.file-main\{flex:1;min-width:0\}/.test(html), '名字那栏可伸缩且允许收缩（不会撑破）');
  const btn = (html.match(/\.file-item button\.secondary\{[^}]*\}/) || [''])[0];
  chk(/flex:0 0 auto/.test(btn), '按钮不参与伸缩（宽度固定）');
  chk(/height:30px;padding:0 10px;font-size:12px/.test(btn),
    '按钮收窄（34px→30px），把宽度让给文件名');
  chk(/\.file-item\{[^}]*gap:8px/.test(html), '列表项间距 10px → 8px，再让一点宽度');
  chk(!/position:absolute/.test(html.match(/\.file-item[^{]*\{[^}]*\}/g)?.join('') || ''),
    '列表项里没有绝对定位元素 —— 结构上不可能出现「按钮盖住名字」');
}
chk(/\.file-item \.badge\{font-size:12px;padding:3px 8px\}/.test(html), '徽标 12px（原 13px）');
chk(/\.file-badges\{display:flex;flex-wrap:wrap;gap:5px/.test(html), '徽标成组换行，间距收紧');
chk(/\.file-item\{[^}]*padding:11px 13px/.test(html), '列表项内边距收紧（原 15px 17px）');
chk(/\.file-item button\.secondary\{height:30px/.test(html), '「加载」按钮同步收小（30px/12px）');
// 两个动作竖排：横排会占约 120px 把文件名挤到截断（截图里出现过）
{
  const acts = (html.match(/\.file-acts\{[^}]*\}/) || [''])[0];
  chk(/flex-direction:column/.test(acts), '加载/删除竖排（横排会挡住文件名）');
  chk(/gap:8px/.test(acts), '两者留 8px 间距，避免误点');
  chk(/min-width:58px/.test(html), '两个按钮等宽（竖排对齐）');
}
chk(!/\.file-meta\{/.test(html), '已删掉不再使用的 .file-meta 样式');
chk(/\.file-list\{display:grid;gap:8px;align-content:start/.test(html),
  '列表行高只由内容决定（align-content:start）—— 否则列表被撑满后每行被拉开，条目上下留大片空白');
chk(/\.file-list\{[^}]*gap:8px/.test(html), '列表项间距 8px（原 12px），同屏看得更多');
chk(/id="sideToggle"/.test(html), '左栏右上角有收起按钮');
{
  // 收起按钮放在标题行里（文字左、按钮右），不再绝对定位单独占一行
  const headStart = html.indexOf('id="sideToggle"');
  const head = html.slice(Math.max(0, headStart - 260), headStart + 120);
  chk(/class="card-head"/.test(head), '收起按钮在 .card-head 标题行里');
  chk(head.indexOf('<h1>项目与数据</h1>') < head.indexOf('id="sideToggle"'),
    '标题在左、按钮在右');
  const st = (html.match(/\.side-toggle\{[^}]*\}/) || [''])[0];
  chk(!/position:absolute/.test(st), '不再是绝对定位（那会让它单独占一行）');
  chk(/flex:0 0 auto;width:28px;height:28px/.test(st), '尺寸和窄轨上的展开箭头一致（28x28）');
}
chk(/id="sideRail"/.test(html), '收起后留一条窄轨用于展开');
{
  // 收起/展开是一对箭头，方向要对应：收起 ‹ 、展开 ›
  const toggle = (html.match(/<button id="sideToggle"[^>]*>([^<]*)</) || [])[1] || '';
  const railIcon = (html.match(/<span class="side-rail-icon"[^>]*>([^<]*)</) || [])[1] || '';
  chk(toggle.trim() === '‹', '收起按钮是 ‹（指向左）', JSON.stringify(toggle));
  chk(railIcon.trim() === '›', '展开图标是 ›（指向右），与收起箭头成对', JSON.stringify(railIcon));
  chk(/\.side-rail-icon\{[^}]*width:28px;height:28px/.test(html),
    '展开图标做成和收起按钮同样大小的方块');
  chk(!/检<br>索/.test(html), '窄轨里不再用竖排文字');
  chk(/body\.side-collapsed \.col-left \.side-rail\{[^}]*align-items:flex-start/.test(html),
    '展开箭头放在窄轨顶部，与收起按钮位置对应');
  chk(/body\.side-collapsed \.col-left \.side-rail\{[^}]*cursor:pointer/.test(html)
    && /\.side-rail\{display:none\}/.test(html),
    '整条窄轨可点，展开前隐藏');
}
{
  const start = body.indexOf('function applySideCollapsed(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/side-collapsed/.test(fn), '切换 side-collapsed 类');
  chk(/map\.invalidateSize\(\)/.test(fn), '收起/展开后让地图重算尺寸');
  chk(/refreshMapPipSize\(\)/.test(fn) && /mapPip\.invalidateSize/.test(fn),
    '地图小窗也一起重算');
  // 视频面板是栏内普通元素，自动跟着栏宽变；这里只需更新控件换行与地图小窗
  chk(/applyVideoPanelLayout\(\)/.test(fn),
    '收起/展开后更新视频面板的控件换行（位置由 CSS 自动跟随）');
}
{
  const start = body.indexOf("window.addEventListener('resize'");
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('});', start));
  chk(/applyVideoPanelLayout\(\)/.test(fn), '窗口尺寸变化时同样更新视频面板');
  chk(/map\.invalidateSize\(\)/.test(fn), '窗口尺寸变化时地图重算');
}
chk(/window\.addEventListener\('resize'/.test(body),
  '监听窗口尺寸变化（分栏布局对宽度很敏感）');
// 旧的「transform 偏移停靠」整套机制已按需求删除（面板改成固定面板），
// 下面只断言它确实不在，避免以后有人又把这套脆弱逻辑加回来。
{
  const code = body.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
  chk(!/dockVideoToColumn/.test(code), '旧的 dockVideoToColumn() 已删除');
  chk(!/resetVideoPlacement|dockBtn/.test(code), '旧的归位逻辑已删除');
  chk(!/dialogOffset|dialogWidth|videoMaxH/.test(code), '偏移量/宽度/高度上限的全局状态已删除');
  chk(!/getBoundingClientRect\(\)\.left-base\.left/.test(code), '不再有任何「算落点」的代码');
  chk(/function applyVideoPanelLayout\(\)/.test(body), '换成只管控件换行的 applyVideoPanelLayout()');
}
chk(!/applyCompareMode/.test(body), '旧的「对照模式」代码已移除（新布局本身就是对照）');
chk(!/compare-on/.test(html), '旧的 compare-on 样式已移除');
chk(/width<780/.test(body) && /narrow-tools/.test(body),
  '窄窗口时允许标题栏控件换行（不再挤成竖排）');

console.log('\n=== 卡片头部与搜索区排布 ===');
chk(/<div class="card-head">/.test(html), '卡片头部改用 .card-head');
chk((html.match(/<div class="card-tools/g) || []).length === 3,
  '三张卡片的控件组都用 .card-tools（GeoJSON 文件 / 轨迹地图 / 标记点）',
  String((html.match(/<div class="card-tools/g) || []).length) + ' 处');
chk(/<div class="card-tools map-tools">/.test(html), '地图卡片的控件组额外带 map-tools');
chk(/<div class="card-tools marker-tools">/.test(html), '标记点卡片的控件组额外带 marker-tools');
chk(/<div class="card-head">\s*\n\s*<h2>轨迹地图<\/h2>/.test(html),
  '「轨迹地图」在新结构里');
chk(/<h2>轨迹文件<\/h2>/.test(html),
  '两张卡已合并，标题为「轨迹文件」');
{
  // 合并后行序：标题 -> 三个步骤 -> 筛选 -> 三个动作 -> 列表
  const order = ['<h2>轨迹文件</h2>', 'id="detectBtn"', 'class="file-filter"',
                 'card-tools file-actions', 'id="fileList"'].map((s) => html.indexOf(s));
  chk(order.every((n) => n > 0) && order.every((v, i) => i === 0 || order[i - 1] < v),
    '行序：标题 → 检测/生成 → 筛选 → 加载全部/刷新/清空 → 文件列表', order.join(','));

  const acts = html.slice(html.indexOf('card-tools file-actions'), html.indexOf('id="fileNotice"'));
  const ids = ['loadAllBtn', 'refreshBtn', 'clearBtn'].map((id) => acts.indexOf('id="' + id + '"'));
  chk(ids.every((n) => n > 0), '三个动作按钮在同一排');
  chk(ids[0] < ids[1] && ids[1] < ids[2], '顺序：加载全部 → 刷新 → 清空');
  chk(/<button id="clearBtn" class="secondary">清空<\/button>/.test(html), '「清除地图」改叫「清空」');
}
chk(!/class="row" style="justify-content:space-between"/.test(html),
  '嵌套 .row 的旧头部写法已全部移除');
chk(/\.card-tools\{display:flex;align-items:center;gap:8px;flex-wrap:nowrap;margin-left:auto\}/.test(html),
  '控件组 nowrap：整体换行，绝不内部拆开（这是「清除地图」被甩下一行的根因）');
chk(/\.card-head\{[^}]*flex-wrap:wrap/.test(html), '头部整体仍可换行（窄卡片时控件组整组下移）');
chk(/\.card-head h2\{margin:0\}/.test(html), '标题外边距清零（否则在 flex 里对不齐）');
{
  // 全局 select{width:100%} 会被下拉框继承，等于声明占满整行，把同行控件挤走
  const ctrl = (html.match(/\.follow-select,\.ctrl-select\{([^}]*)\}/) || [])[1] || '';
  const globalSelect = (html.match(/(?:^|\n)select\{([^}]*)\}/) || [])[1] || '';
  chk(/width:auto/.test(ctrl),
    '.ctrl-select 显式 width:auto，不继承全局 select 的 width:100%',
    '全局 select: ' + ((globalSelect.match(/(?:^|;)width:([^;]*)/) || [])[1] || '?'));
  chk(/width:100%/.test(globalSelect), '（确认全局 select 确实是 width:100%）');
}
chk(/\.map-tools button\.secondary\{height:36px/.test(html),
  '地图卡片头部按钮高度对齐下拉框的 36px');
// 「清除地图」和「重新扫描 / 加载全部轨迹」是一类操作，挪到一起了
{
  const tools = html.slice(html.indexOf('card-tools file-actions'), html.indexOf('id="fileList"'));
  const ids = ['loadAllBtn', 'refreshBtn', 'clearBtn'].map((id) => tools.indexOf('id="' + id + '"'));
  chk(ids.every((n) => n > 0), '「加载全部 / 刷新 / 清空」在同一排按钮里');
  chk(ids[0] < ids[1] && ids[1] < ids[2], '顺序：加载全部 → 刷新 → 清空');
  // 整行头部：从标题切到搜索区结束，里面应当只有底图选择、没有「清除地图」
  const mapHead = html.slice(html.indexOf('<h2>轨迹地图</h2>'),
                             html.indexOf('id="poiList"'));
  chk(!/id="clearBtn"/.test(mapHead), '地图卡片头部里不再有「清除地图」');
  chk(/id="baseMap"/.test(mapHead), '地图卡片头部保留底图选择');
  chk(/id="placeInput"/.test(mapHead), '地名搜索也在同一行（不再单独占一行）');
}
  // 注意别在末尾写 \} —— 这条规则后面还有 flex/min-width 才到右括号，
  // 要求「紧随右括号」会匹配不上（我上一版就栽在这儿）
  chk(/\.search-bar\{[^}]*margin:0 0 0 14px/.test(html),
    '搜索区不再是独立一行（并进标题行，左边留 14px 间距）');
chk(/\.search-bar\{[^}]*flex:1 1 260px/.test(html),
  '搜索区占据标题与「底图」之间的剩余宽度');
chk(/\.search-bar input\{[^}]*min-width:160px/.test(html), '输入框最小宽度 160px，窄卡片不溢出');
chk(/\.search-bar input\{[^}]*height:36px/.test(html), '输入框高度收到 36px（原来整行时是 50px）');
chk(/\.search-bar button\{height:36px/.test(html), '「搜索地名」按钮与输入框等高 36px');
{
  // 地名搜索必须真的在标题行里，否则地图上方又会多占一行
  const head = html.slice(html.indexOf('<h2>轨迹地图</h2>'), html.indexOf('id="poiList"'));
  chk(/id="placeInput"/.test(head), '地名输入框在轨迹地图的标题行内');
  chk(/id="baseMap"/.test(head), '底图选择也在同一行');
  const after = html.slice(html.indexOf('id="poiList"'), html.indexOf('id="probePanel"'));
  chk(!/class="search-bar"/.test(after), '标题行下面不再有独立的搜索行');
}

console.log('\n=== 2D / 3D GeoJSON 合并 ===');
chk(/const SHOW_3D_FILES=false;/.test(body), 'SHOW_3D_FILES 开关存在且默认关闭');
chk(/function pickOneGeoFilePerVideo\(/.test(body), 'function pickOneGeoFilePerVideo()');
chk(/geoFiles=pickOneGeoFilePerVideo\(d\.files\|\|\[\]\)/.test(body),
  '扫描时就去重（不是只隐藏显示，否则“加载全部”会画出重复轨迹）');
{
  const start = body.indexOf('function pickOneGeoFilePerVideo(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/if\(SHOW_3D_FILES\)return list;/.test(fn), '开关打开时原样返回（可一键恢复）');
  chk(/plainKeys/.test(fn) && /return !plainKeys\.has/.test(fn),
    '有普通版时丢掉 3D 版');
  chk(/streamKeyOf\(f\.relative_path\)/.test(fn), '用 streamKeyOf 抹掉 .3d 后再配对');
}
chk(/SHOW_3D_FILES=false;/.test(body) && body.indexOf('const SHOW_3D_FILES=') < body.indexOf('function scanGeoJSON'),
  'SHOW_3D_FILES 声明在 scanGeoJSON 之前（避免暂时性死区）');
chk(/3D 相关代码：暂时搁置，保留不动/.test(body), '3D 代码标注为搁置而非删除');
chk(/point_heights 与坐标第三维完全重复|point_heights 与坐标第三维/.test(body),
  '注释记录了 3D 文件体积大的原因（高度存了两遍）');
chk(/function is3dTrack\(/.test(body), 'is3dTrack 保留（3D 代码未删除）');

console.log('\n=== 丢弃 3D 文件后「该点相对高度」的补偿 ===');
chk(/function fetchTrackHeight\(/.test(body), 'function fetchTrackHeight()（改从 SRT 遥测取高度）');
chk(/function interpolateSeries\(/.test(body), 'function interpolateSeries()（按时间线性插值）');
{
  const start = body.indexOf('async function fetchTrackHeight(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/interpolateSeries\(data\.times,data\.alt,pointTime\)/.test(fn),
    '取高度用插值而不是取最近点（跨高度台阶时差一倍）');
  chk(/videoPathFromGeojson\(track\.fileInfo\.relative_path\)/.test(fn),
    '用 videoPathFromGeojson 把 .geojson 换成对应视频路径');
  chk(/telemetryCache\[path\]=data/.test(fn), '整份遥测缓存起来，重复检索不再请求');
  chk(/try\{/.test(fn) && /catch\(e\)\{[\s\S]{0,20}return null/.test(fn),
    '取不到就返回 null，不会让结果卡报错');
}
chk(/id="hitHeight"/.test(body), '结果卡里高度单元格有 id，便于异步补填');
{
  const start = body.indexOf('function renderNearbyResult(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/fetchTrackHeight\(hit\.track,hit\.time\)\.then/.test(fn), '渲染后异步补填高度');
  chk(/if\(!\(hit\.height!=null&&Number\.isFinite\(hit\.height\)\)\)/.test(fn),
    '只在 2D 文件没带高度时才去请求（有就别多此一举）');
}
chk(/中位差 0\.0003 m/.test(body) && /最大 0\.42 m/.test(body),
  '注释里记录了实测精度（中位 0.0003 m / 最大 0.42 m）');
chk(/GPS 高度是台阶状的/.test(body), '注释记录了残差来源（高度台阶 + 每 3 帧采样）');
chk(!/等价替换/.test(body), '不再声称是「等价替换」——实测有残差');

console.log('\n=== 轨迹气泡 ===');
chk(/从点击位置播放/.test(body), '气泡里有播放按钮');
{
  const start = body.indexOf('function openVideoFromPopup(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/if\(map\)map\.closePopup\(\);/.test(fn), '点击播放后自动关闭轨迹气泡');
  chk(fn.indexOf('closePopup') < fn.indexOf('try{'),
    '关闭气泡在解析参数之前 —— 即使参数有问题也不会留个气泡在那儿');
}
chk((body.match(/openVideoFromPopup\(/g) || []).length >= 3,
  '气泡按钮 / 结果卡按钮 / 备选按钮共用同一个入口（关气泡对后两者是空操作）');

console.log('\n=== 报错可见性（跨域脚本脱敏）===');
chk(/s\.crossOrigin='anonymous'/.test(html),
  'CDN 兜底脚本带 crossorigin —— 否则 Leaflet 内部报错只会显示「Script error.」');
chk(/Script error/.test(body) && /跨域脚本内部抛出/.test(body),
  '横幅对「Script error.」给出专门解释（否则提示等于没有信息量）');
chk(/function iconsUsable\(\)/.test(body), 'function iconsUsable()');
{
  const start = body.indexOf('function iconsUsable(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/if\(droneIcon&&crosshairIcon&&probeIcon\)return true;/.test(fn), '三个图标都在就直接可用');
  chk(/return ensureMapIcons\(\);/.test(fn), '缺了就现补一次');
}
{
  // 图标为 null 时异常会抛进 Leaflet 内部（跨域 -> 信息全无），所以每处建 marker
  // 之前都要先确认图标可用，而不是等到 Leaflet 自己报错
  const guards = (body.match(/if\(!iconsUsable\(\)\)return;/g) || []).length;
  const markers = (body.match(/L\.marker\(/g) || []).length;
  chk(guards >= 3, '三处会抛进 Leaflet 的 marker 创建都加了图标兜底', guards + ' 处');
  chk(markers >= 5, '（marker 创建点共 ' + markers + ' 处，另两处在小地图创建流程内）');
}
chk(/if\(!core\.every\(p=>p&&Number\.isFinite\(p\.lat\)&&Number\.isFinite\(p\.lng\)\)\)return;/.test(body),
  'followViewport 先挡掉含 NaN 的坐标，不喂给 Leaflet');

chk(/function clearFatal\(\)/.test(body), 'function clearFatal()（提示不能只增不减）');
chk(/id="fatalClose"/.test(html), '横幅带关闭按钮');
chk(/fatalClose'\)\?\.addEventListener\('click',clearFatal\)/.test(body)
  || /getElementById\('fatalClose'\)\?\.addEventListener\('click',clearFatal\)/.test(body),
  '点关闭按钮可手动清掉');
{
  const start = body.indexOf('function boot(');
  const fn = start < 0 ? '' : body.slice(start, body.indexOf('\n}', start));
  chk(/clearFatal\(\);/.test(fn), '初始化成功后自动清掉加载阶段的提示');
  chk(fn.indexOf('initBaseMap();') < fn.indexOf('clearFatal();'),
    '清提示在初始化之后（真出错时不会被误清）');
}

console.log('\n=== 空格 = 播放/暂停（点过全屏按钮后也必须成立）===');
chk(/function isTypingTarget\(/.test(body), 'function isTypingTarget()（输入框里不接管空格）');
chk(/function togglePlay\(/.test(body), 'function togglePlay()');
chk(/function isSpaceKey\(/.test(body), 'function isSpaceKey()（兼容 key 与 code）');
{
  const start = body.indexOf('function isTypingTarget(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  for (const t of ['input', 'textarea', 'select']) {
    chk(new RegExp(`tag==='${t}'`).test(fn), `输入控件 ${t} 里不接管空格（否则打不了空格）`);
  }
  chk(/isContentEditable===true/.test(fn), '可编辑元素里也不接管');
}
{
  // 关键（实测过）：Chrome 自带视频控件的键盘处理写在它自己的 shadow DOM 里，
  // 不属于“默认行为”，冒泡阶段 preventDefault 拦不住 —— 必须捕获阶段 +
  // stopPropagation，让事件根本到不了那个控件。
  const kd = body.indexOf("window.addEventListener('keydown',e=>{");
  chk(kd > 0, '空格监听挂在 window 上（比 document 更早）');
  const kdFn = body.slice(kd, body.indexOf('},true);', kd));
  chk(/grabSpace\(e\)/.test(kdFn), 'keydown 走 grabSpace() 统一处理');
  chk(/togglePlay\(\)/.test(kdFn), 'keydown 里执行播放/暂停');
  chk(/ae\.blur\(\)/.test(kdFn), '按下后把焦点从按钮上移开（再堵一层）');

  chk(/},true\);/.test(kdFn + '},true);') && /,true\);\s*\n\s*\nwindow\.addEventListener\('keyup'/
    .test(body.slice(kd)), 'keydown 用捕获阶段（第三个参数 true）');

  const ku = body.indexOf("window.addEventListener('keyup',e=>{");
  chk(ku > 0, '有配套的 keyup 处理（按钮激活在 keyup）');
  const kuFn = body.slice(ku, body.indexOf('},true);', ku));
  chk(/grabSpace\(e\)/.test(kuFn), 'keyup 同样截住');
  chk(!/togglePlay\(\)/.test(kuFn), 'keyup 里不再切一次播放状态（否则一次按键切两下）');

  const gs = body.indexOf('function grabSpace(');
  const gsFn = body.slice(gs, body.indexOf('\n}', gs));
  chk(/e\.preventDefault\(\)/.test(gsFn), 'grabSpace 里 preventDefault');
  chk(/e\.stopPropagation\(\)/.test(gsFn),
    'grabSpace 里 stopPropagation —— 这条才真正阻止自带控件收到空格');
  chk(/if\(!clip\)return false;/.test(gsFn),
    '没打开视频时不接管空格（否则页面上其他按钮的空格激活会被吃掉）');
  chk(/if\(isTypingTarget\(e\.target\)\)return false;/.test(gsFn), '输入框里不接管');

  chk(/fullscreenchange/.test(body) && /webkitfullscreenchange/.test(body),
    '进/出全屏后也把焦点从控件按钮上移开');
}
{
  const start = body.indexOf('function togglePlay(');
  const fn = body.slice(start, body.indexOf('\n}', start));
  chk(/if\(!clip\)return;/.test(fn), '没打开视频时不动作');
  chk(/videoPlayer\.paused/.test(fn), '按播放状态决定播放还是暂停');
  chk(/videoStopAt=null;/.test(fn),
    '停在轨迹段末尾时再按空格视为继续播放（否则一 play 就被立刻暂停，像没反应）');
  chk(/\.catch\(\(\)=>\{\}\)/.test(fn), 'play() 的 Promise 失败不会变成未处理异常');
}
chk(/id="baseMap"/.test(html), '底图选择框存在');
chk((html.match(/<option value="(street|satellite|osm)"/g) || []).length === 3,
  '网页地图的底图下拉提供街道图 / 卫星图 / OpenStreetMap 三种',
  (html.match(/<option value="(street|satellite|osm)"/g) || []).length + ' 个选项');
chk(/function\s+setBaseMap\s*\(/.test(body), 'function setBaseMap()');
chk(/function\s+initBaseMap\s*\(/.test(body), 'function initBaseMap()');
chk(/function\s+clearBaseLayers\s*\(/.test(body), 'function clearBaseLayers()');
chk(/tdt_vec/.test(body) && /tdt_cva/.test(body), '街道图 = 天地图矢量 + 矢量注记');
chk(/tdt_img/.test(body) && /tdt_cia/.test(body), '卫星图 = 天地图影像 + 影像注记');
chk(/\/maptile\/\$\{item\.source\}/.test(body), '底图走服务端代理（天地图 key 是服务器端类型）');
chk(/api\/config/.test(body), '启动时询问服务端有没有天地图 key');
chk(/option\.disabled=true/.test(body), '没有 key 时自动禁用天地图选项并退回 OSM');
chk(/baseMapSelect\.addEventListener\('change'/.test(body), '切换底图立即生效');
chk(/attribution:index===0\?def\.attribution/.test(body), '带天地图版权标注（合规要求）');
chk(!/tile\.openstreetmap\.org/.test(body), '页面不再直连 OSM（统一走代理与缓存）');

console.log('\n=== 按钮尺寸一致性 ===');
{
  const cssProps = (rule) => {
    const o = {};
    rule.split(';').forEach(p => {
      const i = p.indexOf(':');
      if (i > 0) o[p.slice(0, i).trim()] = p.slice(i + 1).trim();
    });
    return o;
  };
  const baseMatch = html.match(/(?:^|\n)button\{([^}]*)\}/);
  const playMatch = html.match(/\.play-btn\{([^}]*)\}/);
  chk(!!baseMatch, '找到通用 button 样式');
  chk(!!playMatch, '找到 .play-btn 样式');
  if (baseMatch && playMatch) {
    const base = cssProps(baseMatch[1]);
    const play = cssProps(playMatch[1]);
    for (const prop of ['padding', 'font-size', 'border-radius', 'font-weight']) {
      chk(base[prop] === play[prop],
        `“播放此处视频”的 ${prop} 与通用按钮一致`,
        `通用 ${base[prop]} / 播放 ${play[prop]}`);
    }
  }
  chk(/\.row>\.play-btn\{margin-top:0\}/.test(html), 'flex 行内的播放按钮不带额外上边距（不会错位）');
  // 操作条里这两个按钮必须同栏同一行、样式成对（一个主按钮、一个次要按钮）
  chk(/<button id="playHitBtn" class="play-btn"[^>]*>▶ 播放此处视频<\/button>/.test(html),
    '“播放此处视频”是常驻主按钮');
  chk(/<button id="resultFlyBtn" class="secondary"[^>]*>地图定位到该点<\/button>/.test(html),
    '“地图定位到该点”用 secondary 通用样式');
  {
    const rowStart = html.indexOf('class="row action-row"');
    const row = html.slice(rowStart, html.indexOf('</div>', rowStart));
    chk(/id="playHitBtn"/.test(row) && /id="resultFlyBtn"/.test(row),
      '两个结果按钮和选点/搜索按钮在同一行');
  }
}

console.log('\n=== 标记点报告（Word）===');
{
  chk(/<button id="markerReportBtn"/.test(html), '标记点卡片里有「生成 Word 报告」按钮');
  chk(/<div id="reportModal" class="mini-modal"/.test(html), '有报告生成前的弹窗');
  chk((html.match(/<input type="radio" name="reportImageMode"/g) || []).length === 2,
    '弹窗里两个截图尺寸选项（原分辨率 / 压缩至 320ppi）');
  chk(/name="reportImageMode" value="full" checked/.test(html), '默认选「原分辨率」');
  chk(/name="reportImageMode" value="a4"/.test(html), '另一个是「压缩至 320ppi」');

  chk(/jsonPost\('\/api\/report\/docx'/.test(body), '前端把这一批点提交给 /api/report/docx');
  chk(/jsonPost\('\/api\/snapshot'/.test(body), '每个点先取视频截图（/api/snapshot）');
  chk(/jsonPost\('\/api\/mapsnapshot'/.test(body), '每个点再取地图截图（/api/mapsnapshot）');
  chk(/api\('\/api\/reverse-geocode\?lat='/.test(body), '所在位置走 /api/reverse-geocode');

  const report = body.slice(body.indexOf('async function runWordReport('),
    body.indexOf('function startWordReport('));
  chk(report.length > 0, '找到 runWordReport()');
  chk(/const basemap=basemapKind\|\|reportBasemapKind\(\)/.test(body),
    '报告地图的底图来自弹窗里那个下拉（不再跟随网页地图的底图）');
  chk(/const DEFAULT_BASEMAP='street'/.test(body),
    "网页地图默认底图是街道图（DEFAULT_BASEMAP='street'）");
  chk(/<option value="street" selected>/.test(html),
    '底图下拉里街道图带 selected（initBaseMap 读的就是这个值）');
  chk(/let currentBaseMapKind=DEFAULT_BASEMAP;/.test(body),
    '脚本里的当前底图初始值也指向同一个常量');
  chk(!/\|\|'street'/.test(body), "没有残留的 ||'street' 兜底（否则会跟默认值不一致）");

  // 报告确认弹窗：报告自己的底图选项（和尺寸选项一样是单选，不是下拉），默认卫星图
  chk((html.match(/<input type="radio" name="reportBasemap" value="(street|satellite|osm)"/g) || []).length === 3,
    '弹窗里报告底图是三个单选项（与上面的尺寸选项同一种形式）',
    (html.match(/name="reportBasemap"/g) || []).length + ' 处');
  chk(/<input type="radio" name="reportBasemap" value="satellite" checked>/.test(html),
    '报告底图默认选卫星图（选项里也标了「推荐」）');
  chk(/推荐 —— 影像底图更好认/.test(html),
    '推荐理由就写「影像底图更好认」（短句，一行放得下）');
  chk(!/<select id="reportBasemap"/.test(html), '不再用下拉框');
  chk(/const REPORT_DEFAULT_BASEMAP='satellite'/.test(body),
    "REPORT_DEFAULT_BASEMAP='satellite'（与网页地图的默认值分开）");
  chk(/function reportBasemapKind\(\)/.test(body), 'function reportBasemapKind()');
  chk(/reportBasemapRadios\.find\(input=>input\.checked\)/.test(body),
    '取值从选中的那个单选框读');
  chk(/地图截图用下面选的底图（\$\{basemapDisplayName\(reportBasemapKind\(\)\)\}）/.test(body),
    '弹窗说明里写明会用哪个底图');
  chk(/function refreshReportBaseHint\(\)/.test(body)
    && /reportBasemapRadios\.forEach\(input=>input\.addEventListener\('change'/.test(body),
    '改单选，那句说明立即跟着变');
  chk(!/currentBaseMapKind/.test(report),
    '报告流程里不再引用网页地图的底图（两套底图彻底解耦）');
  chk(/return '未解析'/.test(body), '逆地理编码失败就标「未解析」（不编造位置）');
  chk(/link\.download=result\.download_name/.test(report),
    '下载用服务端给的中文文件名（download 属性）');
  chk(/reportBusy/.test(report) && /finally\{/.test(report),
    '生成中防重入，且无论成败都会解锁');
  chk(!/fldSimple|TOC \\o/.test(html), '页面里没有域代码目录那套东西（目录由服务端书签实现）');
}

console.log('\n=== 标记点列表：默认名与自动分栏 ===');
{
  chk(!/placeholder="例如/.test(html), '取点命名框不再写「例如：…」占位提示');
  chk(/function nextMarkerName\(/.test(body), 'function nextMarkerName()（项目名-序号）');
  chk(/videoMarkName\.value=nextMarkerName\(\)/.test(body),
    '弹窗打开时预填顺序生成的默认名');
  chk(/videoMarkName\.placeholder=''/.test(body), '预填的同时清掉占位文本');
  chk(/if\(videoMarkName\.select\)videoMarkName\.select\(\)/.test(body),
    '预填后整段选中 —— 一打字就是替换，不改就用默认');
  chk(/\|\|nextMarkerName\(\)/.test(body), '名字被清空再确定时，仍回落到默认名');

  chk(/function markerListLayout\(/.test(body) && /function applyMarkerLayout\(/.test(body),
    'function markerListLayout() / applyMarkerLayout()（自动分栏）');
  chk(/markerList\.style\.gridTemplateColumns/.test(body),
    '把算出来的栏数写进 grid-template-columns');
  chk(/classList\.toggle\('marker-compact',layout\.compact\)/.test(body),
    '挤不下时切到 marker-compact（只留名称）');
  chk(/applyMarkerLayout\(\);\s*\/\/ 栏宽变了/.test(body),
    '窗口尺寸变化时重排列表');

  chk(/\.marker-list\{[^}]*display:grid/.test(html), '列表用 grid（可多栏）');
  chk(/\.marker-list\.marker-compact \.marker-num\{display:none\}/.test(html),
    '密集模式隐藏经纬度，只保留名称');
  chk(/\.marker-name\{flex:0 1 auto/.test(html),
    '名称不再撑满整行（经纬度与 × 才能紧跟其后）');
  chk(/\.marker-num\{flex:0 0 auto;text-align:left/.test(html),
    '经纬度靠左对齐');
}

console.log('\n=== 点标记点跳转：只定位、不自动播放 ===');
{
  chk(/function openVideoFromPopup\(encoded,autoPlay=true\)/.test(body),
    'openVideoFromPopup 多了 autoPlay 参数（默认 true，老调用不受影响）');
  chk(/autoPlay:autoPlay!==false/.test(body), 'autoPlay 记进 clip');
  chk(/if\(st\.autoPlay===false\)\{/.test(body),
    'startClip：不自动播放时停在那一帧就 return');
  chk(/JSON\.stringify\(payload\)\), false\)/.test(body),
    '点标记点跳转时明确传 false');
  chk(/已定位到该时刻（未自动播放）/.test(body), '状态栏写明未自动播放');
  chk(/openVideoFromPopup\('\$\{encoded\}'\)/.test(html),
    '轨迹气泡的「从点击位置播放」没被改动（那个仍然自动播）');
}

console.log('\n=== 标记点名字不能重复 ===');
{
  chk(/<div id="videoMarkError" class="mini-modal-error"/.test(html),
    '命名框里有专门的错误行（和新建项目弹窗一个套路）');
  chk(/const videoMarkError=document\.getElementById\('videoMarkError'\)/.test(body),
    '取了 #videoMarkError 引用');
  chk(/function normalizeMarkerName\(/.test(body),
    'function normalizeMarkerName()（忽略大小写与多余空白）');
  chk(/function markerNameTaken\(/.test(body), 'function markerNameTaken()');
  chk(/function showVideoMarkError\(/.test(body), 'function showVideoMarkError()');
  chk(/if\(markerNameTaken\(name\)\)\{/.test(body), 'confirmVideoMark 里先查重');

  const confirm = body.slice(body.indexOf('function confirmVideoMark('),
    body.indexOf('function confirmVideoMark(') + 700);
  chk(confirm.indexOf('showVideoMarkError') < confirm.indexOf('addVideoMark(pendingMark'),
    '重名时先提示并 return —— 走不到 addVideoMark');
  chk(/videoMarkError\.style\.display='none'/.test(body),
    '打开/关闭弹窗时清掉上一次的错误提示');
}

console.log('\n=== 服务端返回网页时的报错要能看懂 ===');
{
  chk(/const text=await r\.text\(\)/.test(body),
    'api() 先取文本再自己解析 JSON（不再直接 r.json()）');
  chk(/服务端返回的不是数据，而是一个网页/.test(body),
    '不是 JSON 时给出人话解释（原来的 "Unexpected token \'<\'" 看不懂）');
  chk(/旧代码的服务/.test(body),
    '提示里点明「端口上还跑着旧代码服务」这个最常见原因');
  chk(/return d;\n\}/.test(body) && /if\(d&&d\.error\)throw new Error\(d\.error\)/.test(body),
    '正常 JSON 的路径不变：r.ok 且无 error 才返回，有 error 照旧抛');
}

console.log('\n=== 机头 → 准星 的注视指示线 ===');
{
  chk(/const LOOK_LINE_STYLE=\{/.test(body), '有独立的线样式常量');
  chk(/color:'#9ca3af'/.test(body) && /weight:1/.test(body) && /dashArray:'3,7'/.test(body),
    '很浅很细的灰色虚线（#9ca3af / 1px / 3,7）');
  chk(/interactive:false/.test(body), '指示线不接鼠标，不挡地图点击');
  chk(/lineCap:'round'/.test(body), '虚线端点是圆的（细线更好看）');
  chk(/const DRONE_NOSE_PX=14/.test(body), '机尖偏移量抽成常量，方便调');
  chk(/function droneNoseLatLng\(/.test(body), 'function droneNoseLatLng()（按航向算机头位置）');
  chk(/function updateLookLine\(/.test(body) && /function hideLookLine\(/.test(body),
    'function updateLookLine() / hideLookLine()');
  chk(/updateLookLine\(drone,target\)/.test(body), 'syncCrosshair 里跟着准星一起更新');
  chk(/function hideMapCrosshair\(\)\{[\s\S]{0,200}hideLookLine\(\)/.test(body),
    '准星隐藏时线一起收掉（关视频 / 关准星 / 清空地图都走 hideMapCrosshair）');
  chk(/map\.on\('zoomend',\(\)=>\{if\(mapCrosshair\)syncCrosshair\(\)\}\)/.test(body),
    '缩放后重算起点（起点是按像素偏移算的，缩放会变）');
}

console.log('\n=== 报告里的地图截图：16:9 + 飞机与注视虚线 ===');
{
  chk(/function reportDroneAt\(/.test(body),
    'function reportDroneAt()（取该时刻飞机的位置与朝向）');
  chk(/const loaded=loadedTracks\.find/.test(body),
    '飞机位置优先用已加载的航迹');
  chk(/indexAtTime\(track\.times,Number\(m\.time\)\|\|0\)/.test(body), '按标记点的时间取航迹点');
  chk(/bearingAt\(track\.coords,i\)/.test(body), '朝向用 bearingAt()');
  chk(/reportTrackCache\[want\]=track/.test(body),
    '没加载就现取这条视频的 GeoJSON 并缓存（不再依赖「已加载航迹」）');
  chk(/function reportMetersOffset\(/.test(body),
    'function reportMetersOffset()：算飞机相对目标点的南北/东西偏移');
  chk(/function reportMapZoomForOffset\(/.test(body),
    'function reportMapZoomForOffset()：飞机快出画才降级');
  chk(/await reportDroneAt\(m\)/.test(body), 'reportDroneAt 改成异步（要能现取航迹）');
  chk(/async function reportTrackFor\(/.test(body), 'function reportTrackFor()');
  chk(/const gj=await fetchGeo\(f\)/.test(body),
    '航迹没加载就现取这条视频的 GeoJSON（不再依赖「已加载航迹」）');
  chk(/reportTrackCache\[want\]/.test(body), '取回来的航迹按视频路径缓存，一个点只取一次');
  chk(/const REPORT_MAP_MAX_ZOOM=17/.test(body),
    '报告地图默认 17 级（18 级视野太窄、参照物不够）');
  chk(/let zoom=REPORT_MAP_MAX_ZOOM;\s*\n\s*\n\s*if\(drone\)/.test(body),
    '默认就是 17 级，只有飞机快出画才动缩放');
  chk(/return \{file:String\(\(d&&d\.file\)\|\|''\),zoom\}/.test(body),
    'reportMapImageOf 把实际用的缩放级一起返回');
  chk(/zoom:mapShot\.zoom/.test(body),
    '图注里的「缩放 N 级」用实际值');
  chk(!/zoom:TRACK_FOCUS_ZOOM/.test(body),
    '没有再写死 16 级（曾经图注写 16、地图却是 18）');
  chk(/zoom=reportMapZoomForOffset\(m\.lat,offset\.north,offset\.east\)/.test(body),
    '按飞机相对目标点的偏移选级');
  chk(/lat:m\.lat,\s*\n\s*lng:m\.lng,/.test(body),
    '取景中心永远是目标点（不再取两点中点）');
  chk(!/\=\(m\.lat\+drone\.lat\)\/2/.test(body), '已经不再算中点了');
  chk(/body\.target_lat=m\.lat/.test(body),
    '目标点仍然显式传给后端（红十字不跟着取景方式跑偏）');
  chk(/width:REPORT_MAP_WIDTH/.test(body) && /height:REPORT_MAP_HEIGHT/.test(body),
    '截图尺寸用常量（1600×640）');
  chk(/body\.drone_lat=drone\.lat/.test(body) && /body\.drone_bearing=drone\.bearing/.test(body),
    '把飞机的位置与朝向一起传给 /api/mapsnapshot');
}

console.log('\n=== 左列底边对齐 + 滚动条不再出现「浅灰直角」 ===');
{
  chk((html.match(/class="card card-fill"/g) || []).length >= 2,
    '轨迹文件卡片也带 card-fill（撑满左列，底边与中/右列对齐）',
    String((html.match(/class="card card-fill"/g) || []).length) + ' 处');

  chk(/@supports not selector\(::-webkit-scrollbar\)/.test(html),
    '标准滚动条属性用 @supports 只留给 Firefox');

  // 只数「声明」（带冒号）；注释里提到属性名不算
  const widthHits = (html.match(/scrollbar-width:/g) || []).length;
  chk(widthHits === 1,
    'scrollbar-width 只声明一次（在 @supports 里）—— 直接写它会让 Chrome 忽略 webkit 规则、箭头又回来',
    widthHits + ' 次');

  chk(/::-webkit-scrollbar-button[^{]*\{display:none/.test(html),
    '去掉滚动条两端的箭头按钮（那正是模块边界上的「浅灰直角」）');
  chk(/::-webkit-scrollbar-track[^{]*\{background:transparent/.test(html),
    '滚动条轨道透明，只留一条细圆角滑块');
  chk(/::-webkit-scrollbar-thumb[^{]*\{background:#cbd5e1;border-radius:999px/.test(html),
    '滑块是细圆角的');
}

console.log('\n=== 报告视频截图上的目标点标志（右键取点的位置）===');
{
  chk(/function videoImageSpot\(/.test(body), 'function videoImageSpot()：换成左上原点的 0..1 坐标');
  chk(/const pt=videoImagePoint\(e\);/.test(body) && /fx:\(pt\.xImg\+1\)\/2/.test(body),
    '换算用同一个 videoImagePoint（不另起一套算法）');
  chk(/let pendingMarkSpot=null;/.test(body), '记下待命名落点在画面上的位置');
  chk(/pendingMarkSpot=\(spot&&Number\.isFinite\(spot\.fx\)/.test(body),
    '命名框只在坐标有效时才记落点');
  chk(/pendingMarkSpot=null;\s*\/\/ 取消/.test(body) || /pendingMarkSpot=null;/.test(body),
    '关掉命名框（含取消）就丢掉落点，不带进下一个点');
  chk(/mark\.fx=pendingMarkSpot\.fx;/.test(body) && /mark\.fy=pendingMarkSpot\.fy;/.test(body),
    '确认保存时把 fx/fy 一起写进标记点');
  chk(/mark\.fx=Number\(m\.fx\);/.test(body) && /mark\.fy=Number\(m\.fy\);/.test(body),
    '从项目读回时也保留 fx/fy（老标记点没有就不写）');
  chk(/function markerSpotOf\(/.test(body), 'function markerSpotOf()：取落点并校验范围');
  chk(/body\.spot_fx=spot\.fx;/.test(body) && /body\.spot_fy=spot\.fy;/.test(body),
    '有落点时随 /api/snapshot 一起传（后端在那一处叠标志）');
}

console.log('\n=== DOM id 一致 ===');
const idsInHtml = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(x => x[1]));
const idsUsed = new Set([...body.matchAll(/getElementById\('([^']+)'\)/g)].map(x => x[1]));
const missing = [...idsUsed].filter(i => !idsInHtml.has(i));
chk(missing.length === 0, 'getElementById 目标都存在', missing.length ? '缺 ' + missing.join(',') : '无');

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
