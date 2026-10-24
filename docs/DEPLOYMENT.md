# GitHub Actions 与 GitHub Pages 部署说明

> **当前状态（重要）**：本仓库只提交了工作流配置和本文档，**尚未在 GitHub 上实际部署，也尚未实际触发或验证 Actions 运行**，因此没有可声称的线上地址或成功运行记录。下面是从 GitHub 网页完成首次上线所需的最少步骤；第一次运行的结果以 GitHub Actions 页面和 Pages 环境输出为准。

## 1. 架构与前置条件

- 站点是纯静态原生 ES Modules 页面，入口为仓库根目录的 `index.html`，没有前端构建步骤。
- 数据位于 `docs/data/`，由 Python 采集器生成；GitHub Pages 直接发布仓库根目录。
- 仓库默认分支按 `main` 配置。如果实际默认分支不是 `main`，需要同步修改两个工作流中的分支条件和触发路径。
- 工作流只在 GitHub 托管的 `ubuntu-latest` runner 上运行；本地无需安装 GitHub Actions runner。
- Python 采集器使用标准库，Node 测试使用 GitHub runner 自带的 Node.js，不需要 `npm install`。
- 根目录的 `.nojekyll` 用于避免 Pages 侧 Jekyll 处理；部署工作流也会在上传前再次创建它。

## 2. 在 GitHub 网页完成首次配置

### 第 1 步：把完整仓库放到 `main` 分支

1. 在 GitHub 创建空仓库（不要额外生成 README、`.gitignore` 或 License，避免覆盖本地文件）。
2. 打开仓库首页，通过 **Add file → Upload files** 上传项目文件，或先用本地 Git 推送到 `main`。无论哪种方式，都必须保留目录层级，尤其是 `.github/workflows/`、`docs/data/`、`collector/`、`assets/`、`tests/`、`index.html`、`package.json` 和根目录 `.nojekyll`。
3. 确认 GitHub 仓库首页能看到 `main` 分支和上述文件。

### 第 2 步：启用 Actions 与写入权限

1. 打开 **Settings → Actions → General**。
2. 在 **Actions permissions** 中选择 **Allow all actions and reusable workflows**，然后保存。
3. 在 **Workflow permissions** 中选择 **Read and write permissions**，然后保存。定时采集需要向 `docs/data/` 提交并推送数据。
4. 如果 `main` 启用了分支保护规则，必须允许 GitHub Actions 机器人写入，或为数据更新配置明确的绕过/合并流程；否则采集工作流会在最后 `git push` 处失败。工作流不会使用 force push。

### 第 3 步：把 Pages 来源设为 GitHub Actions

1. 打开 **Settings → Pages**。
2. 在 **Build and deployment → Source** 中选择 **GitHub Actions**。
3. 不需要选择 Deploy from a branch，也不需要配置 Jekyll 或构建目录。

### 第 4 步：手动跑一次数据更新工作流

1. 打开 **Actions** 标签页；如果页面提示 Actions 未启用，按提示启用。
2. 在左侧选择 **Update competition data**。
3. 点击 **Run workflow**，选择 `main` 分支，再点击运行。
4. 等待任务成功。该工作流依次执行：
   - Python 标准库测试：`python -m unittest discover -s tests/python -v`
   - `node --version` 与 `npm test`
   - `python .github/scripts/seed_staging_data.py --target docs/data --stage collector-output`
   - `python -m collector --sources collector/sources.json --output collector-output`
   - `python .github/scripts/validate_data.py --data-dir collector-output`
   - `python .github/scripts/publish_staged_data.py --sources collector/sources.json --stage collector-output --target docs/data`
   - 仅当发布脚本返回 `published=true` 且 `docs/data/` 有变化时，以 `github-actions[bot]` 身份提交并普通 push（不使用 force）。
