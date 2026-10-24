# 数据字段说明（Schema 1.0.0）

> 当前 `docs/data/competitions.json` 为 `data_mode: "live"` 的公开采集数据（2026-10-24 首次采集 5 条）。所有记录仍为 `verification_status: pending`，不得视为官方确认或报名开放。历史演示数据仍可通过 `tools/generate_demo_data.py` 复现，并只用于本地测试与界面演示；所有演示记录必须保持 `is_demo: true` 和全站演示标识。

## 1. 文件布局

| 文件 | 作用 |
| --- | --- |
| `docs/data/competitions.json` | 展示用竞赛数据与数据模式 |
| `docs/data/sources.json` | 信息源状态、最近检查/成功时间与采集结果 |
| `docs/data/meta.json` | 最近运行摘要、统计快照与历史运行 |
| `docs/data/quality-report.json` | 数据质量报告、缺失字段统计、待人工核验列表 |
| `docs/data/run-history.json` | 可读运行历史 |
| `tests/fixtures/competitions.edge-cases.json` | 仅用于测试的边界与重复公告模拟数据 |

所有公开数据均为静态 JSON。浏览器只读取 `docs/data/`，不会写回服务器。

## 2. 顶层对象：competitions.json

```json
{
  "schema_version": "1.0.0",
  "data_mode": "demo",
  "generated_at": "2026-10-24T20:55:27+08:00",
  "notice": "全部记录均为合成演示数据，不是真实赛事。",
  "record_count": 10,
  "records": []
}
```

- `schema_version`：字段契约版本；破坏性改动提升主版本。
- `data_mode`：`demo` 或 `live`；`demo` 时 UI 必须展示明显横幅。
- `generated_at`：生成时间，ISO 8601 且带时区。
- `record_count`：可选；存在时必须等于记录数量。
- `notice`：面向使用者的数据状态提示。

## 3. 单条竞赛记录

每条记录必须始终包含下列键。无法确认的值使用 `null`，并在 `missing_fields` 中列出。前端显示待确认，不得根据经验补全。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 稳定唯一 ID，更新时不可变化 |
| `title` | string | 公告/竞赛名称 |
| `organizer` | string 或 null | 主办方原文摘要，不得猜测 |
| `category` | string | 类别；无法判断用其他并记录缺失 |
| `competition_level` | string | 国家级/省级/校级/国际级/其他/待确认 |
| `region` | string 或 null | 地区，例如全国、浙江省 |
| `eligible_participants` | string 或 null | 适用对象与参赛资格原文摘要 |
| `team_size` | string 或 null | 人可读团队人数，如 3-5 人、个人赛 |
| `registration_start` | ISO string 或 null | 报名开始 |
| `registration_deadline` | ISO string 或 null | 报名截止；状态必须动态计算 |
| `event_start` | ISO string 或 null | 比赛/活动开始 |
| `event_end` | ISO string 或 null | 比赛/活动结束 |
| `description` | string 或 null | 竞赛简介 |
| `requirements` | string 或 null | 作品/材料/参赛要求 |
| `official_notice_url` | URL 或 null | 官方原文通知，独立存储 |
| `registration_url` | URL 或 null | 官方报名入口，独立存储；禁止拼接或猜测 |
| `source_name` | string | 信息源名称 |
| `source_url` | URL 或 null | 被采集的原始公告地址 |
| `published_at` | ISO string 或 null | 原文发布时间 |
| `fetched_at` | ISO string | 采集时间 |
| `last_verified_at` | ISO string 或 null | 核验时间；null 表示尚未核验 |
| `verification_status` | enum | 见第 4 节 |
| `registration_status` | enum | 保存时快照；前端必须按当前时间重新推导 |
| `confidence` | number 0-1 | 保守可信度评分，不是官方保证 |
| `content_hash` | string | 内容 sha256，64 位小写十六进制 |
| `is_demo` | boolean | 模拟数据必须为 true |
| `missing_fields` | string[] | 无法确认的字段名数组 |
| `verification_notes` | string 或 array | 核验说明 |
| `verification_history` | object[]，可选 | 时间、方法、HTTP 状态、备注等核验记录 |
| `change_history` | object[]，可选 | 原文更新与重新核验记录 |
| `source_id` | string，可选 | 关联 `sources.json` 的信息源 ID |
| `source_type` | string，可选 | html_list、rss、atom、json_feed、wechat_manual 等 |

