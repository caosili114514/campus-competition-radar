# 验证与交付记录

记录时间：2026-10-24（Asia/Shanghai）。本文件只陈述实际执行过的检查；没有执行的外部操作会明确标注未执行。

## 1. 环境

- 操作系统：Windows 11（10.0.26200）
- Python：3.12.14（项目运行时不依赖第三方包）
- Node.js：v24.21.0（测试使用内置 `node:test`）
- 浏览器：Microsoft Edge Headless（实际渲染与交互验收）
- 子路径托管：本地 HTTP 服务器从仓库父目录提供带空格/中文的目录路径，模拟 GitHub Pages 项目子路径
- GitHub Actions 与 GitHub Pages：用户已在 GitHub 网页完成仓库配置；Pages 部署工作流成功，线上地址为 <https://caosili114514.github.io/campus-competition-radar/>；首次数据更新已成功生成并发布 5 条 pending 公开记录

## 2. 自动化测试

### Python

```powershell
python -m unittest discover -s tests/python -v
```

实际结果：**52 tests / 51 passed / 1 demo-only skipped / 0 failed**，退出码 0。跳过项只在演示数据上适用的链接域断言；测试类型同时兼容 demo 和 live 数据。

另外执行：

```powershell
python -m compileall -q collector tests/python
```

结果：退出码 0。

### Node.js

```powershell
npm test
```

实际结果：**32 tests / 32 passed / 0 failed**，退出码 0。

测试覆盖包括日期解析与截止状态、组合筛选、筛选与卡片状态一致性、localStorage 收藏/进度/备注持久化、数据结构归一化、去重、缺失字段、链接核验状态、单来源失败容错、详情抓取隔离、robots 规则、更新频率、请求间隔、手动公众号入口和演示数据边界。

## 3. 数据契约与发布保护

以下安全采集与发布保护测试是在六个来源仍为 disabled 的配置下实际执行的，用于验证不会用空数据覆盖演示内容。

当前已发布 live 数据：

```powershell
python .github/scripts/validate_data.py --data-dir docs/data
python tools/validate_data.py --data-dir docs/data
```

结果：两份校验器均通过。CI 校验器报告 5 个 JSON 文件、5 条 live 记录、6 个来源、20 条日志记录；要求字段、ISO 时区、枚举、content_hash、计数一致性、重复 ID/标题/URL 与 JSONL 均可解析。字段覆盖检查提示部分来源使用程序设计、电子设计、艺术设计等细分类别，不影响数据契约通过。

启用来源前的安全采集回归：

```powershell
Remove-Item -Recurse -Force collector-output -ErrorAction SilentlyContinue
python .github/scripts/seed_staging_data.py --target docs/data --stage collector-output
python -m collector --sources collector/sources.json --output collector-output
python .github/scripts/validate_data.py --data-dir collector-output
python .github/scripts/publish_staged_data.py --sources collector/sources.json --stage collector-output --target docs/data
```

实际结果：

- 该回归测试时 6 个候选来源全部 `enabled: false`、`verified: false`。
- 采集器退出码 0，生成空的 `data_mode: live` staging 数据，运行状态为 `no_enabled_sources`。
- staging 数据契约校验通过：0 records、6 sources、8 log entries。
- 发布脚本输出 `[SKIP] No source has enabled=true`，`published=false`，`docs/data/` 全部文件哈希前后不变。
- 该保护避免每日任务在未启用真实来源时把演示数据替换为空数据。

## 4. 真实公开来源核查与临时采集

开发期间实际发起过公开网络请求，结果如下。只能说明当时可访问，不代表抓取许可、内容真实性或主办方授权已经确认。

| 候选来源 | 列表页 HTTP | robots.txt | 临时真实采集 |
| --- | --- | --- | --- |
| 中国大学生计算机设计大赛 | 200 | 404（无规则文件） | 成功解析 |
| 全国大学生信息安全竞赛 | 200 | 200，Allow | 过滤后 0 条 |
| 全国大学生电子设计竞赛 | 200 | 404（无规则文件） | 成功解析 |
| 全国大学生数学建模竞赛 | 200 | 200，空规则 | 过滤后 0 条 |
| 全国大学生广告艺术大赛 | 200 | 200，Allow | 成功解析 |
| 中国大学生服务外包创新创业大赛 | 200 | 404（无规则文件） | 过滤后 0 条 |

将六个来源临时启用并每源限制 2 条候选后，真实采集实际结果：

