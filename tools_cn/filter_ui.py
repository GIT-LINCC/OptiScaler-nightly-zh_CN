#!/usr/bin/env python3
"""把抽取出的字符串分成"界面文本 / 非界面文本"，生成便于人工评审的清单。

用法：
  python tools_cn/filter_ui.py                       # 用 tools_cn/strings_extracted.json
  python tools_cn/filter_ui.py --strings "C:/ALL/下载/压缩/extracted_strings.json" \
      --out tools_cn/strings_review.txt --show 200

输出文件分三段：UI 字符串、非 UI 字符串、仅出现在注释中的字符串。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cstr

UI_CTX = re.compile(
    r"ImGui::(Text|Button|Checkbox|Slider|Combo|BeginCombo|Selectable|Input|ColorEdit|ColorPicker|"
    r"RadioButton|BulletText|LabelText|CollapsingHeader|SeparatorText|InputText|DragInt|DragFloat)|"
    r"ShowHelpMarker|ShowTooltip|PopulateCombo|AddDLSS|AddResourceBarrier|ScopedCollapsingHeader|"
    r"SeparatorTextEx|SetTooltip|BeginMenu|MenuItem|TreeNode|OpenWiki|BeginChild|StatusFlag"
)


def load(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or (data and "value" not in data[0]):
        raise SystemExit(f"错误：{path} 不是抽取格式（应为含 value/count/files 的对象数组）")
    return data


def is_ui(item: dict) -> bool:
    return any(UI_CTX.search(f.get("ctx", "")) for f in item.get("files", []))


def is_comment_only(item: dict) -> bool:
    locs = item.get("files", [])
    if not locs:
        return False
    if "comment" in locs[0]:
        return all(f.get("comment") for f in locs) and len(locs) == item.get("count", len(locs))
    return all(f.get("ctx", "").lstrip().startswith("//") for f in locs)


def dump(title: str, items: list, limit: int) -> list:
    lines = [f"=== {title} ({len(items)}) ==="]
    for it in sorted(items, key=lambda x: x["value"]):
        f0 = it["files"][0] if it["files"] else {"file": "?", "line": 0, "ctx": ""}
        lines.append(f'{it["count"]:4d} | {it["value"]!r}')
        lines.append(f"      {f0['file']}:{f0['line']}: {f0['ctx']}")
    lines.append("")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description="按界面/非界面拆分字符串清单")
    ap.add_argument("--strings", help="字符串 JSON，默认 tools_cn/strings_extracted.json")
    ap.add_argument("--out", default=str(cstr.TOOLS_DIR / "strings_review.txt"), help="输出文本路径")
    ap.add_argument("--show", type=int, default=0, help="同时打印前 N 条 UI 字符串（默认不打印）")
    args = ap.parse_args()

    db_path = cstr.resolve_strings_db(args.strings)
    items = load(db_path)

    comments = [it for it in items if is_comment_only(it)]
    rest = [it for it in items if not is_comment_only(it)]
    ui_items = [it for it in rest if is_ui(it)]
    non_ui = [it for it in rest if not is_ui(it)]

    lines = [f"# 来源: {db_path}", f"# 总计: {len(items)} 条", ""]
    lines += dump("UI STRINGS", ui_items, args.show)
    lines += dump("NON-UI STRINGS", non_ui, args.show)
    lines += dump("COMMENT-ONLY STRINGS（可忽略）", comments, args.show)

    out = Path(args.out)
    if not out.is_absolute():
        out = (cstr.TOOLS_DIR / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    print(f"来源: {db_path}")
    print(f"UI: {len(ui_items)}, NON-UI: {len(non_ui)}, 仅注释: {len(comments)}")
    print(f"已写入: {out}")
    if args.show:
        print()
        for it in sorted(ui_items, key=lambda x: -x["count"])[: args.show]:
            f0 = it["files"][0]
            print(f'{it["count"]:4d} | {it["value"]!r} @ {f0["file"]}:{f0["line"]}')


if __name__ == "__main__":
    main()
