// 图墙副标题（`Across N flight(s), M frame(s) …`）的测试。
//
// 为什么单测这一行：
//   ① 它必须说清"跨**整个项目**的架次"，而不是当前 Flight 下拉框那一个 ——
//      这个"局部 vs 全局"的分工是功能的价值所在（同一块地多趟飞过、清晰度差几倍）。
//   ② 我在这里踩过一次坑：想加注释说明，**把注释放进了模板字符串拼接中间**，
//      于是那几行说明文字会当作文本渲染到界面上。这类"注释变成界面文字"的错
//      不会报错，只会让页面上多出一段莫名其妙的话。

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'Code', 'project_geojson_preview.html'), 'utf8');

let ok = true;
const chk = (c, label, extra = '') => {
  ok = ok && !!c;
  console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
};

// 取出 frameGalleryRender 里组装标题/副标题的那一段。
// 注意 headHtml 现在是 `'<div class="fg-head"><h4>'+t('Frames of this spot')…`，
// 所以只锚在字符串字面量本身，不要再锚 `=`（i18n 那轮把它从 '=' 改成了 '+'）。
const iHead = html.indexOf("const headHtml='<div class=\"fg-head\"><h4>'+");
const iEnd = html.indexOf('frameGalleryAppend();', iHead);
const seg = iHead >= 0 && iEnd > iHead ? html.slice(iHead, iEnd) : '';

console.log('\n=== 1) 副标题的组装方式 ===');
chk(iHead > 0, '找到 headHtml 的组装处');
{
  // 只检查 headHtml 的**值**里有没有混进注释文字。
  // 不能扫整段 —— 同一段里 modeHtml 的 title 属性里本来就有 "//"（那是给用户的说明）。
  const vStart = html.indexOf("'<div class=\"fg-head\">", iHead);
  const vEnd = html.indexOf("';", vStart);
  const value = vStart >= 0 && vEnd > vStart ? html.slice(vStart, vEnd) : '';
  // 模板字符串里出现 "// " 或 "/*" 就当是注释漏进去了
  chk(!/\/\/\s|\/\*/.test(value),
    'headHtml 的值里没有混进注释文字', value.slice(0, 60).replace(/\s+/g, ' '));
}
// 文案改成 t('英文原串') 之后，断言跟到同样的形状上 ——
// 不然这些会因为"字符串被 t() 包起来"而误报（实际逻辑一个字没改）。
chk(/across'\)\} <b>\$\{sorties\}<\/b> \$\{t\('flight\(s\)'\)\}/i.test(seg),
  '副标题里报了跨架次数 sorties');
chk(/<b>\$\{shownPasses\}<\/b> \$\{t\('frame\(s\)'\)\}/.test(seg),
  '副标题里报了这次列了几张 frame(s)');
chk(/\$\{esc\(t\(modeLabel\)\)\}/.test(seg),
  '副标题开头是当前检索档位名（Different angles / Every pass / Clearest only）');

console.log('\n=== 2) 注释写在赋值之前，不在字符串里 ===');
{
  // 关键：说明性注释应当在 const headHtml 之前
  const iComment = html.indexOf('分工是有意的');
  chk(iComment > 0, '有"分工是有意的"这条说明注释');
  chk(iComment < iHead, '注释在 headHtml 之前（没有插进字符串之间）',
    `comment@${iComment} headHtml@${iHead}`);
}

