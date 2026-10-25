// 分组勾选框的**行为**测试（真的执行页面里的函数，不是检查字符串）。
//
// 从 project_geojson_preview.html 里按标记取出两个纯函数：
//   iaGroupCheckState(type, items, isShown)  -> {checked, indeterminate, shown, total}
//   iaGroupClickPlan(isSingleLayer, checked) -> {mode:'hideAll'|'showFirst'|'setAll'}
// 然后在 Node 里用假数据跑，验证：
//   · 单图层组（正射/覆盖）：1/N 显示时是"已勾选"、**不出现半选**；点击 = 关掉整组
//   · 一条都没显示时点击 = 显示第一条
//   · 普通组仍是三态（全选/半选/未选）
//
// 为什么这样测：分组勾选框的 DOM 是 JS 现场生成的，纯静态断言只能证明
// "代码里出现了 if"，证明不了 1/N 时到底是不是半选（之前就是这么漏掉的）。

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

function extract(name) {
  const start = html.indexOf(`/* ${name}:start`);
  const end = html.indexOf(`/* ${name}:end`);
  if (start < 0 || end < 0) return null;
  const src = html.slice(html.indexOf('*/', start) + 2, end);
  // eslint-disable-next-line no-new-func
  return new Function(`${src}; return typeof ${name}==='function' ? ${name} : null;`)();
}

const checkState = extract('iaGroupCheckState');
const clickPlan = extract('iaGroupClickPlan');

console.log('\n=== 0) 两个纯函数能被取出来 ===');
chk(typeof checkState === 'function', 'iaGroupCheckState 可取并执行');
chk(typeof clickPlan === 'function', 'iaGroupClickPlan 可取并执行');

if (typeof checkState === 'function' && typeof clickPlan === 'function') {
  const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const shownOf = (set) => (it) => set.includes(it.id);

  console.log('\n=== 1) 单图层组：有任意一条显示 = 已勾选（不是半选）===');
  {
    const st1 = checkState('ortho', items, shownOf(['a']));
    chk(st1.checked === true, '1/3 显示 -> checked=true', JSON.stringify(st1));
    chk(st1.indeterminate === false, '1/3 显示 -> 不出现半选', JSON.stringify(st1));

    const st1c = checkState('coverage', items, shownOf(['b']));
    chk(st1c.checked === true && st1c.indeterminate === false, '覆盖组同样规则', JSON.stringify(st1c));

    const st2 = checkState('ortho', items, shownOf(['a', 'b']));
    chk(st2.checked === true && st2.indeterminate === false,
      '2/3 显示（旧项目遗留多 true）-> 仍是已勾选、不半选', JSON.stringify(st2));

    const st0 = checkState('ortho', items, shownOf([]));
    chk(st0.checked === false && st0.indeterminate === false,
      '0/3 -> 未勾选', JSON.stringify(st0));
  }

  console.log('\n=== 2) 单图层组：点击语义 ===');
  {
    const p1 = clickPlan(true, true);
    chk(p1.mode === 'hideAll', '已勾选时点击 -> 关掉整组', JSON.stringify(p1));

    const p2 = clickPlan(true, false);
    chk(p2.mode === 'showFirst', '未勾选时点击 -> 显示第一条', JSON.stringify(p2));

    // 组合起来看一整轮往返：显示 -> 点击 -> 隐藏 -> 点击 -> 再显示
    let shown = ['a'];
    const first = (plan) => {
      if (plan.mode === 'hideAll') shown = [];
      else if (plan.mode === 'showFirst') shown = ['a'];
      return checkState('ortho', items, shownOf(shown));
    };
    const s1 = first(clickPlan(true, checkState('ortho', items, shownOf(shown)).checked));
    chk(s1.checked === false, '一次点击后整组关闭（勾选框变未选）', JSON.stringify(s1));
    const s2 = first(clickPlan(true, s1.checked));
    chk(s2.checked === true, '再点一次又显示第一条（勾选框变已勾选）', JSON.stringify(s2));
  }

  console.log('\n=== 3) 普通组仍保持三态 ===');
  {
    const all = checkState('marker', items, shownOf(['a', 'b', 'c']));
    chk(all.checked === true && all.indeterminate === false, '3/3 -> 勾选', JSON.stringify(all));

    const some = checkState('marker', items, shownOf(['a']));
    chk(some.checked === false && some.indeterminate === true, '1/3 -> 半选', JSON.stringify(some));

    const none = checkState('video', items, shownOf([]));
    chk(none.checked === false && none.indeterminate === false, '0/3 -> 未选', JSON.stringify(none));

    chk(clickPlan(false, true).mode === 'setAll' && clickPlan(false, true).value === true,
      '普通组点击 -> 整组设为点击后的状态（开）');
    chk(clickPlan(false, false).value === false, '普通组点击 -> 整组设为点击后的状态（关）');
  }

  console.log('\n=== 4) 计数与过滤 ===');
  {
    const withMore = [{ id: 'a' }, { id: 'b' }, { id: 'more', more: true }];
    const st = checkState('photo', withMore, shownOf(['a']));
    chk(st.total === 2, '「显示更多」占位不参与总数', JSON.stringify(st));
    chk(st.shown === 1, '只统计真实行', JSON.stringify(st));
  }
}

console.log(`\n结果: ${ok ? '全部通过' : '有失败项'}`);
process.exit(ok ? 0 : 1);
