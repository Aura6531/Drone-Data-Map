// 图墙（Frames of this spot）挂在右栏的测试。
//
// 为什么单测"它在哪一栏"：
//   这个框原来是挂在中栏地图下面的，而中栏被地图、覆盖面板、点位详情挤满了 ——
//   结果就是**图墙出来了却看不到**（用户 2026-10-13：「框可以放到右下角，
//   不然太挤了我看不到」）。
//   这类"东西在、但看不见"的问题不会报错，只能靠结构断言钉住。

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'Code', 'project_geojson_preview.html'), 'utf8');

let ok = true;
const chk = (c, label, extra = '') => {
  ok = ok && !!c;
  console.log(`  ${c ? '[OK]' : '[FAIL]'} ${label}${extra ? ' -> ' + extra : ''}`);
};

console.log('=== 1) 图墙元素只存在一个 ===');
{
  const n = (html.match(/id="frameGallery"/g) || []).length;
  chk(n === 1, 'id="frameGallery" 只出现一次（移动时没漏删旧的）', String(n));
}

console.log('\n=== 2) 它挂在右栏里，不在中栏 ===');
{
  const iRight = html.indexOf('id="colRight"');
  const iGallery = html.indexOf('id="frameGallery"');
  const iRightEnd = html.indexOf('id="keyModal"');   // 右栏之后的下一个顶层块
  chk(iRight > 0 && iGallery > iRight, 'frameGallery 在 colRight 之后',
    `colRight@${iRight} gallery@${iGallery}`);
  chk(iRightEnd > iGallery, 'frameGallery 在 colRight 结束之前（确实在里面）',
    `gallery@${iGallery} 右栏之后@${iRightEnd}`);

  // 中栏里不该再有它：中栏是 mapCard / 统计 / 覆盖面板那一段
  const iMapCol = html.indexOf('id="map"');
  const iBelowMapEnd = html.indexOf('id="colRight"');
  const midSection = html.slice(iMapCol, iBelowMapEnd);
  chk(midSection.indexOf('id="frameGallery"') < 0,
    '中栏（地图那一段）里已经没有图墙了');
}

console.log('\n=== 3) 右栏里要能占满剩余高度、自己滚 ===');
{
  // 取 .col-right .frame-gallery 那条规则
  const m = html.match(/\.col-right \.frame-gallery\{([^}]*)\}/);
  chk(!!m, '有 .col-right .frame-gallery 规则');
  if (m) {
    const css = m[1].replace(/\s+/g, ' ');
    chk(/flex:\s*1/.test(css), 'flex:1 —— 吃掉视频剩下的高度', css.slice(0, 70));
    chk(/min-height/.test(css), '有 min-height 兜底（视频很长时不被压没）');
    chk(/max-height:\s*none/.test(css),
      '覆盖掉中栏那套 max-height:430px（否则下面还是空一块）');
  }
  // 卡片区自己滚，标题和「更多」按钮才不会被顶走
  const g = html.match(/\.col-right \.frame-gallery \.grid\{([^}]*)\}/);
  chk(!!g, '有 .col-right .frame-gallery .grid 规则');
  if (g) {
    const css = g[1].replace(/\s+/g, ' ');
    chk(/overflow:\s*auto/.test(css), '卡片区自己滚', css.slice(0, 80));
    chk(/align-content:\s*start/.test(css), '卡片从顶部排（不被拉伸分布）');
  }
}

console.log('\n=== 4) 页面脚本仍能找到它（移动后 id 没断） ===');
{
  // 脚本里是按 id 取的，移动位置不影响；这里确认取法没被改成依赖父节点
  const m = html.match(/function frameGalleryEl\(\)\{([^}]*)\}/);
  chk(!!m, 'frameGalleryEl 还在');
  if (m) {
    chk(/getElementById\('frameGallery'\)/.test(m[1]),
      '仍然按 id 取（不依赖它在哪一栏）', m[1].trim());
  }
  const appends = (html.match(/getElementById\('frameGrid'\)/g) || []).length;
  chk(appends >= 2, '渲染与 debug 都按 id 取 frameGrid（两边一致）', String(appends));
}

console.log('\n结果:', ok ? '全部通过' : '有失败项');
process.exit(ok ? 0 : 1);
