"""collector 命令行入口。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .fetcher import DEFAULT_USER_AGENT
from .run import RunOptions, run_collection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m collector",
        description="校园竞赛雷达公开信息采集器（仅标准库；默认来源均未启用且未验证）。",
    )
    parser.add_argument("--sources", required=False, default="collector/sources.json",
                        help="sources 配置 JSON 路径（默认 collector/sources.json）")
    parser.add_argument("--output", "--output-dir", dest="output", required=True,
                        help="输出目录，例如 docs/data 或临时测试目录；程序不会隐式选择 docs/data")
    parser.add_argument("--max-records", type=int, default=200,
                        help="本次最多新增记录数；历史记录始终保留（默认 200）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只校验配置并显示计划，不抓取、不写任何文件")
    parser.add_argument("--fixture", "--fixtures-dir", dest="fixtures_dir", default=None,
                        help="离线 fixture 目录；仅抓取 fixture:// 地址，不联网")
    parser.add_argument("--no-link-check", action="store_true",
                        help="不进行链接 HTTP 事实核验（仍不代表任何验证）")
    parser.add_argument("--max-link-checks", type=int, default=50,
                        help="本次最多核验链接数（默认 50）")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次请求超时秒数")
    parser.add_argument("--retries", type=int, default=2, help="失败重试次数")
    parser.add_argument("--force", action="store_true",
                        help="忽略 update_frequency 调度限制并允许抓取 manual 来源（用于人工触发）")
    parser.add_argument("--request-delay", type=float, default=1.0,
                        help="同一进程请求之间的最小间隔秒数")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT,
                        help="明确的采集 User-Agent")
    return parser
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = RunOptions(
        sources_path=Path(args.sources),
        output_dir=Path(args.output),
        max_records=args.max_records,
        dry_run=args.dry_run,
        fixtures_dir=Path(args.fixtures_dir) if args.fixtures_dir else None,
        check_links=not args.no_link_check,
        link_check_limit=args.max_link_checks,
        timeout=args.timeout,
        retries=args.retries,
        request_delay=args.request_delay,
        force=args.force,
        user_agent=args.user_agent,
    )
    try:
        outcome = run_collection(options)
    except Exception as exc:
        print(f"采集失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"运行 ID: {outcome.run_id}")
    print(f"状态: {outcome.status}")
    print(outcome.message)
    if outcome.dry_run:
        print("试运行模式：未抓取、未写入任何文件。")
    else:
        print(f"记录数: {len(outcome.records)}")
        print(f"输出文件: {', '.join(outcome.written_paths)}")
    for source in outcome.sources:
        marker = "启用" if source.get("enabled") else "未启用"
        print(
            f"- {source.get('name')} [{marker}] "
            f"状态={source.get('status')} verified={str(source.get('verified')).lower()} "
            f"新增={source.get('records_added', 0)}"
        )
    return 0