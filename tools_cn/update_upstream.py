#!/usr/bin/env python3
"""上游更新后的一站式维护脚本。

做三件事（可分别开关）：
  1) 体检：对比最新上游源码与 dict_v10.json，列出「新增待翻译 / 字典过期键」
  2) 出清单：把待翻译条目写成 review/todo-YYYYMMDD.md + .json（含上下文、位置、可复用的旧译文建议）
  3) 同步源码树（可选）：把上游源码覆盖进本仓库，再自动注入字体补丁与译文

典型用法：
  # 只看上游新增了什么（不碰任何文件，只写 review/）
  python tools_cn/update_upstream.py --src ../OptiScaler-master

  # 连源码树一起升级（覆盖本仓库 OptiScaler/ 并重新汉化）
  python tools_cn/update_upstream.py --src ../OptiScaler-master --sync-tree

  # 顺便清理字典里已经失效的键（默认只报告，--apply-prune 才真删）
  python tools_cn/update_upstream.py --src ../OptiScaler-master --prune-stale --apply-prune

退出码：默认 0；加 --strict 且存在待翻译条目时返回 1（可用于 CI 提醒）。
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import cstr
import extract_strings
import sync_check

# 同步源码树时需要一起更新的根目录文件（相对仓库根）
ROOT_FILES = ("OptiScaler.ini", "OptiScaler.sln", "setup_windows.bat", "setup_linux.sh",
              "Streamlined_fetcher_windows.bat", "dxvk.conf",
              "Changelog.md", "Config.md", "Features.md", "Issues.md", "README.md", "Spoofing.md")


def scan(menu_dir: Path, include_headers: bool):
    items, _ = extract_strings.build(
        menu_dir,
        include_headers=include_headers,
        min_len=cstr.DEFAULT_MIN_LEN,
        ctx_chars=cstr.DEFAULT_CTX_CHARS,
        max_locations=cstr.DEFAULT_MAX_LOCATIONS,
        comments="include",
        sort_key="count",
    )
    return items


def best_match(value: str, keys: list):
    """找最可能对应的旧条目（上游改名/微调原文时，可直接复用旧译文）。"""
    close = difflib.get_close_matches(value, keys, n=1, cutoff=0.7)
    return close[0] if close else None


def analyse(items, dictionary):
    """返回 (待翻译界面文本, 缺失计数, 过期键)。"""
    missing_ui = []
    bucket = {"ui": 0, "log": 0, "comment": 0, "other": 0}

    keys = list(dictionary)
    for it in items:
        if it["value"] in dictionary:
            continue
        kind = sync_check.classify(it)
        bucket[kind] += 1
        if kind != "ui":
            continue
        suggestion = best_match(it["value"], keys)
        missing_ui.append({
            "value": it["value"],
            "count": it["count"],
            "file": it["files"][0]["file"],
            "line": it["files"][0]["line"],
            "ctx": it["files"][0]["ctx"],
            "suggest_from": suggestion,
            "suggest_text": dictionary[suggestion] if suggestion else None,
        })

    values = {it["value"] for it in items}
    stale = [k for k in dictionary
             if k not in values and dictionary[k] not in values]
    return missing_ui, bucket, stale


def write_review(out_dir: Path, menu_dir: Path, items, missing_ui, bucket, stale, dictionary) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    md = out_dir / f"todo-{stamp}.md"
    js = out_dir / f"todo-{stamp}.json"

    ui_total = sum(1 for it in items if sync_check.classify(it) == "ui")
    lines = [
        f"# 上游同步检查 {stamp}",
        "",
        f"- 源码目录：`{menu_dir}`",
        f"- 上游字符串：{len(items)} 条（界面文本 {ui_total}）",
        f"- 字典条目：{len(dictionary)}",
        f"- **待翻译界面文本：{len(missing_ui)} 条**",
        f"- 无需翻译：日志/格式串 {bucket['log']}、注释 {bucket['comment']}、其他 {bucket['other']}",
        f"- 字典中已失效的键：{len(stale)} 条（`--prune-stale --apply-prune` 可清理）",
        "",
    ]

    if missing_ui:
        lines += ["## 待翻译", "", "| # | 英文原文 | 次数 | 位置 | 可复用旧译文 |", "|---|---|---|---|---|"]
        for i, m in enumerate(sorted(missing_ui, key=lambda x: -x["count"]), 1):
            reuse = ""
            if m["suggest_from"]:
                reuse = f"`{m['suggest_from']}` → {m['suggest_text']}"
            value = m["value"].replace("|", "\\|").replace("\n", "\\n")
            lines.append(f"| {i} | `{value}` | {m['count']} | {m['file']}:{m['line']} | {reuse} |")
        lines += ["", "> 每条的位置见上表；翻译时保留 `##id`、`%s`、`{0:X}`、`\\n` 等占位符。", ""]
    else:
        lines += ["## 待翻译", "", "没有新增界面文本，上游这次改动不涉及菜单文字。", ""]

    if stale:
        lines += ["## 字典中已失效的键（上游删了或改了原文）", ""]
        for k in sorted(stale)[:80]:
            lines.append(f"- `{k}` → {dictionary[k]}")
        if len(stale) > 80:
            lines.append(f"- ... 其余 {len(stale) - 80} 条")

    md.write_text("\n".join(lines), encoding="utf-8")
    js.write_text(json.dumps({"generated": stamp, "source": str(menu_dir),
                              "missing_ui": missing_ui, "stale_keys": stale},
                             ensure_ascii=False, indent=1), encoding="utf-8")
    return md


def sync_tree(menu_dir: Path) -> None:
    """把上游源码树同步进本仓库（保留字体资产），然后重新注入汉化。"""
    upstream_root = menu_dir.parent          # .../OptiScaler
    repo_root = cstr.REPO_ROOT
    target = repo_root / "OptiScaler"

    print(f"  同步源码树：{upstream_root} -> {target}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(upstream_root, target)

    for name in ROOT_FILES:
        src = upstream_root.parent / name
        if src.is_file():
            shutil.copy2(src, repo_root / name)

    # 重新打字体补丁（字体来自 tools_cn/assets）并注入译文
    for script in ("cjk_patch.py", "apply_dict_v10.py"):
        cmd = [sys.executable, str(cstr.TOOLS_DIR / script), "--src", str(repo_root)]
        if script == "apply_dict_v10.py":
            cmd.append("--quiet")
        print(f"  运行 {script} ...")
        rc = subprocess.call(cmd)
        if rc != 0:
            raise SystemExit(f"错误：{script} 执行失败（退出码 {rc}）")


def prune(dictionary: dict, stale: list, dict_path: Path, apply: bool) -> None:
    if not stale:
        return
    if not apply:
        print(f"  过期键 {len(stale)} 条（未删除；加 --apply-prune 才真正清理）")
        return
    backup = dict_path.with_suffix(".json.bak")
    backup.write_text(dict_path.read_text(encoding="utf-8"), encoding="utf-8")
    for k in stale:
        dictionary.pop(k, None)
    dict_path.write_text(json.dumps(dictionary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  已删除 {len(stale)} 条过期键（原文件备份为 {backup.name}）")


def main() -> None:
    ap = argparse.ArgumentParser(description="上游更新后同步译文/源码树")
    ap.add_argument("--src", help="上游源码目录（仓库根或 OptiScaler/menu）")
    ap.add_argument("--dict", dest="dict_path", help="翻译字典，默认 dict_v10.json")
    ap.add_argument("--out", default=str(cstr.TOOLS_DIR / "review"), help="待翻译清单输出目录")
    ap.add_argument("--include-headers", action="store_true", help="同时扫描 *.h / *.hpp")
    ap.add_argument("--sync-tree", action="store_true", help="把上游源码树覆盖进本仓库并重新汉化")
    ap.add_argument("--prune-stale", action="store_true", help="报告字典中已失效的键")
    ap.add_argument("--apply-prune", action="store_true", help="真的删除失效键（会写 .bak 备份）")
    ap.add_argument("--json", action="store_true", help="同时把摘要打印成 JSON")
    ap.add_argument("--strict", action="store_true", help="存在待翻译条目时返回退出码 1")
    ap.add_argument("--quiet", action="store_true", help="少打印")
    args = ap.parse_args()

    menu_dir = cstr.resolve_menu_dir(args.src)
    dict_path = cstr.resolve_dict(args.dict_path)
    dictionary = cstr.load_dict(dict_path)

    print(f"上游源码: {menu_dir}")
    print(f"翻译字典: {dict_path}（{len(dictionary)} 条）")

    items = scan(menu_dir, args.include_headers)
    missing_ui, bucket, stale = analyse(items, dictionary)
    md = write_review(Path(args.out), menu_dir, items, missing_ui, bucket, stale, dictionary)

    print(f"上游字符串: {len(items)} 条")
    print(f"待翻译界面文本: {len(missing_ui)} 条"
          f"（日志/格式串 {bucket['log']}、注释 {bucket['comment']}、其他 {bucket['other']} 不计）")
    print(f"清单已写入: {md}")
    if missing_ui and not args.quiet:
        for m in sorted(missing_ui, key=lambda x: -x["count"])[:10]:
            hint = f"  ⟵ 可复用 {m['suggest_from']!r}" if m["suggest_from"] else ""
            print(f"  ? [{m['count']}] {m['value']!r} @ {m['file']}:{m['line']}{hint}")
        if len(missing_ui) > 10:
            print(f"  ... 其余 {len(missing_ui) - 10} 条见清单")

    if args.prune_stale or args.apply_prune:
        prune(dictionary, stale, dict_path, args.apply_prune)

    if args.sync_tree:
        print()
        sync_tree(menu_dir)
        print("源码树已同步并重新汉化。建议再跑一次本命令确认「待翻译 0 条」。")

    if args.json:
        print(json.dumps({"source": str(menu_dir), "dict": str(dict_path),
                          "strings": len(items), "missing_ui": len(missing_ui),
                          "stale_keys": len(stale), "review": str(md)},
                         ensure_ascii=False, indent=1))

    if args.strict and missing_ui:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
