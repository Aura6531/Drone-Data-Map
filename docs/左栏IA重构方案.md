# 左栏信息架构重构方案（概念稿 · 未改代码）

> 目标：把左栏从「项目 / 数据文件 / 已加载」三个互相重叠的区块，
> 改成「**项目 → 数据来源 → 内容（含地图显隐）**」一条线。
> 原始文件永远留在原路径，项目只登记"哪些磁盘目录属于我"，并维护一份可重建的索引。

---

## 0. 一句话结论

- **数据来源（source）= 项目登记的本机任意目录**（可跨盘、可多个），只存路径与索引元数据；
- **内容（item）= 从来源里扫出来的东西**（视频 / 照片 / 正射影像 / KML / 生成的 SRT·GeoJSON）；
- **地图显隐是内容的一条属性**，不再是一个独立的"已加载"区块；
- 三个动作彻底分开：**登记来源 → 建立/刷新索引 → 显示到地图**（当前这三件事被混叫"加载"）。

---

## 1. 现状盘点（基于代码实测）

### 1.1 数据模型（`Project/<项目名>/project.json`）

```
{
  "name": "东莞地铁",
  "version": 1,
  "folders": [                      ← 数据来源（目前直接用"路径"当主键）
    { "name": "【批量压缩】全景上传 …",
      "path": "A:\\DeepSeek Test\\Data\\360全景照片\\【批量压缩】…",
      "file_count": 150, "mp4_count": 0, "srt_count": 0,
      "jpg_count": 150, "other_count": 0, "total_size": 5208838144,
      "files": [ {name, extension, size, relative_path}, … ]   ← 登记时的一次快照
    }
  ],
  "tracks": [...], "videos": {...}, "photos": {...},
  "markers": [...], "labels": [...], "vectors": [...],
  "ui": { "videos":{}, "photos":{}, "markers":{}, "ortho":{}, "coverage":{}, … }
}
```

### 1.2 安全边界（已经做好、必须保住的部分）

| 能力 | 位置 | 现状 | 结论 |
|---|---|---|---|
| 只扫用户明确加入的目录 | `scan_folder()` `project_manager.py:585` | `folder.rglob("*")`，参数是**用户传入的单个目录** | ✅ 可复用 |
| 列目录只允许登记目录内 | `/api/project/tree` `8389` | 先取 `project.folders` 作为 `roots`，再 `target.relative_to(r)` 校验 | ✅ 可复用（核心安全阀） |
| 删文件只允许登记目录内 | `/api/project/delete-files` `8859` | 校验 `roots` + 扩展名白名单 `.mp4/.mov/.osv/.jpg/.jpeg/.png` | ✅ 可复用 |
| 全量列 GeoJSON | `list_project_geojson()` `3206` | 只遍历 `project.folders` | ✅ 不会扫整机 |
| 照片索引 | `analyze_project_media()` `1122` | 只遍历 `project.folders` | ✅ |
| 文件夹选择器 | `select_folders_windows()` `693` + `clean_selected_folders()` `667` | 支持 **Ctrl 多选**、去掉空值/重复/不存在的目录 | ✅ 可复用 |
| 登记来源 | `POST` 分支 `add_folder()` `9328` | 按 `path.casefold()` 去重后追加，**不复制文件** | ⚠️ 需补"来源 id" |

**结论：不会误删原始文件、不会默认扫描未登记目录 —— 这两条现在就是成立的，重构不能破坏它们。**

### 1.3 现有缺陷（本次要解决的）

1. **概念混叠**：`数据文件`（磁盘树）与 `已加载`（图层清单）是同一批文件的两种视角，
   用户要在两处找同一个视频；"加载"一词同时指"登记""生成""上图"。
2. **来源没有身份**：`folders[]` 用 `path` 当主键。移动目录 / 换盘符 = 来源丢失，只能重新登记。
3. **索引是隐式的**：`files[]` 是登记那一刻的快照，之后再没更新；
   而 `list_project_geojson()` 又是**每次调用实时 `rglob`** ——
   大目录（190 张照片 / 150 张全景）每次打开面板都扫盘，且"索引时间"无从展示。
4. **状态无处表达**：现在只能看出"文件在不在列表里"，看不出
   「未处理 / 已生成 / 缺 SRT / 已过期 / 来源离线」。
5. **显隐 key 不稳定**：`ui.markers` 用**名字**、`ui.ortho` 用**文件名**、
   `ui.videos` 用路径 —— 一旦改名或多来源同名，状态会错位。

---

## 2. 目标信息架构

```
左栏
├─ ① 项目  ────────────────────────────────
│    [ 东莞地铁 ▾ ]            [新建] [⋯]
│    来源 3 个 · 内容 214 项 · 索引 2 分钟前
│
├─ ② 数据来源（Sources） ───────────────────
│    ＋ 添加来源…                     ↻ 全部刷新
│    ▸ A:\…\360全景照片      150 张   ✓ 在线   2 分钟前
│    ▸ D:\项目部\东莞地铁     12 个视频 ✓ 在线  5 分钟前
│    ▸ E:\外业\0918（已离线） ⚠ 找不到   [重新定位] [移除]
│
└─ ③ 内容（Contents） ─────────────────────
     搜索 [            ]   筛选 [全部类型 ▾] [只看有问题的]
     ▾ 视频 (12)                    全选 ○  ⋯
        ☑ 🎬 DJI_…0001_V.MP4  [D:\项目部]  4K  · 已生成  ⤢ ✎ ×
     ▾ 照片 (190)  …
     ▾ 正射影像 (1) …
     ▾ KML / 矢量 (0) …
     ▾ 位置点 (11) / 文字标注 (2)   ← 项目自有的标注类，无来源
```

### 2.1 三个区块的职责（不许重叠）

| 区块 | 回答的问题 | 数据来源 | 允许的写操作 |
|---|---|---|---|
| ① 项目 | "我现在在哪个项目 / 怎么管理项目" | `/api/project/list` · `/api/project/get` | 新建、切换、重命名、导出、移除登记（不删数据） |
| ② 数据来源 | "这个项目看的是哪些磁盘目录" | `project.folders` | 添加、刷新索引、重定位、移除关联、在资源管理器打开 |
| ③ 内容 | "这里面有什么 / 能不能上图 / 能不能用" | 索引 + 生成物 + 标注 | 勾显隐、定位、生成/重建、重命名、移除、删除生成物 |

---

## 3. 按钮清单（同一动作只有一种叫法）

### 3.1 项目区

| 按钮 | 语义 | 触发 | 影响磁盘 |
|---|---|---|---|
| 新建项目 | 建立项目空壳（只建 `Project/<名>/project.json`） | 弹窗输入名字 | 只建元数据 |
| 切换项目 | 换当前项目 | 下拉 | 无 |
| 项目设置 ⋯ | 重命名 / 复制 / 导出 / 备份 | 菜单 | 无 |
| 移出项目列表 | 从列表移除该项目（保留项目目录） | 居中确认 | **不删数据** |

### 3.2 数据来源区

| 按钮 | 语义 | 后端 | 影响磁盘 |
|---|---|---|---|
| **添加来源…** | 调用 Windows 文件夹选择器（可 Ctrl 多选），把目录**登记**进项目 | `POST /api/project/add-folder`（复用 `select_folders_windows`） | 只读扫描、写 `project.json` |
| **刷新索引**（单个来源 ↻） | 重新扫描该来源，更新文件清单与状态 | 新增 `POST /api/project/source/reindex` | 只读 |
| **全部刷新** | 依次刷新所有在线来源 | 同上（批量） | 只读 |
| **重新定位…** | 来源离线时重新指定它的新路径（保留来源 id 与已有生成物关联） | 新增 `POST /api/project/source/relocate` | 只读 + 写元数据 |
| **移除**（解除关联） | 把来源从项目里摘掉；**可选**同时删掉"本程序生成的 SRT/GeoJSON" | 新增 `POST /api/project/source/detach`（带 `delete_generated:false` 默认） | 默认不删任何文件 |
| 在资源管理器中打开 | 只读跳转 | 前端 `explorer.exe` 由后端 `os.startfile` | 无 |

