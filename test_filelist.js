// 用真实文件名验证：类型标签 + 归拢排序 + 索引不被打乱
const fs = require('fs');
const path = require('path');

// 路径按脚本所在目录推导（换机器/换盘符都不用改）；可用 argv[2] 覆盖
const HTML = process.argv[2] || path.join(__dirname, 'Code', 'project_geojson_preview.html');
const html = fs.readFileSync(HTML, 'utf8');

function extractFn(name) {
  const start = html.indexOf('function ' + name + '(');
  let depth = 0;
  for (let j = html.indexOf('{', start); j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (depth === 0) return html.slice(start, j + 1); }
  }
  throw new Error(name);
}
// 抠 const 对象（STREAM_KINDS / STREAM_QUAL）：用大括号配对，别用正则
// （正则里的 \\s 在 JS 里是字面反斜杠，之前就栽在这里）
function extractConst(name) {
  const start = html.indexOf('const ' + name + '=');
  if (start < 0) throw new Error('const ' + name);
  let depth = 0;
  for (let j = html.indexOf('{', start); j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (depth === 0) return html.slice(start, j + 2); }
  }
  throw new Error('const ' + name);
}
const src = 'const t=k=>k;\n'
  + extractConst('STREAM_KINDS') + '\n' + extractConst('STREAM_QUAL') + '\n'
  + extractFn('streamLabelOf') + '\n' + extractFn('streamKindOf') + '\n' + extractFn('streamTagOfPath') + '\n' + extractFn('streamNoteOf') + '\n'
  + extractFn('streamRankOf') + '\n' + extractFn('streamKeyOf') + '\n'
  + extractFn('is3dTrack') + '\n' + extractFn('parseDjiName') + '\n' + extractFn('shortFileName')
  + '\n' + extractFn('dateOfFile')
  + '\nreturn {streamLabelOf,streamNoteOf,streamRankOf,streamKeyOf,is3dTrack,'
  + 'parseDjiName,shortFileName,dateOfFile};';
const { streamLabelOf, streamNoteOf, streamRankOf, streamKeyOf, is3dTrack,
        parseDjiName, shortFileName, dateOfFile } = new Function(src)();

// 筛选逻辑：把两个筛选状态做成闭包，便于反复改值测试
const buildFilter = new Function('dateOfFile', 'streamLabelOf', 'geoFiles', `
let fileFilterDate='';
let fileFilterType='';
${extractFn('fileMatchesFilter')}
${extractFn('filteredGeoFiles')}
return {
  set(d,t){fileFilterDate=d;fileFilterType=t},
  match(f){return fileMatchesFilter(f)},
  filtered(){return filteredGeoFiles()},
};`);

// SHOW_3D_FILES 作为参数注入，这样两种取值都能测。
// isCoverageExport 也要一起注入 —— pickOneGeoFilePerVideo 会调它滤掉覆盖导出产物
// （用户 2026-10-13：「这几个 coverage 的矢量图层……图上不要加载出来」）。
const buildPick = new Function('SHOW_3D_FILES', 'streamKeyOf', 'is3dTrack',
  'isCoverageExport',
  extractFn('pickOneGeoFilePerVideo') + '\nreturn pickOneGeoFilePerVideo;');

// 服务器返回的顺序（按文件名升序），就是截图里那个顺序
const geoFiles = [
  'DJI_20260924095258_0001_S.3d.geojson',
  'DJI_20260924095258_0001_S.geojson',
  'DJI_20260924095258_0001_T.3d.geojson',
  'DJI_20260924095258_0001_T.geojson',
  'DJI_20260924095258_0001_V.3d.geojson',
  'DJI_20260924095258_0001_V.geojson',
].map((relative_path) => ({ relative_path }));

console.log('=== 服务器原始顺序（按文件名）===');
geoFiles.forEach((f, i) => {
  console.log(`  [${i}] ${streamLabelOf(f.relative_path).padEnd(12)} ${f.relative_path}`);
});

const order = geoFiles
  .map((f, index) => ({ index, rank: streamRankOf(f.relative_path) }))
  .sort((a, b) => a.rank - b.rank || a.index - b.index);

console.log('\n=== 排序后显示顺序（类型归拢）===');
order.forEach(({ index }, pos) => {
  const f = geoFiles[index];
  console.log(`  第${pos + 1}行  ${streamLabelOf(f.relative_path).padEnd(12)} ${f.relative_path}   (dataset.index=${index})`);
});

