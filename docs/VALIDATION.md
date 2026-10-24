# 验证与交付记录

记录时间：2026-10-24（Asia/Shanghai）。本文件只陈述实际执行过的检查；没有执行的外部操作会明确标注未执行。

## 1. 环境

- 操作系统：Windows 11（10.0.26200）
- Python：3.12.14（项目运行时不依赖第三方包）
- Node.js：v24.21.0（测试使用内置 `node:test`）
- 浏览器：Microsoft Edge Headless（实际渲染与交互验收）
- 子路径托管：本地 HTTP 服务器从仓库父目录提供带空格/中文的目录路径，模拟 GitHub Pages 项目子路径
- GitHub Actions 与 GitHub Pages：本工作区没有远程 GitHub 仓库权限，未实际运行或部署

## 2. 自动化测试

### Python

```powershell
python -m unittest discover -s tests/python -v
```

实际结果：**52 tests / 52 passed / 0 failed**，退出码 0。

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

已发布演示数据：

```powershell
python .github/scripts/validate_data.py --data-dir docs/data
python tools/validate_data.py --data-dir docs/data
```

结果：两份校验器均通过。CI 校验器报告 5 个 JSON 文件、10 条记录、3 个演示来源、3 条日志记录；要求字段、ISO 时区、枚举、content_hash、计数一致性、重复 ID/标题/URL 与 JSONL 均可解析。

默认真实配置的安全采集：

```powershell
Remove-Item -Recurse -Force collector-output -ErrorAction SilentlyContinue
python .github/scripts/seed_staging_data.py --target docs/data --stage collector-output
python -m collector --sources collector/sources.json --output collector-output
python .github/scripts/validate_data.py --data-dir collector-output
python .github/scripts/publish_staged_data.py --sources collector/sources.json --stage collector-output --target docs/data
```

实际结果：

- 默认 6 个候选来源全部 `enabled: false`、`verified: false`。
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
- 输出 5 条临时 live 记录；全部为 `verification_status=pending`，`verified` 来源数为 0。
- 详情正文、发布时间、官方详情 URL、链接 HTTP 事实成功进入输出；无法明确的报名时间和报名入口保持 `null`。
- `.github/scripts/validate_data.py` 校验通过：5 records、6 sources、20 log entries。
- 结果只存在于临时目录，没有写入或替换 `docs/data/`，也没有把来源设置为启用或已验证。
- 当前不存在已经人工核实、可称为生产已验证的信息源。

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

已执行：工作流结构/关键字段检查，2 个 workflow 通过；另外使用临时安装到 `.tmp/` 的 PyYAML 对两个 workflow 做了完整 YAML 语法解析和关键触发/权限断言，均通过。PyYAML 只是一次性开发校验工具，不是项目运行依赖。GitHub Actions 首次真实运行仍是最终权威验证。

未执行：

- 没有实际触发 GitHub Actions。
- 没有实际部署 GitHub Pages。
- 没有线上网址。
- 没有验证 GitHub 的权限、分支保护、出站访问、schedule 延迟或 Pages 环境行为。

这些需要在 GitHub 仓库网页中按 `docs/DEPLOYMENT.md` 完成，并以首次真实运行日志为准。

## 7. 交付边界

当前站点使用合成演示数据，UI 全站标记；真实候选来源均未启用、未人工核验。自动更新工作流已配置但未真实运行；在线发布未完成。报名、提交或缴费前必须查看主办方原始页面。需要多人登录、跨设备同步或服务端权限控制时，纯静态架构不能提供，需另建后端。