### 3.3 内容区（每个条目 / 每个分组）

| 操作 | 位置 | 语义 | 影响磁盘 |
|---|---|---|---|
| 勾选框 | 行首 | **地图显隐**（唯一含义） | 无（写 `ui`） |
| 定位 ⤢ | 行尾图标 | 飞到该条目的位置（视频→航迹起点、照片→拍摄点、正射→范围中心） | 无 |
| 编辑 ✎ | 行尾图标 | 改名 / 改分类 / 改文字（仅标注类） | 无 |
| 移除 × | 行尾图标 | 从内容清单移除（=取消上图），文件不动 | 无 |
| **生成** / **重新生成** | 分组头 or 行内文字按钮 | 生成 SRT → GeoJSON（→ 正射金字塔） | **只写生成物**，媒体不动 |
| 同步检查 / 修复 | 分组头 | 视频时长 vs SRT 时长比对 | 只读报告 |
| 删除生成物… | 行尾 ⋯ 菜单 | 删除该视频的 SRT / GeoJSON（红色确认） | **只删生成物** |
| 删除原始文件… | 行尾 ⋯ 菜单 | 删媒体文件（默认关闭、双重确认、只在来源目录内） | 破坏性 |

> 命名规范（全文统一）：
> **登记**（add source） ≠ **建立索引**（index） ≠ **生成**（generate） ≠ **上图**（show on map） ≠ **定位**（fly to）。
> 界面上任何"加载"字样都要拆成上面 5 个词之一。

---

## 4. 状态设计

### 4.1 来源级（② 区每行右侧一枚状态徽标）

| 状态 | 徽标 | 颜色 | 判据 | 可执行动作 |
|---|---|---|---|---|
| 在线 | ✓ 在线 | 绿 | 路径存在且可读 | 刷新索引、移除 |
| 索引中 | ⟳ 扫描中… | 蓝（转） | 正在 `rglob` | 取消 |
| 已离线 | ⚠ 找不到 | 橙 | 路径不存在 | 重新定位、移除 |
| 无权限 | ⚠ 无法读取 | 橙 | `PermissionError` | 重新定位 |
| 未建索引 | ○ 未扫描 | 灰 | `indexed_at` 为空 | 刷新索引 |

### 4.2 内容项级（③ 区每行）

处理状态（与显隐勾选**分开表达**）：

| 状态 | 文案 | 颜色 | 说明 |
|---|---|---|---|
| 原始可用 | （不显示） | — | 只有媒体，没什么要生成的 |
| 待生成 | 待生成 | 灰 | 有 MP4，无 SRT/GeoJSON |
| 生成中 | 生成中 38% | 蓝 | 后端任务 |
| 可用 | 已生成 | 绿 | SRT + GeoJSON 齐 |
| 已过期 | 已过期 | 橙 | 视频 mtime 比 GeoJSON 新（重录/替换过） |
| 缺失 | 缺 SRT / 缺 GeoJSON | 红 | 被外部删掉 |
| 不可用 | 无法读取 | 红 | 权限/损坏 |

显隐状态：行首勾选框（三态：全选 / 半选 / 未选），只写 `ui`。

### 4.3 `ui` 状态键的迁移（避免改名/同名错位）

现在：`ui.markers[名字]`、`ui.ortho[文件名]`、`ui.videos[路径]`。
建议：统一为 **`ui.items[itemId]`**，`itemId = "<sourceId>:<relativePath>"`（标注类用 `marker:<id>`），
读取时做一次"旧键 → 新键"映射迁移。

---

## 5. 典型流程

### 流程 A：新建项目 + 登记两个不同磁盘的来源

1. `新建项目` → 输入「东莞地铁」
2. ② 区 `添加来源…` → 资源管理器弹出 → Ctrl 选中 `D:\项目部\0918` 与 `E:\外业\0920` → 确定
3. 后端只做**只读扫描**：写 `folders[{id, path, name, indexed_at, counts}]`，不复制任何文件
4. ② 区出现两行，状态「⟳ 扫描中 → ✓ 在线（12 个视频 / 150 张照片）」
5. ③ 区自动出现分组：视频 / 照片 / 正射 / KML；行尾状态「待生成」
6. 日志栏两行：「已登记 2 个来源」「索引完成：12 个视频、150 张照片」

### 流程 B：已经有视频，但没航迹

1. ③ 区 `视频` 分组显示「待生成 12」
2. 点分组头 `生成`（或行内 `生成`）→ 后端逐条 SRT → GeoJSON
3. 进度写日志栏（`生成中 3/12`），行尾状态变「生成中 → 已生成」
4. 完成后勾选该行 → 地图出现航迹；点 ⤢ 定位

### 流程 C：只想看某一张照片

1. ③ 区照片分组 → 该行 `定位 ⤢`
2. 地图飞到拍摄点并闪一下虚线圆（已实现）
3. 右侧出图；地图**不**因此铺开全部照片点（只有勾选才铺）

### 流程 D：移除一个来源（不删文件）

1. ② 区该来源 `移除`
2. 居中弹窗：「只从项目解除关联，磁盘文件不动」+（可选勾选）「同时删除本程序生成的 SRT / GeoJSON」
3. 默认不勾 → 只改 `project.json`
4. ③ 区该来源的内容消失；日志「已解除关联：E:\外业\0920」

### 流程 E：外接硬盘没插

1. 打开项目 → ② 区该来源显示「⚠ 找不到」
2. ③ 区该来源的内容变为灰色（保留位置，不上图）
3. 插上硬盘 → `刷新索引` 恢复正常；或 `重新定位…` 指到新盘符

---

## 6. 后端：可复用 / 需新增

### 6.1 直接复用（不改）

- `select_folders_windows()`（多选对话框）、`clean_selected_folders()`（去空/去重/只留真实目录）
- `/api/project/tree` 的**根目录白名单校验**（`relative_to(roots)`）
- `/api/project/delete-files` 的**来源内 + 扩展名白名单**双重校验
- `load_project()` / `save_project()`（含项目名校验 `validate_project_name`）
- `/api/project/sync-check`、`/api/project/geojson-list`、`/api/project/photos`

### 6.2 需要调整 / 新增

| # | 需求 | 现状 | 方案 |
|---|---|---|---|
| 1 | 来源要有稳定身份 | `folders[]` 用 path 当主键 | 增加 `id`（uuid4）；path 只作 locator。`ui` 键、生成物关联全部改用 id |
| 2 | 索引要显式、可展示 | `files[]` 只在登记时生成；`list_project_geojson` 每次实时 `rglob` | 增加 `indexed_at` / `scan_ms` / `counts`；`geojson-list`、`tree` 优先读索引（含 mtime 失效判断），避免每次打开面板扫盘 |
| 3 | 来源健康检查 | 无 | `GET /api/project/sources` 返回每个来源 `exists/readable/indexed_at/counts` |
| 4 | 重新定位 | 无 | `POST /api/project/source/relocate {source_id, new_path}`：校验新路径存在 → 迁移 `path`，保留 id 与生成物关联 |
| 5 | 解除关联 | 只有"删项目"（`delete_project` 9120）和"删文件" | `POST /api/project/source/detach {source_id, delete_generated:false}`：默认只移出 `folders` |
| 6 | 生成物与来源的归属 | 生成物写在来源目录内，靠相对路径猜 | 索引里记录 `generated: {srt, geojson, geo3d}`，删除/重建都以索引为准 |
| 7 | 过期判定 | 无 | 比较 `video.mtime` 与 `geojson.mtime`，写入索引状态 |
| 8 | 大目录性能 | `rglob` 全量 | 索引化 + 分页/懒加载（已有一层懒加载的 tree 可复用） |
| 9 | 迁移 | `ui` 老键 | 一次性迁移脚本：旧 `ui.videos/photos/markers/ortho` → `ui.items`，保留旧键只读兼容一个版本 |

