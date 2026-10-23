#!/usr/bin/env python3
"""从 OptiScaler 源码抽取界面字符串，输出与 extracted_strings.json 同构的 JSON。

默认行为与旧版脚本完全一致（已用 2026-10 的 OptiScaler-master 验证：1569 条 /
2020 处，与 extracted_strings.json 逐字段相同），同时新增以下能力：

  --src               指定源码目录（仓库根或 OptiScaler/menu），默认本仓库
  --include-headers   同时扫描 *.h / *.hpp（默认只 *.cpp）
  --comments          include（默认，兼容现有 JSON）/ skip（剔除仅注释项）
  --max-locations     每条字符串记录的出现位置上限，默认 6
  --ctx-chars         上下文截断长度，默认 160
  --min-len           最小字面量长度，默认 2
  --sort              count（默认）/ value / file

示例：
  python tools_cn/extract_strings.py
  python tools_cn/extract_strings.py --src "C:/ALL/下载/压缩/OptiScaler-master" \
      --out tools_cn/strings_extracted.json --stats
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cstr


def build(src_dir: Path, include_headers: bool, min_len: int, ctx_chars: int,
          max_locations: int, comments: str, sort_key: str):
    files = cstr.list_sources(src_dir, include_headers=include_headers)
    if not files:
        raise SystemExit(f"错误：{src_dir} 下没有找到可扫描的源文件")

    entries = {}
    per_file = {}

    for f in files:
        literals = cstr.scan_file(f, min_len=min_len, ctx_chars=ctx_chars)
        per_file[f.name] = len(literals)
        for lit in literals:
            if comments == "skip" and lit.in_comment:
                continue
            entry = entries.get(lit.value)
            if entry is None:
                entry = {"value": lit.value, "count": 0, "files": []}
                entries[lit.value] = entry
            entry["count"] += 1
            if len(entry["files"]) < max_locations:
                entry["files"].append(
                    {"file": f.name, "line": lit.line, "ctx": lit.ctx, "comment": lit.in_comment}
                )

    items = list(entries.values())

    for it in items:
        # 若所有记录位置都是注释，则保留 comment 标记供下游判断
        it["comment_only"] = all(loc["comment"] for loc in it["files"])

    if sort_key == "value":
        items.sort(key=lambda x: (-x["count"], x["value"]))
    elif sort_key == "file":
        items.sort(key=lambda x: (x["files"][0]["file"], x["files"][0]["line"]))
    else:
        items.sort(key=lambda x: -x["count"])

    return items, per_file


def main() -> None:
    ap = argparse.ArgumentParser(description="抽取 OptiScaler 源码中的字符串字面量")
    ap.add_argument("--src", help="源码目录（仓库根或 OptiScaler/menu），默认本仓库")
    ap.add_argument("--out", default=str(cstr.TOOLS_DIR / "strings_extracted.json"),
                    help="输出 JSON 路径")
    ap.add_argument("--include-headers", action="store_true", help="同时扫描 *.h / *.hpp")
    ap.add_argument("--comments", choices=["include", "skip"], default="include",
                    help="是否保留仅出现在注释中的字符串，默认 include（兼容现有 JSON）")
    ap.add_argument("--max-locations", type=int, default=cstr.DEFAULT_MAX_LOCATIONS,
                    help=f"每条字符串记录的位置上限，默认 {cstr.DEFAULT_MAX_LOCATIONS}")
    ap.add_argument("--ctx-chars", type=int, default=cstr.DEFAULT_CTX_CHARS,
                    help=f"ctx 截断长度，默认 {cstr.DEFAULT_CTX_CHARS}")
    ap.add_argument("--min-len", type=int, default=cstr.DEFAULT_MIN_LEN,
                    help=f"最小字面量长度，默认 {cstr.DEFAULT_MIN_LEN}")
    ap.add_argument("--sort", choices=["count", "value", "file"], default="count",
                    help="输出排序方式，默认 count（出现次数降序）")
    ap.add_argument("--stats", action="store_true", help="打印每个文件的出现次数统计")
    ap.add_argument("--no-comment-flag", action="store_true",
                    help="不写入 comment / comment_only 字段（输出与旧版 JSON 完全同构）")
    args = ap.parse_args()

    src_dir = cstr.resolve_menu_dir(args.src)
    items, per_file = build(
        src_dir,
        include_headers=args.include_headers,
        min_len=args.min_len,
        ctx_chars=args.ctx_chars,
        max_locations=args.max_locations,
        comments=args.comments,
        sort_key=args.sort,
    )

    comment_only = sum(1 for it in items if it.get("comment_only"))
    occurrences = sum(it["count"] for it in items)

    if args.no_comment_flag:
        for it in items:
            it.pop("comment_only", None)
            for loc in it["files"]:
                loc.pop("comment", None)

    out = Path(args.out)
    if not out.is_absolute():
        out = (cstr.TOOLS_DIR / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"源码目录: {src_dir}")
    print(f"扫描文件: {len(per_file)} 个 -> {', '.join(sorted(per_file))}")
    if args.stats:
        for name, cnt in sorted(per_file.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<24} {cnt:5d} 处")
    print(f"唯一字符串: {len(items)}")
    print(f"出现次数  : {occurrences}")
    print(f"仅注释项  : {comment_only} 条（翻译时可忽略，--comments skip 可剔除）")
    print(f"已写入    : {out}")


if __name__ == "__main__":
    main()
