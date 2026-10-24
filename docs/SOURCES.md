# 信息源配置与合规说明

## 1. 原则

- 只访问无需登录即可阅读的公开页面。
- 遵守 robots.txt；明确禁止时跳过并记录原因。
- 不绕过登录、验证码、付费墙、访问控制或反爬机制。
- 不使用账号模拟、代理轮换或高频请求。
- 微信公众号文章不作为批量抓取源；只支持维护者手动提交公开链接。
- 页面 HTTP 200 只代表当时可访问，不代表主办方授权、报名开放或内容无误。
- 采集结果默认均为 `verification_status: pending`，除非经过人工核验。演示数据使用 `data_mode: demo` 并在界面全程标记。

## 2. 配置文件

默认配置位于 `collector/sources.json`，CLI 也可通过 `--sources` 指向其他 JSON：

```bash
python -m collector \
  --sources collector/sources.json \
  --output docs/data \
  --max-records 200 \
  --max-link-checks 30
```

顶层对象：

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-10-24T21:06:22+08:00",
  "notice": "候选来源均 enabled=false、verified=false。",
  "sources": []
}
```

单个来源字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 稳定唯一标识，仅限字母、数字、点、下划线、短横线 |
| `name` | 是 | 展示名称 |
| `domain` | 是 | 站点域名 |
| `list_url` | 是 | 公告列表、RSS/Atom 或 JSON feed 地址 |
| `parser` | 是 | `html`、`rss`、`atom`、`json` 或 `auto` |
| `update_frequency` | 是 | 建议频率，例如 `daily`、`weekly`、`manual` |
| `enabled` | 是 | 布尔值；只有 `true` 才会抓取 |
| `source_type` | 是 | official、university、manual、fixture 等描述性值 |
| `verified` | 否 | 是否已由人工核实来源身份与抓取许可；默认 false |
| `verification_note` | 条件 | `verified=true` 时必须填写证据说明 |
| `url_include_pattern` | 否 | 只保留匹配此正则的链接 |
| `title_include_keywords` | 否 | 标题必须包含任一关键词 |
| `title_exclude_keywords` | 否 | 标题包含任一关键词则剔除 |
| `max_items_per_run` | 否 | 单来源单次最多处理条数 |
| `max_records` | 否 | 兼容的条数上限 |
| `request_delay_seconds` | 否 | 该来源请求最小间隔 |
| `items_path` | 否 | JSON feed 中记录数组的点分路径，例如 `data.items` |
| `is_demo` | 否 | 演示来源必须为 true |

## 3. 解析器

- `html`：解析公开 HTML 列表中的候选链接，识别容器上下文和内嵌日期。
- `rss` / `atom`：解析标准订阅源标题、链接、发布时间和摘要。
- `json`：读取 JSON Feed/API 中的条目，可用 `items_path` 指定数组位置。
- `auto`：根据响应类型或内容选择 HTML/RSS/Atom/JSON 解析器。

每个来源拥有独立过滤规则与条数上限。增加来源不需要修改核心调度器；特殊网站可新增独立解析器并在 `PARSER_ALIASES` 注册。示例：

```json
{
  "id": "example_university_notices",
  "name": "示例高校竞赛通知",
  "domain": "competitions.example.edu",
  "list_url": "https://competitions.example.edu/notices",
  "parser": "html",
  "update_frequency": "daily",
  "enabled": false,
  "source_type": "university",
  "verified": false,
  "url_include_pattern": "/notice/\\d+\\.html",
  "title_include_keywords": ["竞赛", "大赛", "报名", "征集"],
  "title_exclude_keywords": ["招聘", "获奖名单"],
  "max_items_per_run": 10,
  "request_delay_seconds": 2.0
}
```

启用一个来源前至少完成：

1. 确认页面为公开官方/主办方信息源，且抓取不违反网站条款。
2. 阅读 robots.txt，并用真实请求确认频率合理。
3. 人工打开 2 到 3 个样本链接，确认列表结构与正文解析正确。
4. 核对时区、日期规则、缺失字段和官方报名入口是否分开存储。
5. 保持 `verified=false`，除非已经完成人工来源核验；若确需设为 true，必须填写 `verification_note`。

## 4. 实际核查过的候选来源

以下结果由项目开发过程中于 2026-10-24 用公开 HTTP 请求实测，**只能说明当时列表页可达，不能说明抓取许可、正文内容或活动仍有效**。所有候选默认 `enabled=false`、`verified=false`。

| 来源 | 列表页 | 实测 | robots.txt | 结论 |
| --- | --- | --- | --- | --- |
| 中国大学生计算机设计大赛 | `https://jsjds.blcu.edu.cn/dsdt.htm` | HTTP 200 | 404（无规则文件） | 候选，未人工确认许可/解析 |
| 全国大学生信息安全竞赛 | `http://www.ciscn.cn/announcement` | HTTP 200 | 200，Allow | 候选，未人工确认许可/解析 |
| 全国大学生电子设计竞赛 | `https://www.nuedc-training.com.cn/index/news/index` | HTTP 200 | 404（无规则文件） | 候选，未人工确认许可/解析 |
| 全国大学生数学建模竞赛 | `https://www.mcm.edu.cn/` | HTTP 200 | 200，空规则 | 候选，列表页结构仍需验证 |
| 全国大学生广告艺术大赛 | `https://www.sun-ada.net/home/newss.html` | HTTP 200 | 200，Allow | 候选，未人工确认许可/解析 |
| 中国大学生服务外包创新创业大赛 | `https://www.fwwb.org.cn/public/index` | HTTP 200 | 404（无规则文件） | 候选，未人工确认许可/解析 |