### 6.3 安全红线（写进代码注释与测试）

1. 任何扫描入口的根，**只能来自 `project.folders[].path`**；接口不接受"任意路径扫描"。
2. 任何写/删入口，必须 `Path(target).resolve()` 后 `relative_to(source.path)` 校验通过。
3. `detach` 默认 `delete_generated:false`；`delete-files` 只允许媒体扩展名且必须显式勾选。
4. 删除一律走居中弹窗 + 二次确认（已是现状）。
5. 目录不存在 / 无权限 → 只报状态，**不自动重试、不递归到父目录**。

---

## 7. 分期落地计划（2026-10-25 修订：P1a 已完成，后续从 P1b 开始）

| 阶段 | 内容 | 交付物 | 风险 |
|---|---|---|---|
| P1 | 数据模型：`source.id`、`indexed_at`、`ui.items` 迁移；新增 `GET /sources`、`POST /source/relocate`、`/source/detach` | 兼容旧 `project.json`（读到旧数据自动补 id） | 中（涉及 state 迁移） |
| P2 | 左栏三段重构（② 来源清单 + ③ 内容合并清单），保留旧 DOM 隐藏一版 | 新 IA 可用，旧入口并存 | 低 |
| P3 | 索引化：`tree` / `geojson-list` 读索引，加"刷新索引"与过期判定 | 大目录不再每次扫盘 | 中 |
| P4 | 清理：删除旧「数据文件/已加载」重复入口、迁移日志与测试 | 单一数据入口 | 低 |

> 每阶段都必须满足：`node run_tests.js` **不退化为 40/40 以下**、`check_page.js` 全绿、
> `project.json` 双向兼容（旧项目能读，新项目旧版也能读）。

### 进度

| 阶段 | 状态 | 提交 | 内容 |
|---|---|---|---|
| **P0** | ✅ 完成 | `661d8e7` | 方案 + 五个实现边界（reindex / relocate / 重叠 / 过期模型 / 基线） |
| **P1a** | ✅ 完成 | `a1e4672` | `source_id_for_path()` / `ensure_source_ids()`（内存补、稳定推导）、`save_project()` 原子写、`GET /api/project/sources`、`test_sources.py` |
| **P1b** | ✅ 完成 | `edfd049` | 内容身份 `itemId`（`it_` 真实 / `ip_` 临时）+ `ui.items` 迁移；`GET /api/project/ui-items`、`POST /api/project/ui-migrate`；`test_ui_items.py` |
| **P1c** | ✅ 完成 | 见下 | `POST /source/reindex`（单/全）、`POST /source/relocate`（预检 + 确认）、`POST /source/detach`（默认只解除关联）；`test_source_ops.py` |
| **P2** | ⬜ 待做 | — | 左栏三段式上线；新界面接管流程，旧 DOM 隐藏保留（不同时展示） |
| **P3** | ⬜ 待做 | — | 索引化：`indexed_at` + 读索引，去掉每次 `rglob`；接入过期模型 |
| **P4** | ⬜ 待做 | — | 清理旧 DOM / 旧代码（等新界面通过实际流程验证后） |

> 2026-10-25 明确：**暂不实施 reindex / relocate / 左栏改版**，先把测试清理做干净。

---

## 8. 与现状的差异一览（便于评审）

| 维度 | 现在 | 方案 |
|---|---|---|
| 区块 | 项目 / 数据文件 / 已加载（三者重叠） | 项目 / 数据来源 / 内容（职责单一） |
| 来源身份 | 路径 | `source.id` + 路径（可重定位） |
| 索引 | 登记时快照 + 每次实时扫 | 显式索引（`indexed_at`、可刷新、可过期） |
| 状态 | 只有"在不在列表里" | 来源健康 + 处理状态 + 显隐，三套独立 |
| 动作词 | 都叫"加载" | 登记 / 建索引 / 生成 / 上图 / 定位，各归其位 |
| 删除 | 只有删文件 | 默认只有"移除关联"；删生成物、删媒体分级 |
| 跨盘多来源 | 能力有，但 UI 看不出"这条来自哪个盘" | 每行带来源徽标，② 区集中管理 |

---

## 9. 已确认的决策（2026-10-25）

1. **旧 project.json 自动补来源 id：可以。**
   - 读取时只在**内存**里补齐；第一次明确保存时才写回；
   - 保存采用**原子写**（临时文件 + os.replace），已落地；
   - 补 id 必须**稳定**：由 sha1(normcase(resolve(path))) 推导（src_xxxxxxxxxxxx），
     同一路径每次读都得到同一个 id，**不能用随机 uuid**（否则显隐状态/生成物归属每次都会错位）。
2. **旧界面：保留一版回退能力，但不与新界面同时可操作。**
   - 新界面先接管用户流程；旧「数据文件 / 已加载」DOM 隐藏保留，作为短期回退；
   - 数据与 API 的兼容**保留更久**，等新界面通过实际流程验证后再清理旧 DOM 与代码。
3. **移除来源：初版只解除关联。**
   - 「同时删除本程序生成物」这个选项**初版默认不提供/不勾选**；
   - 等来源 id、生成物归属、安全边界都验证可靠后再加，并且确认框要**列出将删除的文件与数量**；
   - 删除范围严格限定：**本程序生成、且位于该来源目录内**的 SRT / GeoJSON 等，
     原始视频、照片与其他文件一律不碰。

### 已实现（P1a，2026-10-25）

| 项 | 状态 |
|---|---|
| source_id_for_path() / ensure_source_ids() | ✅ project_manager.py |
| load_project() 内存补 id（不写盘） | ✅ |
| save_project() 原子写（tmp + fsync + os.replace） | ✅ |
| GET /api/project/sources | ✅ 返回 id / 路径 / 在线状态 / 计数 |
| 测试 Code/test_sources.py | ✅ 6 组断言，已登记进 
un_tests.js |

---

## 10. 实现边界（P1 开工前定稿）

> 本节回应 2026-10-25 提出的五个边界问题。所有接口都以「只读扫描 + 只写 project.json」为原则，
> 任何写/删都必须先过 `resolve()` + `relative_to(source.path)` 的校验。

### 10.1 索引刷新（reindex）：单来源 + 全部

| 接口 | 用途 | 说明 |
|---|---|---|
| `POST /api/project/source/reindex` | 刷新**一个**来源 | body: `{project_name, source_id}` |
| `POST /api/project/sources/reindex` | 刷新**全部**（或指定若干） | body: `{project_name, source_ids?: []}`；省略 = 所有在线来源 |

**执行模型**：初版**同步**执行（`rglob` + `stat`，实测 150 个文件约 30~80 ms），
返回里带 `duration_ms`；单个来源文件数 > 5000 或耗时 > 2 s 时，前端显示「扫描中…」并允许继续操作，
后端按 `source_id` 加互斥锁，第二个并发请求直接返回 `{"skipped": "already running"}`。

**返回结构**

```json
{
  "success": true,
  "duration_ms": 74,
  "sources": [
    {
      "id": "src_bd464df53aaa",
      "path": "A:\\…\\360全景照片",
      "status": "ok",                  // ok | missing | denied | partial | timeout
      "indexed_at": "2026-10-25T10:41:00",
      "counts": {"files":150,"mp4":0,"srt":0,"jpg":150,"other":0,"bytes":5208838144},
      "warnings": [{"path":"…\\子目录","error":"PermissionError"}]
    }
  ]
}
```