5. 如果数据未变化，No data changes to commit. 是正常的成功结果。默认信息源未启用或没有可采集记录时，采集器可以成功产出空数据，不应把空结果当作已核验的完整赛事库。
6. 安全保护：如果没有任何 `enabled=true` 的信息源，或 staging 为 0 条记录而现有 `docs/data` 仍是演示数据，发布脚本会跳过替换并保留现有数据。此时工作流日志会出现 `[SKIP]` 和原因（例如 `no_enabled_sources`）；不要把它描述成已经完成了一次有效线上采集。要产生 live 数据，必须由维护者人工启用并核验具体来源；不要为了制造成功记录而随意打开全部候选来源。

### 第 5 步：部署站点

- 数据更新工作流成功后，**Deploy static site to GitHub Pages** 会通过 `workflow_run` 自动触发一次部署。
- 也可以在 **Actions → Deploy static site to GitHub Pages → Run workflow** 手动触发，或向 `main` 推送影响 `index.html`、`assets/**`、`docs/data/**`、`collector/**` 或部署工作流本身的变更。
- 部署工作流需要 `contents: read`、`pages: write`、`id-token: write`，使用 `github-pages` environment，上传根目录为 Pages artifact，再由 `actions/deploy-pages` 发布。
- 等待部署任务成功后，从任务的 **github-pages** environment 链接或 **Settings → Pages** 查看站点地址。项目站点通常位于 `https://<owner>.github.io/<repo>/`；前端资源必须使用相对路径，不能假设站点位于域名根目录。

### 第 6 步：首次验收

1. 打开 Pages 地址，确认首页、数据卡片和静态资源均能加载。
2. 在浏览器开发者工具中确认对 `docs/data/competitions.json`、`sources.json`、`meta.json` 的请求没有 404。
3. 如果页面显示演示数据，检查 `meta.json`/记录中的 `data_mode` 与 `is_demo`；不要把这些数据描述为真实已核验赛事。
4. 重新手动运行一次 **Deploy static site to GitHub Pages** 可验证重复部署；无需修改仓库。

## 3. 工作流行为摘要

### `update-data.yml`

- 触发：每天 UTC `18:17` 的 `schedule`，以及 `workflow_dispatch`。
- 并发组：`update-competition-data`，不取消正在运行的任务，避免两个采集任务同时写数据。
- 权限：`contents: write`，用于提交 `docs/data/`。
- 先运行 Python 与 Node 测试；把现有 live 的竞赛记录、信息源调度状态、运行历史和日志视图安全地种子到一次性的 `collector-output/`（demo 不会作为 live 历史注入），再运行采集器，最后先校验 staging 数据。校验不通过时不会替换或提交数据。
- 安全发布脚本 `.github/scripts/publish_staged_data.py` 决定是否把 staging 内容复制到 `docs/data/`，其中包括五个必需文件，并在 stage 提供 `run-history.json` 时一并复制。没有任何 `enabled=true` 来源时直接跳过；staging 为 0 条且现有 `docs/data` 为 demo 时也跳过，避免把演示数据替换成无记录 live 数据。
- 当现有数据已是 live，或 staging 有记录时，才允许替换；这样运行日志和来源失败状态可以随 live 数据一起提交。复制到 `docs/data/` 后会再次运行 `.github/scripts/validate_data.py --data-dir docs/data`。
- 校验内容包括：必需 JSON 文件及 `run-log.jsonl` 可解析、竞赛与来源顶层/记录必需字段存在、竞赛 `id` 与来源 `id` 唯一、count 与数组长度一致、meta 摘要一致、时间使用带 +08:00 的 ISO8601、枚举与 content_hash 合法、重复 title/source_url 检测。
- 仅在发布脚本返回 `published=true` 且 `docs/data/` 有变化时提交，再 `git pull --rebase --autostash`，最后普通 `git push`；不会使用 `--force`。被安全保护跳过的任务可以正常结束，但不会产生提交。

> **关于定时延迟**：GitHub Actions 的 cron 按 UTC 解释，并且计划任务是最佳努力，不保证准点；高峰期可能延迟数分钟甚至跳过。每天 UTC 18:17 对应北京时间次日 02:17（中国标准时间，UTC+8）。需要补采时，使用 **Run workflow** 手动触发。仓库长期无活动等情况也可能影响计划任务，具体以 GitHub 当前官方文档为准。