console.log('\n=== 校验 ===');
let ok = true;
const chk = (c, label, extra = '') => { ok &&= !!c; console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`); };

const ranks = order.map((x) => x.rank);
chk(ranks.join(',') === [...ranks].sort((a, b) => a - b).join(','), '类型权重单调不减（确实归拢了）');
chk(order.length === geoFiles.length, '没有丢失条目');
chk(new Set(order.map((x) => x.index)).size === geoFiles.length, '索引不重复');
chk(order.map((x) => x.index).sort((a, b) => a - b).join(',') === '0,1,2,3,4,5',
  '索引仍是完整集合（点「加载」不会串位）');
// 同类型内保持原顺序：S.3d 必须排在 S 前面
// 2026-10-22：标签改成「镜头 + 画质」后，_S 的类型名是 'Wide 1080p'
const sIdx = order.filter((x) => streamLabelOf(geoFiles[x.index].relative_path) === 'Wide 1080p')
  .map((x) => geoFiles[x.index].relative_path);
chk(sIdx[0] && sIdx[0].includes('.3d'), '同类型内保持原顺序（_S.3d 仍在 _S 之前）', sIdx.join(' , '));

console.log('\n=== 同一视频的 .geojson / .3d.geojson 去重 ===');
{
  const wrap = (names) => names.map((relative_path) => ({ relative_path }));
  // isCoverageExport 用一个"按文件名判"的最小替身（真身也看 file_name，
  // 这里只喂 relative_path，所以替身足够）
  const fakeIsCoverageExport = (f) => {
    const n = String((f && (f.file_name || f.relative_path)) || '');
    return /(^|[\\/])coverage[\\/]/i.test(n)
        || /(^|[_.-])coverage/i.test(n)
        || /(^|[_.-])resolvable/i.test(n);
  };
  const pick = (names, show) =>
    buildPick(show, streamKeyOf, is3dTrack, fakeIsCoverageExport)(wrap(names))
      .map((f) => f.relative_path);

  const BOTH = [
    'DJI_20260924095258_0001_S.3d.geojson',
    'DJI_20260924095258_0001_S.geojson',
    'DJI_20260924095258_0001_T.3d.geojson',
    'DJI_20260924095258_0001_T.geojson',
    'DJI_20260924095258_0001_V.3d.geojson',
    'DJI_20260924095258_0001_V.geojson',
  ];

  const kept = pick(BOTH, false);
  console.log('  去重后（默认）:');
  kept.forEach((n) => console.log('    ' + n));

  chk(kept.length === 3, '6 条合并成 3 条（每个视频一条）', String(kept.length));
  chk(kept.every((n) => !/\.3d\.geojson$/.test(n)), '留下的都是体积更小的普通版');
  chk(pick(BOTH, true).length === 6, 'SHOW_3D_FILES=true 时两条都显示');

  // 边界：某个视频只有 3D 版，不能把它整个去掉
  const only3d = ['DJI_x_0001_V.3d.geojson', 'DJI_x_0001_S.geojson'];
  const k2 = pick(only3d, false);
  chk(k2.length === 2, '只有 3D 版的视频仍然保留（否则整条视频消失）', k2.join(' , '));
  chk(k2.includes('DJI_x_0001_V.3d.geojson'), '保留的正是那条 3D 版');

  chk(pick(['DJI_x_0001_V.geojson'], false).length === 1, '没有 3D 版时原样返回');
  chk(streamKeyOf('a_V.3d.geojson') === streamKeyOf('a_V.geojson'),
    '去重键把 .3d 抹掉后与普通版相同（大小写也不敏感）',
    streamKeyOf('A_V.3D.geojson'));

  // 覆盖图层导出的矢量产物要**从航迹列表里彻底消失**
  // （用户 2026-10-13：「这几个 coverage 的矢量图层没有存在的必要了，
  //  至少图上不要加载出来，也不要在搜索结果里面显示出来」）。
  {
    const withExports = [
      'DJI_20260924095258_0001_V.geojson',            // 真航迹
      'coverage/DJI_coverage_count1.geojson',          // 导出：在 coverage/ 子目录
      'coverage/DJI_coverage_count300.geojson',
      'coverage/DJI_resolvable_20cm.geojson',
      'coverage/DJI_20260924095258_0001_V.geojson',    // 导出：文件名和真航迹一样
    ];
    const kept2 = pick(withExports, false);
    chk(kept2.length === 1, '4 个导出产物被滤掉，只剩真航迹', kept2.join(' , '));
    chk(kept2[0] === 'DJI_20260924095258_0001_V.geojson',
      '留下的正是真航迹（不是同名的那份导出）');
    // SHOW_3D_FILES=true 时也必须滤（它只管 3D，不管导出）
    chk(pick(withExports, true).length === 1, 'SHOW_3D_FILES=true 时同样滤掉导出');
    // 逐条确认三种命名形态都认得
    for (const n of ['coverage/DJI_coverage_count1.geojson',
                     'DJI_coverage_count300.geojson',
                     'DJI_resolvable_20cm.geojson',
                     'x/coverage/DJI_a_V.geojson']) {
      chk(fakeIsCoverageExport({ relative_path: n }), `认得导出产物：${n}`);
    }
    chk(!fakeIsCoverageExport({ relative_path: 'DJI_20260924095258_0001_V.geojson' }),
      '真航迹不会被误滤');
  }

  // 实际流水线：scanGeoJSON 先去重 -> renderFiles 再按类型排序
  const pipeline = pick(BOTH, false)
    .map((relative_path, index) => ({ relative_path, index, rank: streamRankOf(relative_path) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((x) => streamLabelOf(x.relative_path) + '  ' + x.relative_path);
  console.log('\n  实际流水线（先去重、再按类型排序）:');
  pipeline.forEach((line, i) => console.log(`    第${i + 1}行  ${line}`));
  chk(pipeline.length === 3, '列表最终 3 行');
  // 2026-10-22：标签改成「镜头 + 画质」（Wide 4K / Wide 1080p / Thermal 1280×1024）
  chk(/Wide 4K/.test(pipeline[0]) && /Wide 1080p/.test(pipeline[1]) && /Thermal 1280×1024/.test(pipeline[2]),
    '顺序为 Wide 4K -> Wide 1080p -> Thermal 1280×1024');

  console.log('\n=== 文件名简化（年月日 时间 · 编号 · 后缀）===');
{
  const cases = [
    ['DJI_20260924095258_0001_V.geojson', '2026-09-24 09:52:58 · 0001 · V'],
    ['DJI_20260924095258_0001_S.geojson', '2026-09-24 09:52:58 · 0001 · S'],
    ['DJI_20260924095258_0001_T.geojson', '2026-09-24 09:52:58 · 0001 · T'],
    ['DJI_20260924095258_0001_v.geojson', '2026-09-24 09:52:58 · 0001 · V'],
    // 带子目录也要能取到文件名
    ['sub/DJI_20260924095258_0001_T.geojson', '2026-09-24 09:52:58 · 0001 · T'],
    // 编号位数不同
    ['DJI_20250101120000_12_T.geojson', '2025-01-01 12:00:00 · 12 · T'],
  ];
  for (const [input, expect] of cases) {
    const got = shortFileName(input);
    console.log(`    ${input.padEnd(40)} -> ${got}`);
    chk(got === expect, `简化正确`, got);
  }

  // 不符合命名规则的不要瞎猜，原样显示
  chk(shortFileName('随手起的名字.geojson') === '随手起的名字', '不符合命名规则就原样显示',
    shortFileName('随手起的名字.geojson'));
  chk(shortFileName('DJI_2026_0001_V.geojson') === 'DJI_2026_0001_V', '位数不对也不硬拆',
    shortFileName('DJI_2026_0001_V.geojson'));

  console.log('\n   最长/最短对比：');
  const longest = 'DJI_20260924095258_0001_V.geojson';
  console.log(`     原名 ${longest.length} 字 -> 简化后 ${shortFileName(longest).length} 字`);
  chk(shortFileName(longest).length <= 30, '简化后不超过 30 字（窄列一行放得下）',
    String(shortFileName(longest).length));
}

console.log('\n=== 按年月日 / 视频类型筛选 ===');
{
  chk(dateOfFile('DJI_20260924095258_0001_V.geojson') === '2026-09-24', '取到日期',
    dateOfFile('DJI_20260924095258_0001_V.geojson'));
  chk(dateOfFile('随手起的名字.geojson') === '', '拆不出日期就返回空串（不会被误筛掉）');

  const files = [
    { relative_path: 'DJI_20260924095258_0001_V.geojson' },
    { relative_path: 'DJI_20260924095258_0001_S.geojson' },
    { relative_path: 'DJI_20260924095258_0001_T.geojson' },
    { relative_path: 'DJI_20260925120000_0001_V.geojson' },
  ];
  const f = buildFilter(dateOfFile, streamLabelOf, files);

  const show = (label) => {
    const got = f.filtered().map((x) => `${x.index}:${streamLabelOf(x.f.relative_path)}`);
    console.log(`    ${label.padEnd(26)} -> ${got.length} 条  [${got.join('  ')}]`);
    return got;
  };

  f.set('', '');
  chk(f.filtered().length === 4, '不筛时全部返回', String(f.filtered().length));

  f.set('2026-09-24', '');
  chk(show('日期 2026-09-24').length === 3, '按日期筛出 3 条');

  f.set('2026-09-25', '');
  chk(show('日期 2026-09-25').length === 1, '另一天只剩 1 条');

  f.set('', 'Wide 4K');
  chk(show('类型 Wide 4K').length === 2, '按类型筛出 2 条');

  f.set('2026-09-24', 'Thermal 1280×1024');
  chk(show('日期 + 类型组合').length === 1, '两个条件同时生效');

  f.set('2026-09-24', '');
  const idx = f.filtered().map((x) => x.index);
  chk(idx.join(',') === '0,1,2', '保留原始下标（「加载」不会错位）', idx.join(','));

  f.set('2020-01-01', '');
  chk(show('不存在的日期').length === 0, '筛不出就是空，界面会给出提示');
}

console.log('\n=== 三个标签的悬停说明 ===');
  for (const p of ['x_V.MP4', 'x_S.MP4', 'x_T.MP4']) {
    console.log(`  ${streamLabelOf(p).padEnd(18)} -> ${streamNoteOf(p)}`);
  }
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