**失败状态语义**

| status | 判据 | UI | 是否写回索引 |
|---|---|---|---|
| `ok` | 全部可读 | ✓ 索引于 xx | 是 |
| `partial` | 部分子目录 `PermissionError`/`OSError` | ⚠ 部分不可读（N 项） | 是（只写读到的） |
| `missing` | 根目录不存在 | ⚠ 找不到 | **否**（保留旧索引，标 `missing`） |
| `denied` | 根目录 `PermissionError` | ⚠ 无法读取 | 否 |
| `timeout` | 超过 30 s | ⚠ 扫描超时，可重试 | 否 |

> 失败时**绝不删除**已有索引条目 —— 否则插错盘/断网就会把清单清空。

### 10.2 来源重定位（relocate）：先给匹配报告，再确认

不能因为「id 还在」就认定是原数据。两步式：

**第一步：预检（不写盘）**

`POST /api/project/source/relocate` `{project_name, source_id, new_path, confirm: false}`

```json
{
  "success": true,
  "verdict": "likely",             // same | likely | different
  "old_count": 150,
  "new_count": 148,
  "matched": 147,                  // 相对路径完全相同的文件数
  "missing": ["DJI_…0003_V.JPG"],
  "added":   ["DJI_…0151_V.JPG"],
  "match_ratio": 0.98,
  "affects": {"generated_kept": 12, "generated_orphan": 1}
}
```

判定规则（相对路径集合比较，大小写不敏感）：

- `same`：`match_ratio ≥ 0.90` 且新增 ≤ 10%
- `likely`：`match_ratio ≥ 0.50`
- `different`：其它

**第二步：确认**

`confirm: true` 时才真正改写 `path` / `name`：

- **保留 `id`**（这样 `ui` 显隐、生成物关联都不丢）；
- 生成物按**相对路径**重新绑定：仍存在的 → `kept`；找不到的 → 标 `orphan`（不移除记录、不删文件）；
- `verdict === "different"` 时前端**必须**弹确认框：「新目录内容与原来差异较大（匹配 12%），
  仍要把它当作该来源的新位置吗？」，并列出 missing/added 各前 5 条；
- 全过程**不移动、不复制、不删除任何文件**。

### 10.3 来源目录重叠：允许登记，内容按真实文件去重

父目录 + 子目录同时登记是正常需求（例：先加 `D:\项目部`，后加 `D:\项目部\0918`），
所以**不禁止重叠**，但内容清单必须去重：

- **去重键**：`os.path.normcase(os.path.realpath(file))`（`realpath` 能把 junction/软链接指到同一真实文件）
- 每个内容项记录 `sources: [sourceId, …]`，**主来源** = 路径最短（层级最高）的那个；
  行内显示「D:\项目部 ·也被 0918 包含」
- 生成 / 删除 / 重命名等写操作**只对主来源执行一次**，其余来源只是引用
- 同一路径重复登记仍然拒绝（现有 `add_folder` 已去重）
- 登记时若检测到父子关系，给一条**非阻塞提示**：「该目录包含已登记的 0918（或反之），
  重叠的 N 个文件只会出现一次」。初版只提示，不自动合并/拆分。

### 10.4 过期与失效：不止 mtime

只比「视频 mtime vs GeoJSON mtime」会漏掉：外部替换 SRT、生成参数变了、生成物损坏。
所以索引里为每个视频记一份 **fingerprint**：

```json
"gen": {
  "video": {"size": 123456789, "mtime_ns": 1710000000000000000},
  "srt":   {"size": 45678,     "mtime_ns": 1710000000000000000},
  "geojson": {"size": 98765,   "mtime_ns": 1710000000000000000,
              "digest": "sha1:…"},          // 仅 reindex/手动校验时计算
  "params_digest": "sha1:…",                // 合并策略 / 高度基准 / 采样间隔等
  "schema": 2
}
```

**状态推导（按优先级）**

| 状态 | 判据 | UI | 建议动作 |
|---|---|---|---|
| `missing` | 生成物文件不存在 | 缺 GeoJSON / 缺 SRT | 生成 |
| `stale_input` | 视频或 SRT 的 (size,mtime_ns) 与记录不符 | 已过期（源已变） | 重新生成 |
| `stale_params` | `params_digest` 变化 | 已过期（参数已变） | 重新生成 |
| `corrupt` | `digest` 不符或 JSON 解析失败 | 生成物损坏 | 重新生成 |
| `unknown` | 旧索引没有 fingerprint | 未校验 | 重建索引一次 |
| `ok` | 以上都不成立 | 已生成 | — |

- 日常读取只做**轻量校验**（size + mtime_ns），不算 sha1；
- 只在 `reindex` 或用户点「校验」时算 `digest`；
- `schema` 升级时，旧条目统一标 `unknown`，不猜。

### 10.5 测试基线（2026-10-25 复核，现已全绿）

```
命令：node run_tests.js            （PYTHON=DSH 自带 python）
套件：40 套
结果：40 通过 / 0 失败
```

复核前的状态是 **36/38**，两套失败都不是环境问题，已逐个查清并修复：

| 套件 | 真实原因 | 性质 | 修法 |
|---|---|---|---|
| `test_photos.js` | 5 组断言仍在找**已删除**的 `#photoLayerBtn`、`#loadAllBtn`、`#filterDate/#filterType`、`#markerCard`、`photoLayerCount`；遥测实测写死 `folder_index: 0`（加了 360 照片目录后视频变成 index 2） | **断言过期** | 改写成验证现行界面：左栏「已加载 → 照片」勾选 = 唯一开关、点名称 = 打开并缩放到全部照片、`__photoToggle` 代码入口；遥测改为先查 `geojson-list` + `tree` 找到真实 MP4 再拼参数 |
| `test_report.py` | 抽帧样本取 `videos[0]`（字母序第一支）——Data/ 现在多了 360 全景转码 `2048×1024`，于是「原分辨率 ≥1080p」「A4 会缩小」「标志 ≈1.55 倍」三条假设全部失效 | **测试选片假设过期**（产品行为正确：full 不缩放；A4 一律缩放到 2480 宽，含有意放大） | 样本优先 `*_V.MP4`（3840×2160）；压缩档高度改成**精确等比**；标志比例对着「full 宽 / 2480」理论值（±0.1）；另补一条明确断言「窄素材进 A4 也会被放大到 2480」 |

> 结论：**基线 = 40/40**。后续任何改动都不允许低于这个数字；
> `check_page.js` 必须全绿。

---

## 10.6 内容身份（`itemId`）与重叠来源

> 本节定的是 **P1b 的数据键**：在「父子目录可同时登记、内容按真实文件去重」的前提下，
> 一个内容项的身份如何保持稳定 —— 尤其是「主来源被移除」和「来源重定位」这两种情况，
> 不能让图层的勾选状态丢失或重置。

### 10.6.1 身份公式：按**真实文件**取，不按来源取

```
itemId = "it_" + sha1(normcase(realpath(绝对路径)))[:12]
```

- `realpath` 会把 junction / 软链接 / 大小写差异归一到同一个真实文件；
- 同一个文件被父目录与子目录**同时包含**时，两者的 `realpath` 相同 → **同一个 `itemId`**，
  这就是 10.3 里「按真实文件去重」的落地方式；
- 两个不同目录里恰好有**同名同相对路径**的两个文件 → `realpath` 不同 → 两个 `itemId`，互不影响。

### 10.6.2 索引是 id 的来源，实时计算只是兜底

- **扫描（reindex）时**把 `itemId` 连同 `relativePath`、`size`、`mtime_ns` 写进该来源的索引；
- 来源**离线**时直接用索引里存的 `itemId`，不需要访问磁盘；
- 只有在「索引里没有」时才现算一次（并写回索引）。