> **关于自动部署的触发**：使用仓库 `GITHUB_TOKEN` 推送的提交通常不会触发新的 `push` 工作流。因此部署工作流除了监听 `push`，还监听 **Update competition data** 的完成事件（`workflow_run`），这样定时采集提交后仍能进入 Pages 部署。首次配置或分支保护导致自动链路不可用时，可手动运行部署工作流。

## 4. 本地检查命令

以下命令用于维护者在本地复核。采集器先写 `collector-output/`，不会直接写 `docs/data/`；只有发布脚本允许时才会更新站点数据：

```powershell
python -m unittest discover -s tests/python -v
node --version
npm test
python .github/scripts/seed_staging_data.py --target docs/data --stage collector-output
python -m collector --sources collector/sources.json --output collector-output
python .github/scripts/validate_data.py --data-dir collector-output
python .github/scripts/publish_staged_data.py --sources collector/sources.json --stage collector-output --target docs/data
python .github/scripts/validate_data.py --data-dir docs/data
```

`publish_staged_data.py` 会执行与 Actions 相同的安全保护：没有启用来源，或 staging 为 0 条且现有数据仍为 demo 时，不会覆盖 `docs/data/`。如果只想做预览而不更新站点，跳过 publish 行，并把校验目标改为临时目录或 `collector-output/`。JSON 校验脚本支持 `--data-dir <path>`。

## 5. 权限、安全与故障排查

- **不要**把 GitHub Token、API key 或其他密钥写入 `assets/`、`docs/data/` 或任何会通过 Pages 公开的文件。当前默认配置只用仓库自带的 `GITHUB_TOKEN`，不需要自定义 secret。
- **push 被拒绝 / protected branch**：检查第 2 步的 Workflow permissions 和分支保护绕过设置；工作流不会 force push。
- **Pages 404 或部署失败**：确认 Pages 的 Source 已设为 **GitHub Actions**，部署任务确实完成，且 `index.html`、`docs/data/` 已提交到 `main`。项目站点应通过仓库子路径访问。
- **只有更新任务成功、没有自动部署**：打开部署工作流手动运行。`workflow_run` 的自动触发依赖工作流名称完全匹配；修改名称时同步修改 `deploy-pages.yml` 的 `workflows` 字段。
- **schedule 没有运行**：先确认工作流位于默认分支且 Actions 已启用，再手动 `workflow_dispatch`。不要依赖定时任务作为实时性保证。
- **JSON 校验失败**：按 Actions 日志中的字段/重复 ID 提示修复采集器；不要把校验失败的数据强行提交。

## 6. 免费额度与配额（以官方文档为准）

GitHub Free 的 Actions、Pages、私有仓库额度和公共仓库政策会随时间及账户类型变化，本文不写死具体分钟数、构建次数或流量上限。一般原则是：公共仓库通常可使用 GitHub 托管的标准 runner 和 GitHub Pages，私有仓库的 Actions 可能消耗月度分钟/存储额度，Pages 也存在构建、站点大小、带宽或合理使用方面的限制。准确信息请查阅：

- GitHub Actions 计费与用量：<https://docs.github.com/en/billing/concepts/product-billing/github-actions>
- GitHub Pages 限制：<https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits>
- GitHub Free 套餐与产品可用性：<https://docs.github.com/en/get-started/learning-about-github/githubs-plans>

如果当前账户/仓库的套餐或组织策略与预期不同，以 GitHub 当前官方文档和仓库 Settings 中显示的用量为准。

## 7. 本次交付边界

本次已创建：`.github/workflows/update-data.yml`、`.github/workflows/deploy-pages.yml`、`.github/scripts/check_workflows_structure.py`、`.github/scripts/validate_data.py`、`.github/scripts/seed_staging_data.py`、`.github/scripts/publish_staged_data.py` 和根 `.nojekyll`。两个 workflow 已用临时开发工具 PyYAML 做完整语法解析并检查关键触发/权限；PyYAML 不是项目运行依赖。没有实际在 GitHub 上运行 Actions。仓库尚未真正部署，完成上述网页步骤并成功运行工作流后，才可宣称上线。
