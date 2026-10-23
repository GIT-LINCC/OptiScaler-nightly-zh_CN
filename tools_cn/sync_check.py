#!/usr/bin/env python3
"""同步核对：对比"已抽取的字符串 JSON"与"最新源码"，并审计翻译字典。

三件事：
  1) 结构核对：JSON 里的字符串集合、出现次数、行号/上下文是否与最新源码一致
  2) 字典覆盖：最新源码中的字符串有多少已被字典覆盖，缺的按"界面文本/日志格式串"分类
  3) 字典过期：字典里有多少键在源码中已不存在（旧版界面文字，可清理）

示例：
  python tools_cn/sync_check.py                                  # 用本仓库源码核对
  python tools_cn/sync_check.py --src "C:/ALL/下载/压缩/OptiScaler-master" \
      --strings "C:/ALL/下载/压缩/extracted_strings.json" --json report.json
  python tools_cn/sync_check.py --src ... --strings ... --write-db   # 用最新源码刷新 JSON

退出码：0 = 一致；1 = 存在漂移（配合 --strict，可用于 CI）
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cstr

# 明显的日志/调试/非界面文本特征
LOG_PATTERNS = re.compile(
    r"\{[0-9A-Za-z_]*:?X?\}|"
    r"\berror\b|\bfailed\b|\bresult:|\bcaptured\b|\bcount\b|"
    r"%[0-9\.]*[dflus]|"
    r"LOG_|::|Handle|SwapChain|swapchain|pSwap|vk[A-Z]|ImGui_Impl|"
    r"PWSTR|HWND|CommandQueue|CommandList|allocator|Fence|Semaphore|Descriptor|"
    r"Backbuffer|_vulkanObjects|\{ADEC",
    re.IGNORECASE,
)

# 界面文本判定：出现在 ImGui 调用、选项表或状态标记里
UI_PATTERNS = re.compile(
    r"ImGui::(Text|TextWrapped|TextDisabled|TextColored|Button|Checkbox|SliderFloat|"
    r"SliderInt|Combo|BeginCombo|MenuItem|BeginMenu|Selectable|InputInt|InputText|"
    r"CollapsingHeader|BeginTabItem|TreeNodeEx|SetTooltip|ProgressBar|RadioButton|"
    r"BeginTable|TableSetupColumn|BulletText|LabelText|SeparatorText)|"
    r"ScopedCollapsingHeader|ShowTooltip|ShowHelpMarker|AddOption|StatusFlag|"
    r"PopulateCombo|OpenWiki|TextLink"
)


def load_db(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or (data and "value" not in data[0]):
        raise SystemExit(f"错误：{path} 不是抽取格式（应为含 value/count/files 的对象数组）")
    return data


def extract(src_dir: Path, include_headers: bool, keep_comments: bool) -> list:
    import extract_strings

    items, _ = extract_strings.build(
        src_dir,
        include_headers=include_headers,
        min_len=cstr.DEFAULT_MIN_LEN,
        ctx_chars=cstr.DEFAULT_CTX_CHARS,
        max_locations=cstr.DEFAULT_MAX_LOCATIONS,
        comments="include" if keep_comments else "skip",
        sort_key="count",
    )
    return items


IDENT_LIKE = re.compile(r"^[\w\./\\\-+%#]+$")


IDENT_LIKE = re.compile(r"^[\w\./\\\-+%#]+$")
CAMEL_ID = re.compile(r"^[a-z][A-Za-z0-9_]*$")


def classify(entry: dict) -> str:
    """把一条字符串归类：comment / log / ui / other。

    ui    = 真正的界面文本（ImGui 标签、选项表文字、状态标记）
    log   = 日志、调试输出、错误码格式串
    other = 文件名、内部标识符、ImGui ID、纯符号等非界面文本
    """
    value = entry["value"]
    ctx = entry["files"][0]["ctx"] if entry.get("files") else ""
    stripped = value.strip()

    if entry.get("comment_only") or ctx.lstrip().startswith("//"):
        return "comment"
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", stripped):
        return "other"                      # 纯符号/分隔符/占位符
    if stripped.startswith("##"):
        return "other"                      # ImGui 内部 ID，不出现在界面上
    if LOG_PATTERNS.search(value) or "LOG_" in ctx:
        return "log"
    if stripped.startswith(("http://", "https://")):
        return "other"                      # 链接，不翻译
    if re.search(r"\.(dll|exe|ini|json|log|txt|h|cpp)$", stripped, re.IGNORECASE):
        return "other"                      # 文件名，不翻译
    if " " not in stripped and CAMEL_ID.match(stripped):
        return "other"                      # lowerCamelCase 内部 ID
    if UI_PATTERNS.search(ctx):
        return "ui"
    if " " not in stripped and IDENT_LIKE.match(stripped):
        return "other"
    return "ui"


def compare_db(db: list, fresh: list) -> dict:
    """对比 JSON 与最新抽取结果，返回差异明细。"""
    old = {it["value"]: it for it in db}
    new = {it["value"]: it for it in fresh}

    added = [new[v] for v in new.keys() - old.keys()]          # 源码新增
    removed = [old[v] for v in old.keys() - new.keys()]        # 源码已删除
    changed_count = []
    changed_loc = []

    for v in old.keys() & new.keys():
        o, n = old[v], new[v]
        if o["count"] != n["count"]:
            changed_count.append({"value": v, "old": o["count"], "new": n["count"]})
        o0, n0 = o["files"][0], n["files"][0]
        if (o0["file"], o0["line"]) != (n0["file"], n0["line"]) or o0["ctx"] != n0["ctx"]:
            changed_loc.append({
                "value": v,
                "old": f"{o0['file']}:{o0['line']}",
                "new": f"{n0['file']}:{n0['line']}",
            })

    return {
        "db_unique": len(old), "db_occurrences": sum(x["count"] for x in db),
        "src_unique": len(new), "src_occurrences": sum(x["count"] for x in fresh),
        "added": sorted(added, key=lambda x: -x["count"]),
        "removed": sorted(removed, key=lambda x: -x["count"]),
        "changed_count": changed_count,
        "changed_location": changed_loc,
        "identical": not (added or removed or changed_count or changed_loc),
    }


def audit_dict(dictionary: dict, fresh: list) -> dict:
    """审计字典与最新源码的匹配情况。"""
    src_values = {it["value"] for it in fresh}
    missing = [it for it in fresh if it["value"] not in dictionary]
    stale = [k for k in dictionary if k not in src_values]

    buckets = {"ui": [], "log": [], "comment": [], "other": []}
    for it in missing:
        buckets[classify(it)].append(it)

    stale_identity = [k for k in stale if dictionary[k] == k]
    stale_real = [k for k in stale if dictionary[k] != k]

    all_buckets = {"ui": 0, "log": 0, "comment": 0, "other": 0}
    for it in fresh:
        all_buckets[classify(it)] += 1

    return {
        "dict_entries": len(dictionary),
        "src_buckets": all_buckets,
        "src_unique": len(fresh),
        "covered": len(fresh) - len(missing),
        "missing_total": len(missing),
        "missing_ui": buckets["ui"],
        "missing_log": buckets["log"],
        "missing_comment": buckets["comment"],
        "missing_other": buckets["other"],
        "stale_total": len(stale),
        "stale_real": stale_real,
        "stale_identity": stale_identity,
    }


def print_report(diff: dict, audit: dict, dictionary: dict, top: int) -> None:
    print("=" * 72)
    print("一、JSON 与最新源码的一致性")
    print("-" * 72)
    print(f"  已有 JSON : {diff['db_unique']} 条 / {diff['db_occurrences']} 处")
    print(f"  最新源码 : {diff['src_unique']} 条 / {diff['src_occurrences']} 处")
    if diff["identical"]:
        print("  结论：完全一致，JSON 无需更新（行号、上下文、出现次数均未漂移）")
    else:
        print(f"  结论：存在差异 -> 新增 {len(diff['added'])} 条 / 删除 "
              f"{len(diff['removed'])} 条 / 次数变化 {len(diff['changed_count'])} 条 / "
              f"位置漂移 {len(diff['changed_location'])} 条")
        for item in diff["added"][:top]:
            loc = item["files"][0]
            print(f"    + [{item['count']}] {item['value']!r} @ {loc['file']}:{loc['line']}")
        for item in diff["removed"][:top]:
            loc = item["files"][0]
            print(f"    - [{item['count']}] {item['value']!r} @ {loc['file']}:{loc['line']}")
        for c in diff["changed_count"][:top]:
            print(f"    ~ {c['value']!r} 次数 {c['old']} -> {c['new']}")
        for c in diff["changed_location"][:top]:
            print(f"    > {c['value']!r} 位置 {c['old']} -> {c['new']}")

    print()
    print("=" * 72)
    print("二、翻译字典覆盖情况")
    print("-" * 72)
    covered = audit["covered"] / audit["src_unique"] * 100 if audit["src_unique"] else 0.0
    print(f"  字典条目   : {audit['dict_entries']}")
    print(f"  源码字符串 : {audit['src_unique']}，已覆盖 {audit['covered']}（{covered:.1f}%）")
    b = audit["src_buckets"]
    ui_total = b["ui"]
    ui_missing = len(audit["missing_ui"])
    if ui_total:
        print(f"  界面文本   : {ui_total - ui_missing}/{ui_total} 已翻译"
              f"（{(ui_total - ui_missing) * 100 / ui_total:.1f}%），"
              f"未翻译 {ui_missing} 条")
    print(f"  非界面文本 : 日志格式串 {b['log']} / 注释 {b['comment']} / 其他 {b['other']}（无需翻译）")
    print(f"  缺失       : {audit['missing_total']} 条 -> "
          f"界面文本 {len(audit['missing_ui'])} / 日志格式串 {len(audit['missing_log'])} / "
          f"注释 {len(audit['missing_comment'])} / 其他 {len(audit['missing_other'])}")
    if audit["missing_ui"]:
        print("  建议补译（界面文本）：")
        for it in sorted(audit["missing_ui"], key=lambda x: -x["count"])[:top]:
            loc = it["files"][0]
            print(f"    ? [{it['count']}] {it['value']!r} @ {loc['file']}:{loc['line']}")
    if audit["missing_log"]:
        print(f"  （另有 {len(audit['missing_log'])} 条日志/格式串，通常不需要翻译）")

    print()
    print("=" * 72)
    print("三、字典过期条目")
    print("-" * 72)
    print(f"  源码中已不存在的键: {audit['stale_total']} 条 "
          f"（其中恒等映射 {len(audit['stale_identity'])} 条，可安全清理）")
    for k in audit["stale_real"][:top]:
        print(f"    x {k!r} -> {dictionary[k]!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description="核对字符串 JSON / 字典 与最新源码的同步状态")
    ap.add_argument("--src", help="源码目录（仓库根或 OptiScaler/menu）")
    ap.add_argument("--strings", help="已抽取的字符串 JSON，默认 tools_cn/strings_extracted.json")
    ap.add_argument("--dict", dest="dict_path", help="翻译字典，默认 dict_v10.json")
    ap.add_argument("--include-headers", action="store_true", help="同时扫描 *.h / *.hpp")
    ap.add_argument("--keep-comments", action="store_true",
                    help="抽取时保留注释内字符串（默认保留，符合现有 JSON 语义）")
    ap.add_argument("--top", type=int, default=15, help="每类最多打印条数，默认 15")
    ap.add_argument("--json", dest="json_out", help="把结果写入 JSON 报告")
    ap.add_argument("--write-db", action="store_true",
                    help="用最新源码抽取结果覆盖 --strings 指向的 JSON")
    ap.add_argument("--strict", action="store_true", help="存在漂移时以退出码 1 结束")
    args = ap.parse_args()

    src_dir = cstr.resolve_menu_dir(args.src)
    db_path = cstr.resolve_strings_db(args.strings)
    dict_path = cstr.resolve_dict(args.dict_path)

    db = load_db(db_path)
    fresh = extract(src_dir, args.include_headers, keep_comments=True)
    diff = compare_db(db, fresh)
    dictionary = cstr.load_dict(dict_path)
    audit = audit_dict(dictionary, fresh)

    print(f"源码目录: {src_dir}")
    print(f"字符串库: {db_path}")
    print(f"翻译字典: {dict_path}（{len(dictionary)} 条）")
    print()
    print_report(diff, audit, dictionary, args.top)

    if args.write_db:
        db_path.write_text(json.dumps(fresh, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已用最新源码刷新：{db_path}")

    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute():
            out = (cstr.TOOLS_DIR / out).resolve()
        payload = {
            "source_dir": str(src_dir),
            "strings_db": str(db_path),
            "dict": str(dict_path),
            "consistency": {
                "identical": diff["identical"],
                "db_unique": diff["db_unique"], "src_unique": diff["src_unique"],
                "db_occurrences": diff["db_occurrences"], "src_occurrences": diff["src_occurrences"],
                "added": [{"value": x["value"], "count": x["count"]} for x in diff["added"]],
                "removed": [{"value": x["value"], "count": x["count"]} for x in diff["removed"]],
                "changed_count": diff["changed_count"],
                "changed_location": diff["changed_location"],
            },
            "dict_audit": {
                "dict_entries": audit["dict_entries"],
                "covered": audit["covered"],
                "missing_total": audit["missing_total"],
                "missing_ui": [{"value": x["value"], "count": x["count"],
                                "file": x["files"][0]["file"], "line": x["files"][0]["line"]}
                               for x in audit["missing_ui"]],
                "missing_log_count": len(audit["missing_log"]),
                "missing_comment_count": len(audit["missing_comment"]),
                "missing_other_count": len(audit["missing_other"]),
                "stale_keys": audit["stale_real"],
                "stale_identity_keys": audit["stale_identity"],
            },
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"JSON 报告已写入：{out}")

    if args.strict and not diff["identical"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