### 10.6.3 `ui.items` 与「主来源」解耦

- 图层显隐一律记在 `ui.items[itemId]`，**不记在来源上**；
- 「主来源（primary）」只决定**写操作落在哪个目录**（生成物写哪里、删除删哪份），
  规则：路径最短（层级最高）者为 primary，并列时按 `sourceId` 字典序；
- 因此：
  - **主来源被移除** → 次短来源自动接管 primary，`itemId` 不变，**显隐状态原样保留**；
  - 移除一个「非主」来源 → 内容仍在清单里（只是少了一个引用），显隐不变；
  - 所有包含它的来源都被移除 → 条目从清单消失，但 `ui.items[itemId]` **保留为孤儿键**
    （重新登记回来时状态自动恢复）；reindex 报告里给出「孤儿状态 N 条」，
    并提供显式清理按钮（默认不清）。

### 10.6.4 重定位（relocate）必须迁移 id

`realpath` 变了（换盘符、移动目录）→ `itemId` 也会变。所以 relocate **不是**「只改 path」，
必须做一次键迁移，步骤（与 10.2 的两步预检合并）：

1. 预检得到 `matched`：相对路径集合的交集（old → new 一一对应）；
2. `confirm:true` 生效时：
   - `ui.items[newId] = ui.items[oldId]`（**新键已存在则不覆盖**）；
   - 旧键**按下面「旧键的删除条件」处理**（可能删、也可能保留，不能无条件删）；
   - `generated` 归属按相对路径重绑（找不到的标 `orphan`）；
3. 预检报告里给三个数：`ui_keys_migrated` / `ui_keys_shared` / `ui_keys_unmatched`，
   确认框上写明「迁移 N 条 / 共用 M 条（其它来源仍引用，旧键保留）/ K 条在新目录找不到（保留为孤儿）」。

> 例外：若新路径 `realpath` 与旧路径相同（只是换了大小写/走 junction），
> `itemId` 天然不变，`ui_keys_migrated` 为 0。

**旧键的删除条件（重叠来源时会踩）**：父子来源可能同时包含同一个文件。
重定位其中一个来源后，新路径产生新 `itemId`，但**另一个来源仍引用原路径** ——
此时旧键不能删，否则没被移动的那个来源会丢显隐。规则：

- 迁移前先查：`oldId` 是否仍被**其它来源的索引**引用（任一来源里存在 `itemId == oldId` 的条目）；
- **仍被引用** → 新旧键**同时保留**同样的状态值（`ui.items[newId] = ui.items[oldId]`，旧键不动），
  预检报告多给一个 `ui_keys_shared: N`；
- **不再被任何来源引用** → 才删除旧键（`ui_keys_migrated`）；
- 确认框文案区分三种数：`迁移 N`（旧键删除）/ `共用 M`（新旧都留）/ `未匹配 K`（保留孤儿）。

### 10.6.5 旧 `ui` 键的迁移（可增量、可离线、可补迁）

旧键：`ui.videos[相对路径]`、`ui.photos[...]`、`ui.markers[名字]`、`ui.ortho[文件名]`。

**迁移依据不止「现场扫描」**：`project.json` 里每个来源已经存了文件清单
（`folders[].files[]`：`name` / `relative_path` / `size`），
所以**来源离线时也能完成大部分映射**（相对路径 + 名字就够算 `itemId`）。
现场扫描只是「补充新增/变化的文件」，不是迁移的前提。

**规则**

1. **可以离线迁移**：先用 `project.json` 里的清单做映射；来源在线时再用扫描结果补全。
2. **`ui.itemsVersion` 只表示「迁移尝试过」，不表示「旧键作废」**：
   读状态的顺序永远是 `ui.items[itemId]` → 找不到再看旧键；
   旧键一直可读，**不会因为版本号变大而失效**。
3. **未映射的旧键必须持续保留**，并在每次打开项目 / reindex 时**自动补迁**
   （`增量迁移`：只要这次能映射上就写入 `ui.items`，然后才删旧键）。
4. **删旧键的前提**同 10.6.4：该旧键对应的内容已完整映射，且没有其它来源仍引用。
5. 迁移日志要给出三个数：`本次迁移 N` / `待补迁 M（来源离线或缺文件）` / `歧义 K`。
6. 歧义（两个不同来源下有相同相对路径但不同真实文件）：按 **primary 来源**解析，
   并在日志里列出被按 primary 解析的条目；这类旧键迁移后**保留一份**
   （`ui.legacy[oldKey] = 值`），便于人工核对，不静默丢弃。

### 10.6.6 明确的已知边界

| 场景 | 结果 | 说明 |
|---|---|---|
| 父 + 子目录同时登记 | 一个条目、一个 `itemId`，UI 显示「来源 A · 也被 B 包含」 | 靠 `realpath` 归并 |
| 移除主来源 | 次短来源接管，显隐保留 | 见 10.6.3 |
| 重定位到新盘 | id 迁移 + 显隐迁移，报告给出数量 | 见 10.6.4 |
| 文件被外部**改名** | 视为新文件（新 id），旧键变孤儿 | 不做 rename 检测（成本高）；reindex 会报「消失 N / 新增 M」 |
| 文件被外部**替换**（同名） | id 不变（路径同），但 `stale_input` 触发「已过期」 | 见 10.4 |
| 旧项目第一次打开 | 增量迁移；未匹配的旧键保留且**不会失效**，来源恢复后补迁 | 见 10.6.5 |
| 外接盘离线时打开旧项目 | 用 project.json 里的文件清单迁移，不依赖现场扫描 | 见 10.6.5 |
| 重定位后旧 id 仍被另一来源引用 | 新旧键都保留状态，不删旧键 | 见 10.6.4 |

### 10.6.7 离线算出的身份：插回盘后必须「保持或可迁移」

`itemId` 依赖 `realpath`，而**离线时根本解析不了 realpath**（目录不存在）。
所以必须接受"离线时会算出另一个身份"这件事，但要用规则保证它不丢状态：

| 情形 | 身份取法 | 插回盘之后 |
|---|---|---|
| 索引里**已有** `itemId`（哪怕是上次在线算的真实身份） | **原样沿用，绝不覆盖** | 真实路径一致 → 身份不变，什么都不用做 |
| 索引里**没有** `itemId`，且盘在线 | `it_<sha1(realpath)>` | — |
| 索引里**没有** `itemId`，且盘离线 | 暂用 `ip_<sha1(来源路径|相对路径)>`，并标记 `itemIdPending=true` | reindex 时算出真实 `it_…`，把 `ip_…` 的 ui 状态**迁移**过去（旧键按 10.6.4 的条件决定是否删除） |

要点：

1. **永远优先沿用索引里已有的身份**；只要存过真实身份，离线也不降级成临时身份。
2. 只有"从来没有身份"时才用临时 `ip_` 身份，并记下 `itemIdPending`。
3. 盘恢复后（reindex）：
   - 临时身份 `ip_X` → 真实身份 `it_Y`；
   - `ui.items[it_Y] = ui.items[ip_X]`（已存在则不覆盖）；
   - `ip_X` 是否删除，按 10.6.4：仍被其它来源引用就保留；
   - 全程不改用户看到的显隐。
4. junction / 符号链接：离线时按"来源路径 + 相对路径"算的是**逻辑路径**身份；
   插回盘后按 `realpath` 算的是**真实路径**身份。两者不同属于预期，
   由第 3 条迁移消化，不需要用户干预。

### 10.6.8 P1b 验收标准（一句话）

> **旧项目打开后，视频 / 正射 / 覆盖等原有地图显隐，在「在线」「离线」「重新接盘」三种状态下都不丢。**

拆成可自动验证的四条：