## 4. 枚举与状态规则

`verification_status`：

- `verified`：已核对官方来源且页面可访问；这不等于报名仍开放。
- `pending`：待核验，不得写成官方确认。
- `broken`：通知或报名链接异常、不可访问。
- `expired`：报名已截止或活动已结束。
- `incomplete`：关键字段缺失，尚不足以判断。

`registration_status`：

- `open`：报名窗口内（须有可信起止时间）。
- `upcoming`：尚未开始。
- `closed`：已过截止时间。
- `unknown`：日期缺失或无法确认。

动态规则：若 `registration_deadline` 早于当前时间，UI 必须显示已截止，即使 JSON 保存的是 `open`。日期缺失时显示待确认，不得根据经验补全。

## 5. 时间、链接与可信度

- 全部时间使用 ISO 8601 并显式包含时区，例如 `2026-10-29T23:59:59+08:00`。
- 站点默认时区为 `Asia/Shanghai`。若来源仅提供日期，采集器必须保留日期精度，不能声称具体截止时刻已经确认。
- 官方通知与报名入口分别存入 `official_notice_url` 与 `registration_url`；不得自动拼接或猜测后者。
- HTTP 200 只能说明页面返回成功，不能证明报名开放或内容真实。报名状态由报名窗口和核验状态共同呈现。
- `confidence` 是保守评分，不是平台担保。演示数据即使标记 `verified` 也只用于展示徽标，并在全站横幅和记录徽标中明确标注为模拟数据。

## 6. 前端与自动化约定

- 前端必须用 `docs/data/competitions.json` 的真实载入记录动态计算统计。
- 缺少、空字符串或 null 字段统一显示待确认。
- 收藏、报名进度和备注只存浏览器 `localStorage`；清除浏览器数据会丢失，也不会跨设备同步。
- 采集器合并已有数据时保留历史记录和变更历史；相同公告不得重复发布。
- `tools/validate_data.py` 与自动化工作流检查必需键、时区、枚举、content_hash、重复 id/title/source_url 和统计一致性。
- `tests/fixtures/` 下的模拟数据只供测试使用，不得复制到生产 JSON 后声称真实。

## 7. 示例记录（演示数据节选）

```json
{
  "id": "demo-001",
  "title": "【模拟】全国大学生创新实践挑战赛",
  "organizer": "演示主办方（非真实机构）",
  "category": "创新创业",
  "competition_level": "国家级",
  "eligible_participants": "普通高校全日制本科生、研究生",
  "team_size": "3-5 人",
  "registration_start": "2026-10-01T09:00:00+08:00",
  "registration_deadline": "2026-10-29T23:59:59+08:00",
  "official_notice_url": "https://example.com/demo-notice/demo-001",
  "registration_url": "https://example.com/demo-register-001",
  "source_name": "演示信息源（合成，非真实来源）",
  "source_url": "https://example.com/demo-fixture/demo-001",
  "published_at": "2026-10-20T10:00:00+08:00",
  "fetched_at": "2026-10-24T20:00:00+08:00",
  "last_verified_at": null,
  "verification_status": "verified",
  "registration_status": "open",
  "confidence": 0.82,
  "content_hash": "64 位小写 sha256",
  "is_demo": true,
  "missing_fields": [],
  "verification_notes": "模拟核验状态，未访问真实赛事网站。"
}
```

完整字段和真实文件以 `docs/data/competitions.json` 及 `tools/validate_data.py` 为准。