明确排除：

- `https://cpipc.acge.org.cn/`：robots.txt 为 `Disallow: /`，不默认采集。
- 微信公众号文章：不批量抓取；只接收公开链接并保存待核验任务。
- 需要登录、验证码、JavaScript 反爬或非公开接口的页面：不绕过。

## 5. 运行状态与核验

来源状态包括禁用、等待检查、抓取成功、空结果、抓取失败、解析失败、配置错误、robots 阻止和试运行。每个来源独立执行，失败不会中断其他来源。

链接核验区分：

- HTTP 2xx 可达
- 3xx 重定向
- 401/403 禁止访问
- 404 未找到
- 超时
- 连接错误
- 疑似需要 JavaScript
- 其他 HTTP/服务器错误

HTTP 2xx 只会记录为可达，不会自动将报名入口标记为有效，也不会自动设置 `verified=true`。截止日期已过时，前端优先显示已截止；日期缺失时显示待确认。

## 6. 手动公众号公开链接

合规入口：

```bash
python -m collector.wechat \
  --url "https://mp.weixin.qq.com/s/..." \
  --output docs/data
```

若公开页面可合法读取，则提取标题与摘要，保存原始链接和 `pending` 核验状态；若无法读取，则写入待核验任务，不视为官方确认。程序不会绕过登录、验证码或微信访问限制，不会尝试批量枚举文章。

## 7. 2026-10-24 开发期实际采集验证

这一节只记录真实执行事实，不把候选来源提升为 `verified`。

- 六个候选列表页均实际返回 HTTP 200。
- robots.txt 核查：`ciscn` 与 `sun_ada` 返回 200 Allow；`mcm` 返回 200 空规则；`jsjds`、`nuedc`、`fwwb` 返回 404（无规则文件）。程序对 401/403、超时和不可确认情况采取保守跳过。
- 将六个来源临时设为启用、每源最多 2 条候选后执行真实采集：命令退出码 0，耗时约 21.5 秒；3 个来源成功解析，3 个来源因当前公告不符合赛事过滤条件而返回空结果，0 个来源网络失败。
- 本次输出 5 条 live 记录，全部 `verification_status=pending` 且 `verified` 来源数为 0；5 个官方通知链接进行了 HTTP 事实检查，无一条被宣告为报名开放或官方确认。
- 采集器完成了列表解析、顺序详情正文抓取、发布/正文时间提取、团队人数与适用对象保守抽取、HTTP 链接事实记录以及数据契约校验。
- 结果使用 `.github/scripts/validate_data.py` 校验通过：5 records、6 sources、20 log entries。
- 由于来源许可、逐条正文真实性、主办方授权和人工核验尚未确认，这 5 条临时结果只保存在开发临时目录，没有写入或替换 `docs/data/` 的演示数据，也没有把任何候选来源设为启用或已验证。

因此当前结论是：来源列表页可达性已实际核查，采集管线在真实公开页面上跑通；但不存在已人工验证可用的生产信息源，上线前仍需维护者逐源复核许可与解析结果。
