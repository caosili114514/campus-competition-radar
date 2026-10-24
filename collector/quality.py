"""数据质量报告与中文可读摘要。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .link_checker import LINK_STATUS_LABELS
from .schema import (
    MISSING_FIELD_CANDIDATES,
    REGISTRATION_STATUSES,
    VERIFICATION_STATUSES,
    now_iso,
)


def _coverage(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    present = sum(1 for record in records if record.get(field) is not None)
    total = len(records)
    return {
        "present": present,
        "total": total,
        "percent": round(present / total * 100, 1) if total else 0.0,
    }
def build_quality_report(records: list[dict[str, Any]], sources: list[dict[str, Any]], *,
                         generated_at: str | None = None,
                         data_mode: str = "live") -> dict[str, Any]:
    total = len(records)
    verification_counts = Counter(record.get("verification_status") or "pending" for record in records)
    registration_counts = Counter(record.get("registration_status") or "unknown" for record in records)
    link_counts: Counter[str] = Counter()
    registration_link_counts: Counter[str] = Counter()
    for record in records:
        fact = record.get("link_check")
        link_counts[(fact or {}).get("status") or "not_checked"] += 1
        reg_fact = record.get("registration_link_check")
        registration_link_counts[(reg_fact or {}).get("status") or "not_checked"] += 1

    links_checked_total = (
        total - link_counts.get("not_checked", 0)
        + total - registration_link_counts.get("not_checked", 0)
    )
    missing_counts = {
        field: sum(1 for record in records if field in (record.get("missing_fields") or []))
        for field in MISSING_FIELD_CANDIDATES
    }
    field_coverage = {field: _coverage(records, field) for field in MISSING_FIELD_CANDIDATES}
    enabled = [source for source in sources if source.get("enabled")]
    success_statuses = {"success", "empty"}
    success = [source for source in enabled if source.get("status") in success_statuses]
    failed_statuses = {"fetch_failed", "parse_failed", "config_error"}
    failed = [source for source in enabled if source.get("status") in failed_statuses]
    skipped_statuses = {"not_due", "manual_skipped", "robots_blocked"}
    skipped = [source for source in enabled if source.get("status") in skipped_statuses]
    verified_sources = [source for source in sources if source.get("verified") is True]
    pending_verification = sum(
        1 for record in records
        if record.get("verification_status") in ("pending", "incomplete")
    )

    warnings: list[str] = []
    if not enabled:
        warnings.append("当前没有启用的信息源；本次未抓取任何来源，也未做链接核验。空数据不会被解释为没有赛事。")
    if verified_sources == []:
        warnings.append("没有已验证信息源；所有来源和记录均不得标注为官方确认或已核实。")
    if records:
        warnings.append("所有自动采集记录均需人工核验；registration_status 仅由明确日期推导，不由链接状态推断。")
    if link_counts.get("ok"):
        warnings.append(f"{link_counts['ok']} 条链接仅记录为 HTTP 可达，不代表报名开放或报名有效。")
    if link_counts.get("redirect"):
        warnings.append(f"{link_counts['redirect']} 条链接发生重定向；跳转目标需人工确认是否为同一公开通知。")
    if link_counts.get("js_required_page"):
        warnings.append(f"{link_counts['js_required_page']} 条链接疑似依赖 JavaScript 渲染，内容未能可靠核验。")
    if registration_link_counts.get("ok"):
        warnings.append(f"{registration_link_counts['ok']} 条报名入口仅记录为 HTTP 可达，不代表报名开放或报名有效。")
    if registration_link_counts.get("not_found"):
        warnings.append(f"{registration_link_counts['not_found']} 条报名入口返回 404，记录已标记 broken，需人工确认。")
    if registration_link_counts.get("js_required_page"):
        warnings.append(f"{registration_link_counts['js_required_page']} 条报名入口疑似依赖 JavaScript，不能确认报名页内容。")
    if failed:
        warnings.append(f"{len(failed)} 个启用来源抓取或解析失败；其余来源与历史记录已尽量保留。")
    if skipped:
        warnings.append(f"{len(skipped)} 个启用来源因 update_frequency、manual 或 robots.txt 规则被跳过；不代表来源无效。")
    if records and missing_counts.get("registration_url") == total:
        warnings.append("所有记录的报名入口均待确认；程序没有根据通知页或首页猜测报名 URL。")
    message = (
        f"共 {total} 条记录；待人工核验 {pending_verification} 条；"
        f"来源 {len(sources)} 个（启用 {len(enabled)}，成功 {len(success)}，失败 {len(failed)}）；"
        f"链接事实已检查 {links_checked_total} 次。"
    )
    if total == 0 and not enabled:
        message += " 本次没有启用来源，输出为空 live 数据。"

    return {
        "schema_version": "1.0.0",
        "data_mode": data_mode,
        "generated_at": generated_at or now_iso(),
        "summary": {
            "message": message,
            "record_count": total,
            "pending_verification_count": pending_verification,
            "verified_record_count": verification_counts.get("verified", 0),
        },
        "summary_text": message,        "totals": {
            "record_count": total,
            "verified_record_count": verification_counts.get("verified", 0),
            "pending_verification_count": pending_verification,
            "source_count": len(sources),
            "enabled_source_count": len(enabled),
            "successful_source_count": len(success),
            "failed_source_count": len(failed),
            "skipped_source_count": len(skipped),
            "disabled_source_count": len(sources) - len(enabled),
            "links_checked": links_checked_total,
        },
        "verification_status_counts": {key: verification_counts.get(key, 0) for key in VERIFICATION_STATUSES},
        "registration_status_counts": {key: registration_counts.get(key, 0) for key in REGISTRATION_STATUSES},
        "field_coverage": field_coverage,
        "missing_field_counts": missing_counts,
        "link_check_summary": {
            key: link_counts.get(key, 0)
            for key in list(LINK_STATUS_LABELS) + ["not_checked"]
        },
        "registration_link_check_summary": {
            key: registration_link_counts.get(key, 0)
            for key in list(LINK_STATUS_LABELS) + ["not_checked"]
        },
        "source_summary": {
            "total": len(sources),
            "enabled": len(enabled),
            "success": len(success),
            "failed": len(failed),
            "skipped": len(skipped),
            "disabled": len(sources) - len(enabled),
            "verified": len(verified_sources),
            "needs_manual_verification": len(sources) - len(verified_sources),
        },
        "warnings": warnings,
        "notice": "质量报告描述采集与字段完整度，不构成对赛事真实性、报名开放状态或主办方授权的认证。",
    }