1. **在线迁移**：旧 `ui.videos[相对路径]` / `ui.ortho[文件名]` / `ui.coverage[srt]`
   能映射到 `ui.items[itemId]`，状态值不变；已映射的旧键删除，未映射的保留并计数。
2. **离线迁移**：把来源路径指向不存在的目录（但 `project.json` 里仍有 `files[]` 清单），
   迁移仍能完成映射；身份用 `ip_…` 并标 `itemIdPending`；界面状态不变。
3. **重新接盘**：目录回来后再次迁移，`ip_…` 状态迁到 `it_…`，状态值不变；
   若旧 `ip_` 键仍被另一来源引用，则两个键都保留（10.6.4）。
4. **不误删**：迁移过程只改 `project.json` 的 `ui`，**不触碰任何磁盘文件**。

### 10.6.9 P1b 落地记录（2026-10-25）

| 项 | 落地 |
|---|---|
| 身份 | `item_id_for_path()`（`it_`，realpath）· `item_id_provisional()`（`ip_`，来源+相对路径） |
| 补身份 | `ensure_item_ids()`：load 时只在内存补；在线算真实身份、离线沿用已有身份，从未有过才用 `ip_` 并标 `itemIdPending` |
| 迁移 | `migrate_ui_items()`：`ip_X → it_Y`（旧键仅在没有其它来源引用时删）+ 旧键 `videos/ortho/coverage → items[itemId]`；映射不上的旧键保留计 `pending` |
| 接口 | `GET /api/project/ui-items`（只读）· `POST /api/project/ui-migrate`（写盘，只改 ui） |
| 测试 | `Code/test_ui_items.py`（离线 / 重接盘 / 共用引用 / 不动磁盘），已登记 `run_tests.js` |
| 实测 | 东莞地铁：251 个文件全部 `it_`；原有 ui 桶逐项一致；11 标记点 / 2 标注不受影响 |

> 现状：数据层已就绪，**界面仍读旧键**（行为不变）；P2 切到 `ui.items` 时才需要前端改动。

### 10.7 P1c 落地记录（2026-10-25，分 4 步提交）

| 接口 | 行为 |
|---|---|
| `POST /api/project/source/reindex` | 扫一个来源；成功写清单 + `indexed_at` + `index_status`；`missing/denied/timeout` 时**保留旧索引**只改状态 |
| `POST /api/project/sources/reindex` | 批量（`source_ids` 省略 = 全部），逐个跑、单个失败不影响其它，返回 `ok/total` |
| `POST /api/project/source/relocate` | `confirm:false` 只出预检报告（`matched/missing/added/match_ratio/verdict`）；`confirm:true` 才改路径、重扫、按相对路径迁移 `ui.items`（旧键仅在无其它来源引用时删）；返回 `ui_keys_migrated / ui_keys_shared / ui_keys_unmatched` |
| `POST /api/project/source/detach` | 只从 `folders[]` 移除；磁盘文件一个不动；`ui.items` 状态保留（返回 orphan 计数）；`delete_generated:true` 明确拒绝（等带预览的版本） |

实现要点：
- 扫描超时用线程 `join(timeout)` 控制（30 s），超时记 `timeout` 且不写索引；
- relocate 的「旧 id」**优先取 `itemIdPrev`** —— load 时在线重算会把原值挪到那里，
  只读 `itemId` 会漏掉用户状态（实测踩到，已修）；
- 预检/确认两次都返回同一份报告结构，前端可以复用同一套 UI。

实测（真实项目「东莞地铁」，3 个来源）：
```
单个刷新   status ok，files 150，36 ms
全部刷新   ok 3/3，耗时 0.1 s
重定位预检（指回原路径） verdict=same，matched 150/150，dry_run=true
```

#### 10.7.1 接口返回语义（定稿）

| 接口 | 返回 | 关键字段 |
|---|---|---|
| `POST /api/project/source/reindex` | `{success, source}` | `status` ∈ `ok / partial / missing / denied / timeout / busy`；`indexed_at`；`counts{file_count,mp4_count,srt_count,jpg_count,other_count,total_size}`；`warnings[{path,error}]`；`kept_uncertain` / `dropped` / `duration_ms` |
| `POST /api/project/sources/reindex` | `{success, sources[], count, ok}` | 单个失败不影响其它；`ok` = 状态为 `ok` 的个数 |
| `POST /api/project/source/relocate` | `{success, report}` | 预检：`dry_run:true`、`verdict` ∈ `same/likely/different`、`matched/missing/added/match_ratio`；确认：`dry_run:false` + `ui_keys_migrated / ui_keys_shared / ui_keys_unmatched / ui_orphans` |
| `POST /api/project/source/detach` | `{success, result}` | `removed{id,name,path,file_count}`、`sources_left`、`ui_items_kept`、`ui_items_shared`、`ui_items_orphan`、`orphan_ids[]` |

失败语义：

- `missing`：根目录不存在 —— **保留旧索引**，只写 `index_status/index_warnings`；
- `denied`：根目录 `PermissionError` —— 同上；
- `timeout`：线程 `join(30s)` 超时 —— 同上，不写索引；
- `partial`：部分子目录读不了 —— 那些前缀下的**旧条目保留**并标 `uncertain:true`，
  完整扫描区域内确认消失的条目才删除（`dropped`）；有任何 warning 即 `partial`；
- `busy`：同一 `source_id` 正在扫描 —— 直接返回，不排队、不重复扫。

#### 10.7.2 实现要点（踩过的坑）

1. **扫描根只来自 `project.folders[].path`**，接口不接受外部路径（安全边界）。
2. **partial 合并**：`uncertain` 是相对前缀；前缀下的旧条目保留并标 `uncertain`，
   避免"读不到就当成删了"。
3. **relocate 要认两个旧身份**：`itemIdPrev`（load 时被换下来的原值）与 `itemId`（当前），
   且**先处理 `itemId`**（新键已存在不覆盖，先处理者胜出）。只取一个会丢用户状态。
4. **relocate 的删除阈值**：`_item_ref_count` 是在本来源旧条目已被替换之后算的，
   所以计数就是「其它来源的引用数」→ 必须 `== 0` 才删，`>=1` 计入 `shared` 并保留旧键。
5. **生成物关联**：`project.json` 的 `videos/tracks` 目前是空数组（前端动态构建），
   生成物（`.srt / .geojson`）本身就是索引里的文件条目，因此"按相对路径迁移生成物关联"
   等价于「迁移这些条目的 itemId + 其 ui 状态」，测试 5c 覆盖。
6. **detach 不清理 ui.items**：全部来源移除后内容变 orphan（`orphan_ids`），状态保留。

#### 10.7.3 测试记录

`Code/test_source_ops.py`（已登记 `run_tests.js`）：

```
1) 正常扫描：status ok / 4 文件 / 写 indexed_at / 全部 it_ 身份
2) 目录不存在：status missing，旧索引逐条保留
2b) 并发：手工占锁后 reindex 返回 busy，锁释放后恢复 ok
2c) partial：fake walker 让 locked/ 报 PermissionError，
    locked/inside.mp4 保留且标 uncertain，stale.mp4 被移除，status=partial
3) 批量：一个 ok 一个 missing，互不影响
4) 预检：dry_run、matched/missing/added、路径未改、零写入（JSON 前后一致）
5b) same / different 两种 verdict
5c) 生成物 srt 与其显隐按相对路径迁到新 itemId
5d) 重叠来源：旧 itemId 仍被引用 -> shared>=1 且旧键保留
6) detach：只解除关联、磁盘文件不动、delete_generated 被拒
7) 共享内容：移除一个来源后另一来源仍引用 -> 状态保留、不计 orphan
8) 全部移除：ui.items 原样、shared_id 进 orphan_ids
```

全套：`node run_tests.js` → **40/40 全部通过**；`check_page.js` 全绿。

#### 10.7.4 阶段状态