- 退出码 0，耗时约 21.5 秒，0 个来源网络失败。
- 输出 5 条 live 记录；全部为 `verification_status=pending`，`verified` 来源数为 0。
- 详情正文、发布时间、官方详情 URL、链接 HTTP 事实成功进入输出；无法明确的报名时间和报名入口保持 `null`。
- `.github/scripts/validate_data.py` 校验通过：5 records、6 sources、20 log entries。
- 维护者启用六源后，首次 GitHub Actions 数据更新于 2026-10-24 成功运行，将这 5 条记录写入 `docs/data/` 并触发 Pages 部署。
- 当前不存在已经人工核实、可称为生产已验证的信息源；线上记录仍需人工核验。

## 5. 浏览器实际渲染与交互验收

使用 Headless Edge 加载本地静态服务器，进行实际 DOM、样式和交互检查：

- 仪表盘、竞赛发现、竞赛详情、信息源与运行、我的竞赛、关于页面均成功加载，无未捕获 JavaScript 错误。
- 390x844 移动视口下六个页面均无水平溢出；演示横幅可见；侧栏按移动端规则隐藏。
- 子路径部署测试：从仓库父目录以编码后的目录路径加载 `index.html#/competitions`，资源与 `docs/data/*.json` 全部加载成功，10 张演示卡片渲染，无 404。
- 报名状态筛选实际结果：open=1、pending_window=3、broken=1、upcoming=1、pending_upcoming=0、closed=2、unknown=0、pending_unknown=2；每条结果卡片的状态标签与所选筛选一致。
- 实际交互测试：在竞赛卡片收藏；进入我的竞赛设置进度为准备中；填写备注；刷新 iframe 后收藏徽标、进度和备注全部保留，localStorage 读写成功。
- live 模式集成测试：临时把真实采集的 5 条 pending 记录放入站点数据后，页面显示公开采集数据，演示横幅保持 hidden，演示徽标数量为 0，信息源表加载 6 个来源，无未捕获 JavaScript 错误；测试后恢复演示数据且全部文件哈希一致。
- 实际生成截图：`docs/screenshots/dashboard.png`、`competitions.png`、`detail.png`、`sources.png`、`mobile-dashboard.png`。截图展示的是明确标记的演示数据。

## 6. GitHub Actions 与 GitHub Pages

已完成配置：

- `.github/workflows/update-data.yml`：每日 UTC 18:17 + 手动触发、测试、安全 staging、契约校验、发布保护、变化时普通 commit/push。
- `.github/workflows/deploy-pages.yml`：push main、手动触发、数据更新成功后的 `workflow_run`；使用 GitHub Pages artifact 部署。
- 根目录 `.nojekyll`，无需前端构建。

已执行：

- 工作流结构/关键字段检查，2 个 workflow 通过。
- 使用临时安装的 PyYAML 对两个 workflow 做完整语法解析和关键触发/权限断言，均通过；PyYAML 不是项目运行依赖。
- GitHub Pages 部署工作流 `Deploy static site to GitHub Pages` 已真实运行。
  - 首次由 push 自动触发的运行因 Pages 尚未设置为 GitHub Actions 而失败。
  - 完成 Settings → Pages → GitHub Actions 后，手动部署运行 40101615067 成功。
  - 线上地址：<https://caosili114514.github.io/campus-competition-radar/>。
  - 已实测首页、competitions.json、CSS 和 favicon 均返回 HTTP 200。
- `Update competition data` 首次运行 40103289682 成功，生成并提交 `48976ac`（5 条 live、全部 pending）。
- 第二次运行 40104552347 失败，失败位置是 `Run Python tests`，不是采集器：当时测试仍硬编码要求发布数据必须是 10 条 demo，数据切换为 live 后两项测试失败。
- 已修复为 demo/live 双模式测试：live 数据只校验契约字段，demo 专用链接域断言自动跳过。修复后本地 Python 52 项测试通过（51 passed、1 skipped）。
- 新增 `workflow_dispatch` 的 `force` 输入；当来源因更新频率被跳过时，可在手动运行 update 工作流时勾选 `force` 立即强制采集。

仍未验证：

- 每日 schedule 是否按时触发，以及 GitHub 计划任务延迟。
- 数据更新工作流中的真实来源采集、自动提交和 `workflow_run` 部署链路。
- 六个来源在 GitHub Actions 环境中的出站网络结果及长期页面结构稳定性。

## 7. 交付边界

线上站点已部署，当前发布的是 5 条 `data_mode=live` 的公开采集记录，全部 `verification_status=pending`。`collector/sources.json` 中六个候选来源已设为 enabled=true、verified=false；首次数据更新工作流成功，第二次因测试假设 demo 数据而失败，修复后保留同样的数据契约并支持 live 数据。采集后的记录仍必须人工核验。报名、提交或缴费前必须查看主办方原始页面。需要多人登录、跨设备同步或服务端权限控制时，纯静态架构不能提供，需另建后端。