console.log('\n=== 2b) 检索档位：三档 + 记忆 + 默认值 ===');
{
  const iModes = html.indexOf('const FRAME_MODES=[');
  const seg2 = iModes < 0 ? '' : html.slice(iModes, iModes + 400);
  chk(iModes > 0, '有 FRAME_MODES 定义');
  for (const v of ['angles', 'passes', 'best']) {
    chk(seg2.indexOf(`'${v}'`) >= 0, `档位里有 ${v}`);
  }
  chk(/readFrameMode/.test(html) && /saveFrameMode/.test(html),
    '档位会记住（读 + 写）');
  chk(/return 'angles'/.test(html),
    '默认档是 angles —— 遮挡场景下唯一有用的那档');
  // 请求里必须带上 mode。
  // 锚点要选 **URL 字符串本身**，不要锚在调用点的写法上 ——
  // 我把 URL 构造挪进 `URLSearchParams({...mode})` 之后，原来那个锚点
  // （`api('...')` 紧跟 `mode:readFrameMode()`）就落空了，测试会假失败。
  const iCall = html.indexOf("'/api/project/coverage/frames?'");
  const callSeg = iCall < 0 ? '' : html.slice(iCall, iCall + 700);
  chk(/\bmode\b/.test(callSeg), '请求里带上了 mode', callSeg.slice(0, 70));
  // 360 那条也要带 mode
  const iSph = html.indexOf("'/api/pano360/frames?'");
  const sphSeg = iSph < 0 ? '' : html.slice(iSph, iSph + 500);
  chk(iSph > 0, '找到了 360 检索接口的调用');
  chk(/\bmode\b/.test(sphSeg), '360 那条接口也带上了 mode', sphSeg.slice(0, 70));
  // 换档位要重新检索
  chk(/'change',\(\)=>\{[\s\S]{0,120}searchFramesOfSpot\(\)/.test(html),
    '换档位会重新检索');
}

console.log('\n=== 3) 检索跨架次、不被 Flight 下拉框限制 ===');
{
  // 请求里不能带 srt 参数（带了就只查一个架次了）
  const iCall = html.indexOf("'/api/project/coverage/frames?'");
  const callSeg = html.slice(iCall, iCall + 600);
  chk(iCall > 0, '找到 frames 接口调用');
  chk(!/srt\s*:/.test(callSeg),
    '请求里**没有** srt 参数（否则退化成只查当前架次）');
  chk(/limit\s*:/.test(callSeg), '带了 limit');
  chk(!/folder_index\s*:/.test(callSeg), '请求里也没有 folder_index 限制');
}

console.log('\n=== 4) 每张卡 = 一个**独立趟次**（不是一个架次一张卡）===');
{
  // 用户当场发现的 bug：一个位置同一架次要来回飞好几趟、每趟都拍到，
  // 而"每架次只给最清的一帧"会把其中大部分藏起来。
  // 实测那个点：架次 A 4 趟、架次 B 9 趟，合计 13 个画面，却只显示出 1 条。
  const i = html.indexOf('const shownPasses=hits.length;');
  // 切片要够长：中间插了下拉框的代码（档位 + 边距），1200 会截不到副标题模板。
  // 改成取到"写回 box.innerHTML"那一段为止，跟着代码走而不是写死长度。
  const iEnd = html.indexOf("box.innerHTML=headHtml", i);
  const seg = i < 0 ? '' : html.slice(i, iEnd > i ? iEnd : i + 3000);
  chk(i > 0, '副标题里有趟数逻辑');
  // 副标题要说明排序依据。用户 2026-10-13 改成了「居中 > 变焦覆盖 > 其余」，
  // 所以断言也跟着改：不能再是 "best first"。
  chk(/Closest to the centre first|Sorted by sharpness/.test(seg),
    '副标题说明了排序依据（最贴近中心的优先 / 否则按清晰度）');
  chk(!/best first/.test(seg.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')),
    '不再写 best first（会让人以为第一张就是最清晰的）');
  chk(/\$\{recNote\}|\$\{shownPasses\}/.test(seg),
    '副标题里带上了推荐条数与张数');
  chk(/passes_total/.test(seg), '用了后端给的 passes_total');
  chk(/\$\{t\('Showing'\)\} \$\{shownPasses\} \$\{t\('of'\)\} \$\{allPasses\} \$\{t\('pass\(es\) found\.'\)\}/.test(seg),
    '被 limit 截断时会说明"只显示 N / 共 M 趟"');
  chk(/\$\{esc\(t\(modeLabel\)\)\}/.test(seg), '副标题写明了当前档位名');
  // 边距限制也要在副标题里回显（否则看不出当前用的是哪一档）
  chk(/\$\{esc\(t\(insetLabel\)\)\}/.test(seg), '副标题写明了当前边距档位名');

  // 卡片上要显示"本趟时长"，好区分"专程拍"和"路过扫到"
  chk(/\$\{t\('this pass'\)\} \$\{Number\(h\.pass_seconds\)/.test(html),
    '卡片显示本趟时长（区分专程拍 / 路过扫到）');
}

console.log('\n=== 5) 后端按趟分组的常量与逻辑 ===');
{
  const api = fs.readFileSync(path.join(__dirname, 'Code', 'coverage_api.py'), 'utf8');
  chk(/FIND_PASS_GAP_SECONDS\s*=/.test(api), '有 FIND_PASS_GAP_SECONDS（趟间隔阈值）');
  chk(/FIND_DEDUP_SECONDS\s*=/.test(api), '有 FIND_DEDUP_SECONDS（相邻趟去重）');
  chk(/for grp in passes:/.test(api), '按 passes 分组后逐趟挑最优');
  chk(/best = min\(\(r for _, r in grp\), key=lambda r: r\["gsd"\]\)/.test(api),
    '每趟取该趟里 GSD 最好的那一帧');
  chk(/"pass_seconds"/.test(api) && /"pass_frames"/.test(api),
    '每条命中带 pass_seconds / pass_frames');
  chk(/"passes_total"/.test(api), '返回 passes_total');
  // 目标不能贴着画面边（用户 2026-10-13：「虽然理论上像素-实际物体大小的数值
  // 达到了最优，但因为目标在画面边上被切割，人看不出来是什么情况」）。
  // 用户先定 10%，看过之后定 **25%** 并要求做成可调选项。
  chk(/FIND_FRAME_INSET\s*=\s*0\.25/.test(api),
    '有边距限制，默认 25%（用户选定）');
  chk(/FIND_FRAME_INSET_MAX\s*=/.test(api), '有上限防呆（传太大要夹住）');
  chk(/abs\(xi\)\s*>\s*lim\s+or\s+abs\(yi\)\s*>\s*lim/.test(api),
    '判定用内缩后的限值（不是裸的 |xi|<=1）');
  chk(/"edge_margin"/.test(api), '每条命中带 edge_margin（供界面提示靠边）');
  // 可调：find_frames 要收 frame_inset 参数，且 0 不能被当成缺省
  chk(/frame_inset=None/.test(api), 'find_frames 接受 frame_inset 参数');
  chk(/FIND_FRAME_INSET if frame_inset is None else/.test(api),
    '0 是合法值（用 is None 判，不能被 `or` 吃掉）');
  // HTTP 路由也要透传（否则界面上的选项传不到后端）
  {
    const mgrPath = require('path').join(__dirname, 'Code', 'project_manager.py');
    const mgr = require('fs').readFileSync(mgrPath, 'utf8');
    chk(/frame_inset=frame_inset/.test(mgr), 'HTTP 路由把 inset 透传给 find_frames');
    chk(/params\.get\("inset"\)/.test(mgr), 'HTTP 路由读 inset 查询参数');
  }
  // 说明文案被拆成两个相邻字符串字面量（源码里跨行），所以匹配后半句
  chk(/border to read/.test(api) && /FIND_FRAME_INSET/.test(api),
    '若全部命中都贴边，如实说明原因（而不是假装没拍到）');

  // 优先推荐的两类（用户 2026-10-13）：「目标点至少要在这个红框区域内，
  // 就给优先推荐，另一个推荐的是'变焦且镜头覆盖'」。
  chk(/FIND_CENTRAL_MARGIN\s*=\s*0\.\d+/.test(api),
    '有"居中"的偏好阈值 FIND_CENTRAL_MARGIN');
  chk(/"category"/.test(api) && /"zoom_cover"/.test(api),
    '每条命中带 category / zoom_cover');
  chk(/central/.test(api) && /zoom_cover/.test(api) && /"none"/.test(api),
    '三类齐全：central / zoom_cover / none');
  // 关键：判"居中"要用 FIND_CENTRAL_MARGIN，不能用硬门槛 lim ——
  // 两者混用会让这一层排序完全失效（第一版就是这样，实测八个点全 central）。
  chk(/FIND_CENTRAL_MARGIN else "peripheral"/.test(api) ||
      /<= FIND_CENTRAL_MARGIN/.test(api),
    '用 FIND_CENTRAL_MARGIN 判居中（不是用门槛 lim）');
  chk(/h\["category"\] in \("central", "zoom_cover"\)/.test(api),
    'recommended = 两类推荐之一');
  // 排序键 = 类别 -> **离中心多近** -> 清晰度。
  // 用户 2026-10-13 第二版要求：「如果有大量帧包含目标点，那么优先跳转的应该是
  // '目标点最贴近画面中心、或者稍微更靠近的位置'」——
  // 所以"居中程度"必须是个**数值**参与排序，不能只是个分类布尔。
  chk(/"centre_offset"/.test(api), '每条命中带 centre_offset（离画面中心多远）');
  chk(/_rank\.get\(h\["category"\]/.test(api) && /h\["centre_offset"\]/.test(api),
    '排序 = 类别 -> 离中心多近 -> 清晰度');
  {
    // 居中程度必须排在清晰度**前面**，否则最清的贴边帧又会跑到第一位
    const iSort = api.indexOf('chosen.sort(key=lambda h: (_rank.get(');
    const seg = iSort < 0 ? '' : api.slice(iSort, iSort + 280);
    const iOff = seg.indexOf('centre_offset');
    const iGsd = seg.indexOf('ground_m_per_px');
    chk(iOff > 0 && iGsd > iOff,
      '离中心程度排在清晰度之前（这是用户要的优先级）',
      `offset@${iOff} gsd@${iGsd}`);
  }
  chk(/"recommended"/.test(api), '返回里带 recommended 统计');
  // 三档检索
  chk(/FIND_MODES\s*=\s*\(/.test(api), '有 FIND_MODES 三档定义');
  chk(/mode == "best"/.test(api) || /mode == 'best'/.test(api),
    'best 档：只取最清晰的 1 张');
  chk(/FIND_ANGLE_BEARING_DEG/.test(api) && /FIND_ANGLE_PITCH_DEG/.test(api),
    'angles 档：有方位/俯角去重阈值');
  chk(/bearing_elevation/.test(api), '用 bearing_elevation 算"从哪个方向看的"');
  // 必须用无人机->目标的几何，不能用相机 yaw（云台会独立转）
  chk(/不是相机 yaw|不用相机 yaw/.test(api),
    '注释写明了为什么不用 frame_yaw');
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