- **P1c 完成**（4 个提交：step0 歧义留档 / step1 reindex / step2 relocate / step3 detach）。
- **P2（左栏三段式改版）尚未开始**：本轮没有任何前端改动，也没有重打安装包。
- 测试基线：**40/40**（此前文档里的 39/39 已过时：本轮新增 test_source_ops 等套件）。

### 10.8 P2 验收条件（新左栏接管前必须满足）

> 背景：P1b 迁移器目前只处理 `videos / ortho / coverage`，且**歧义时会选一个 id 并删除旧键**，
> 没有把原值留到 `ui.legacy`。文档承诺过"歧义保留供核对"，这一条必须在 P2 补齐。

**A. 歧义状态不丢 —— ✅ 已实现（2026-10-25，第 0 步）**

- 迁移遇到歧义（同一相对路径命中多个来源）时：
  1. 选中的 `itemId` 写入 `ui.items`（保留原值）；
  2. **同时**把旧键原值写入 `ui.legacy["<kind>:<旧键>"] = 值`；
  3. 旧键**保留不删**（等用户核对后再清，或由"清理孤儿"统一处理）；
  4. 迁移统计里 `ambiguous` 与 `legacy_saved` 两个数都有。
- 已加测试（`Code/test_ui_items.py` §1b）：两个来源同相对路径、不同真实文件 →
  `ui.legacy["videos:v1.geojson"]` 存在且值与旧键一致、旧键仍在、重复迁移不重复累加。

**B. 其余旧状态如何处理（必须逐项写明并实现）**

| 旧状态 | 现在的含义 | P2 处理方式 |
|---|---|---|
| `ui.videos[...]` | 逐条航迹显隐 | ✅ 已迁移到 `items`（P1b） |
| `ui.ortho[...]` | 逐张正射显隐 | ✅ 已迁移（P1b） |
| `ui.coverage[...]` | 逐份覆盖层显隐 | ✅ 已迁移（P1b） |
| `ui.photos[...]` | 历史上未使用（逐张状态只在内存 Set 里） | **没有可迁移的数据**；P2 新增逐张状态时默认"显示"，并在迁移报告里说明"照片逐张状态为新功能" |
| `ui.markers[...]` | 按**名字**记的标记点显隐 | 迁移到 `items["marker:<marker.id>"]`（按 id，不按名字 —— 改名不丢状态）；名字反查不到 id 的保留旧键并计入 `pending` |
| `photosHidden` | "整组照片被清空"的标志 | **长期保留**（黑名单语义）；不展开成 190 条逐项 false |
| `orthoHidden[]` | 被清空的正射清单 | 同上，长期保留 |
| `coverageHidden[]` | 被清空的覆盖清单 | 同上，长期保留 |

> 之所以 `*Hidden` 不转成逐项：它们是"整组清空"的黑名单，展开会产生上百条无意义键，
> 且清空/恢复的语义（重新登记后自动恢复）靠清单本身更直观。

**C. 一次性验证**

P2 上线前跑一次"旧项目体检"：打开项目 → 记录 `ui` 全部键 → 迁移 → 再比对：
所有**原有显隐值**在 `ui.items` / `ui.legacy` / 保留的 `*Hidden` 里都能找到对应，
数量一致；否则不允许切换界面。

### 10.9 旧状态盘点：P2 之前每种都怎么处理

> 现状（P1b + 第 0 步）：`ui.items` 已就绪，但**前端仍读旧键**，所以这一轮只要求
> "不丢、可查、可回退"。下表是逐项结论，不允许"默默丢弃"。

| 旧状态 | 结构 | 现状 | P2 前处理 | P2 时目标 |
|---|---|---|---|---|
| `ui.videos` | `{相对路径: bool}` | ✅ 已迁 `items[itemId]`，旧键删除 | 读 `items` 优先，旧键兜底 | 只读 `items` |
| `ui.ortho` | `{文件名: bool}` | ✅ 已迁 | 同上 | 只读 `items` |
| `ui.coverage` | `{srt 路径/名: bool}` | ✅ 已迁 | 同上 | 只读 `items` |
| `ui.photos` | `{…: bool}`（历史未真正使用） | 空 / 不存在 | **不迁移**（无数据）；显式说明"照片逐张状态是新功能" | 新增 `items[itemId]`，默认显示 |
| `ui.markers` | `{名字: bool}` | 未迁移（不是来源文件） | **保持原样**继续用（改名会丢，P2 修） | 迁到 `items["marker:<marker.id>"]`，按 id 不按名字 |
| `ui.legacy` | `{"<kind>:<旧键>": 值}` | ✅ 第 0 步新增 | 只写不读，供人工核对 | 提供"查看/清理歧义记录"入口 |
| `ui.photosHidden` | bool（整组清空） | 保持原样 | **长期保留**（黑名单语义） | 不变 |
| `ui.orthoHidden` | 数组（被清空的正射） | 保持原样 | 长期保留 | 不变 |
| `ui.coverageHidden` | 数组（被清空的覆盖层） | 保持原样 | 长期保留 | 不变 |
| `ui.itemsVersion` | int | 1 | 只表示"迁移尝试过"，**不表示旧键作废** | 不变 |

> 为什么要保留三个 `*Hidden`：它们是"整组被清空"的黑名单，
> 展开成逐项（190 张照片 / 149 张全景）会产生上百条无意义键，
> 且"重新登记后自动恢复"这个语义靠清单本身更直观。

---

## 11. P2 字段/API 对应表（2026-10-25 定稿，实施依据）

> 原则：**优先复用现有接口**，不为新左栏另造数据通道；写操作只写 `ui.items`
> （`ui-state` 由后端改成**合并**写，避免覆盖 `items/legacy/*Hidden`）。

### 11.1 ① 项目区块

| 用途 | API | 读取字段 | 写入 |
|---|---|---|---|
| 项目下拉 | `GET /api/project/list` | `projects[].name` | — |
| 当前项目详情 | `GET /api/project/get?name=` | `project.name / folders / ui / markers / labels / vectors` | — |
| 新建 / 移出列表 | 现有 `createProjectBtn` / `deleteProjectBtn` 流程（不改） | — | 项目元数据 |
| 来源数量 / 最近索引 | `GET /api/project/sources?name=` | `sources[].id / name / path / exists / index_status / indexed_at` | — |
| 内容数量 | 前端汇总（见 11.3） | — | — |

### 11.2 ② 数据来源区块

| 动作 | API | 读取 | 写入 |
|---|---|---|---|
| 列出 | `GET /api/project/sources?name=` | `id, name, path, exists, index_status, index_warnings, indexed_at, file_count` | — |
| 添加来源（多选） | 复用现有 Windows 文件夹选择流程（`addFolderBtn` → 导入弹窗 → 后端对话框） | — | `folders[]` |
| 单来源刷新 | `POST /api/project/source/reindex` | `source.status / indexed_at / counts / warnings / kept_uncertain / dropped` | `index_*`、`files[]` |
| 全部刷新 | `POST /api/project/sources/reindex` | `sources[]、count、ok` | 同上 |
| 重新定位（两步） | `POST /api/project/source/relocate` | 预检：`verdict / matched / missing / added / match_ratio`；确认：`ui_keys_migrated / ui_keys_shared / ui_keys_unmatched / ui_orphans` | `folders[].path`、`ui.items` |
| 移除来源 | `POST /api/project/source/detach` | `removed / sources_left / ui_items_kept / ui_items_shared / ui_items_orphan` | 只删 `folders[]` 条目 |

**状态 → 可执行动作**

