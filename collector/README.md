# 校园竞赛雷达采集框架

仅使用 Python 3 标准库。采集公开 HTML 列表、RSS/Atom 和 JSON feed，并顺序抓取列表中的公开详情页正文。程序不会登录、不会提交验证码、不会伪造 Cookie 或绕过访问控制。

## 快速运行

```powershell
python -m collector --sources collector/sources.json --output <输出目录> --max-records 200
```

`--output` 必须显式传入。开发/测试请使用临时目录，不要用测试命令写入 `docs/data`。部署任务才应显式写 `docs/data`。

试运行（只校验配置，不抓取、不写文件）：

```powershell
python -m collector --sources collector/sources.json --output <临时目录> --dry-run
```
离线 fixture 测试：

```powershell
python -m collector --sources <fixture sources.json> --output <临时目录> --fixture <fixture 目录>
```

fixture 来源使用 `fixture://文件名`，只读本地目录，不联网。

## 默认来源验证状态

`collector/sources.json` 中的六个真实候选来源当前全部为 `enabled: false`、`verified: false`，并附有明确 `verification_note`。
候选包括中国大学生计算机设计大赛、全国大学生信息安全竞赛、全国大学生电子设计竞赛、全国大学生数学建模竞赛、全国大学生广告艺术大赛、中国大学生服务外包创新创业大赛。

Lead 于 2026-10-24 实测过六个列表页 HTTP 200 并检查了 robots.txt；开发期还把六个来源临时启用、每源限 2 条候选做了一次真实采集，采集器正常完成并通过数据契约校验，产出 5 条全部为 pending 的临时 live 记录（未写入 docs/data）。这不等于抓取许可、逐条正文真实性或主办方授权已验证，程序不会把任何默认来源标记为已验证。
默认运行会生成空 live 数据，并在 meta.json / quality-report.json / sources.json 中明确说明无启用来源、未抓取、未核验。空数据不代表没有赛事。

## 输出文件

- `competitions.json`：`schema_version, data_mode, generated_at, notice, record_count, records`
- `sources.json`：`schema_version, generated_at, data_mode, notice, source_count, enabled_count, sources`
- `meta.json`：`schema_version, data_mode, generated_at, last_run, summary, run_history, notice`
- `quality-report.json`：字段完整度、报名状态统计、链接事实统计、中文 warnings
- `run-log.jsonl`：追加写入的中文运行日志，每行一个 UTF-8 JSON 对象

所有 JSON 使用 UTF-8、`ensure_ascii=False`，中文不转义。日期统一为 Asia/Shanghai 的 ISO 8601，例如 `2026-10-24T20:56:20+08:00`；未知日期为 `null`。

## 记录字段

必需字段始终存在，未知为 `null`：

`id, title, organizer, category, competition_level, eligible_participants, team_size, registration_start, registration_deadline, event_start, event_end, description, requirements, official_notice_url, registration_url, source_name, source_url, published_at, fetched_at, last_verified_at, verification_status, registration_status, confidence, content_hash, region, is_demo, missing_fields, verification_notes`

额外字段：`source_id, source_type, canonical_url, verification_history, change_history, link_check, registration_link_check, detail_fetch, source_list_url`
约束：

- `source_url` 是该公告详情 URL；`source_list_url` 另存来源列表页 URL。
- `team_size` 是可读字符串或 `null`，例如 `1-3人`、`不超过5人`。
- `verification_status`: `verified | pending | broken | expired | incomplete`；自动采集默认 `pending`。
- `registration_status`: `open | upcoming | closed | unknown`，仅由明确报名日期动态推导，不由 HTTP 200 推断。
- `is_demo` 在采集输出中恒为 `false`。
- `registration_url` 只接受来源中明确标注为报名入口的 URL；程序不会把通知页或站点首页猜成报名入口。
- `content_hash` 为 sha256；内容变化时保留 `change_history` 并触发 `pending` 人工复核。

## 合规与请求限制

- 先检查目标来源的 `/robots.txt`；明确 `Disallow`、401/403 或无法确认时跳过来源并记录原因。
- 使用明确 `User-Agent`、超时、有限重试和请求间隔。
- 列表项按顺序抓取详情页，不并发，不进行高频请求。
- 单来源/单详情失败只影响该来源/该条记录；历史 live 数据会保留。
- 链接核验只记录 HTTP 事实（200、重定向、超时、403、404、连接错误、疑似 JS 页面），不据此声称报名开放。
- 默认每个来源最多 20 条、每次最多核验 50 个链接。每日任务应保持低请求量。

## 手动公众号入口

```powershell
python -m collector.wechat --url "https://mp.weixin.qq.com/s/..." --output <输出目录>
```

只使用普通 GET 获取公开页。遇到登录、验证码、403、超时或无法提取正文时，写入 `manual-pending.json` 待核验任务；不登录、不提交验证码、不绕过访问限制。成功解析的记录仍为 `pending`。

## 测试

```powershell
python -m unittest discover -s tests/python -v
```

测试全部使用临时目录，不读取或写入 `docs/data`。

## 调度频率与请求间隔

`update_frequency` 在采集器内参与保守调度，而不是仅作为说明（GitHub Actions 的 seed 脚本会保留 live `sources.json` 中的上次成功时间）：
- `daily`：上次成功后约 20 小时内不重复抓取；
- `weekly`：上次成功后约 6 天内不重复抓取；
- `manual`：自动运行默认跳过，只允许人工 `--force` 或单独手动入口；
- 未识别频率：每次运行检查并记录说明。
每个启用来源的实际请求间隔取 `max(全局 --request-delay, source.request_delay_seconds)`，写入 `sources.json.effective_request_delay_seconds` 并记录到 `run-log.jsonl`。GitHub Actions 是每日触发的兜底工作流；即使某个来源被标为 weekly，也只有到期后才真正请求，但工作流本身仍每天检查调度状态。

链接核验分别保存：`link_check`（通知/详情页）和 `registration_link_check`（来源明确给出的报名入口），两者共享 `--max-link-checks` 总次数。HTTP 200 仍只代表可达，不代表报名开放。