| `status` | 文案 | 允许动作 |
|---|---|---|
| `ok` | ✓ 在线 · 索引于 HH:MM | 刷新、移除 |
| `partial` | ⚠ 部分不可读（N 项） | 刷新、移除 |
| `missing` | ⚠ 找不到目录 | 刷新、**重新定位**、移除 |
| `denied` | ⚠ 无权限 | 刷新、**重新定位**、移除 |
| `timeout` | ⚠ 扫描超时 | 刷新、移除 |
| `busy` | ⟳ 正在扫描 | 只读（按钮禁用） |
| 未扫描（无 `indexed_at`） | ○ 未扫描 | 刷新、移除 |

### 11.3 ③ 内容区块

数据来源（全部为**内存中已有集合**，本轮不新增拉取）：

| 分组 | 数据来源 | 行内字段 | 动作 |
|---|---|---|---|
| 视频 | `loadedTracks[].fileInfo` | 名称、来源（`folder_index` → 来源名）、处理状态（有 `.geojson` = 已生成；`.srt` 缺失 = 缺 SRT） | 上图、定位、移除 |
| 照片 | `photoGroups[]`（按 `photoKindOf` 分 广角/变焦/360） | 名称、来源、张数 | 上图、定位、移除 |
| 正射 | `orthoList[]`（`kind==='ortho'`） | 文件名、来源、金字塔状态 | 上图、定位、移除 |
| KML/矢量 | `projectVectors[]`（`kind: line/polygon`） | 名称、来源（项目）、类型 | 上图、定位、移除 |
| 覆盖 | `coverageItems[]` | SRT 名、来源、是否 built | 上图、定位、移除 |
| 位置点 | `projectMarkers[]` | 名称、分类、来源（项目） | 上图、定位、编辑、移除 |
| 文字标注 | `projectLabels[]` | 文字、来源（项目） | 上图、定位、编辑、移除 |

**显隐键**：`ui.items[itemId]`；`itemId` 来自
`GET /api/project/ui-items` 的 `files[]`（本轮给该接口补 `files: [{source_id, relative_path, itemId, pending}]`），
标记点/标注用 `marker:<marker.id>` / `label:<label.id>`。

**兼容读取**（只读兜底，不写）：`ui.videos[相对路径]` → `ui.ortho[文件名]` → `ui.coverage[srt]` → `ui.markers[名字]`。

### 11.4 迁移

| 时机 | 调用 | 处理 |
|---|---|---|
| 打开项目后（每个会话一次） | `POST /api/project/ui-migrate` | 显示 `migrated / pending / ambiguous / legacy_saved`；有 `pending` 时在内容区顶部提示"还有 N 条旧状态待补迁（来源离线）"，旧键继续可读 |
| 迁移失败 | — | 保留旧入口提示，新面板仍读 items + 旧键兜底，不写 |

### 11.5 本轮明确不做

- 不做 P3 的全项目索引化（内容清单仍基于内存集合 + 现有接口）；
- 不改中间地图、右侧视频/照片区布局；
- 不提供"删除生成物/原始媒体"的选项；
- 不新增项目复制/导出等未定义功能。

---

## 12. P2 落地记录（2026-10-25）

### 12.1 提交清单

| 阶段 | 内容 |
|---|---|
| P2a | §11 字段/API 对应表（先定接口，再写代码） |
| P2b | 三段式左栏上线；`ui-state` 改合并写；`ui-items` 增加 `files[]` |
| P2c | `ui.markers` 按 `marker.id` 迁移；Hidden / photos 字段原样保留 |
| P2d | 按需迁移、SRT 判断修正、窄屏适配、回退互斥 |
| P2e | 测试（新增 `test_ia_panel.js`）与本文档 |

### 12.2 新界面实际调用的接口

| 区块 | 调用 |
|---|---|
| ① 项目 | `GET /api/project/list`、`GET /api/project/get`、`GET /api/project/sources`（取数量/最近索引）；新建/导入/移除直接复用旧按钮的点击处理 |
| ② 数据来源 | `GET /api/project/sources`；添加：`/api/project/select-folder` → `/api/project/scan-folder` → `/api/project/add-folder`；刷新：`/source/reindex`、`/sources/reindex`；重定位：`/source/relocate`（confirm:false → 确认 → confirm:true）；移除：`/source/detach` |
| ③ 内容 | 数据来自内存集合（`loadedTracks`/`photoGroups`/`orthoList`/`coverageItems`/`projectVectors`/`projectMarkers`/`projectLabels`）+ `GET /api/project/ui-items` 的 `files[]` 映射 itemId；显隐写 `POST /api/project/ui-state`（后端合并） |
| 迁移 | `POST /api/project/ui-migrate`（**按需**：只有没 `itemsVersion` 或旧键还有条目时才调） |

### 12.3 显隐与身份规则（实现版）

- 读：`ui.items[itemId]` → 找不到再读旧键（`videos/ortho/coverage/markers`，只读）。
- 写：只写 `ui.items`；`ui-state` 由后端**合并**，不会覆盖 `legacy` / `*Hidden`。
- itemId：文件类来自 `ui-items.files[]`（P1b 的 `it_`/`ip_`），
  位置点 `marker:<id>`、文字标注 `label:<id>`、KML `vector:<id>`。
- 迁移：
  - `videos/ortho/coverage` → `items`（P1b）；
  - `markers` → `items["marker:<id>"]`（P2c，按 id 不按名字）；
  - 名字对不上的旧键**保留**并计 `pending`；
  - 歧义原值进 `ui.legacy`（第 0 步）；
  - `photosHidden / orthoHidden / coverageHidden` **长期保留**，不展开；
  - `photos` 历史为空 → 逐张照片默认显示（新功能，不迁移）。

### 12.4 测试

新增 `test_ia_panel.js`（已登记）：43 条静态断言，覆盖
三段顺序与必备 id、无重复 id（新区块范围）、旧左栏 hidden、添加来源的多选/扫描/登记接线、
单/全量刷新、relocate 两步（预检 → 确认 → 生效，且告知不动文件）、detach 说明与「本轮不提供删除生成物」、
七种来源状态、内容分组/搜索/筛选/三态/动作语义（⤢/✎/× 不叫「加载」）、
`ui.items` 读/写与旧键只读兜底、迁移调用与提示、回退互斥、中栏/右栏未改动。

后端侧（既有）：`test_ui_items.py` 覆盖 markers 迁移、Hidden 保留、`ui-state` 合并写、
歧义留档；`test_source_ops.py` 覆盖 reindex/relocate/detach。

```
node run_tests.js  → 41/41 全部通过
check_page.js      → 全部通过
```

### 12.5 已知限制（本轮不修）

1. 内容清单仍基于**内存集合**（`loadedTracks` 等），所以进入新界面前，旧版的加载流程仍需在后台跑
   （已用轮询兜住）；真正的"全项目索引化"是 P3。
2. 照片的**逐张**显隐只在内存（`photoHidden`）与 `photosHidden` 黑名单层面持久化；
   逐张持久化需要新键，留到 P3 统一做。
3. 文字标注 / KML 的显隐目前是"会话内"（`hidden` 标记 / `vectorHidden`），未写入 `ui.items`
   —— 因为它们的渲染路径还没有统一的可见性入口，P3 一并处理。
4. 新界面文案是中文硬编码（未接 i18n），英文界面下这部分仍是中文。
5. 来源重定位的"差异大"只给 verdict 与数量，没有逐个文件 diff 视图。
6. 左栏仍是固定宽度三卡，窄屏只做"隐藏次要信息"，不做抽屉/浮层改版。

### 12.6 状态

- **P2 完成**（P2a–P2e 各一次提交）。
- **P3（全项目索引化）尚未开始**；没有重打安装包。
- 开发验证**没有**对真实项目调用写接口：迁移改为按需后，重载前后
  `Project/东莞地铁/project.json` 的 mtime 不变（先前 `ui-migrate` 首次运行只新增
  `ui.items/legacy/itemsVersion/itemsMigratedAt` 四个键，未改动任何旧状态）。
