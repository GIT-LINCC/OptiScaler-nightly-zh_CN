#!/usr/bin/env python3
"""扫描源码里"还没处理"的界面文本。

输出两类：
  1) 待翻译  : 源码中是英文、且字典里没有的界面文本
  2) 已译未应用: 字典里有译文、但源码里仍是英文（说明还没跑 apply_dict_v10.py）

首行会打印「界面文本 N 条，已翻译 X（百分比），未翻译 Y」，CI 把这行写进
coverage.txt，最终出现在 Release 说明里。

注意：**请在注入译文之前跑**（对英文源码）。注入后再跑，源码里的英文已经
变成中文，分类器只能靠字典反向推断原文，界面文本总数会与英文原树略有偏差
（1059 → 1037），所以 CI 里这一步排在 apply_dict_v10.py 前面。

内部复用 sync_check.py 的分类器（ui / log / comment / other），
只汇报真正的界面文本，日志与内部标识符不会刷屏。

用法：
  python tools_cn/scan_remaining.py
  python tools_cn/scan_remaining.py --src "C:/ALL/下载/压缩/OptiScaler-master" --top 40
"""
from __future__ import annotations

import argparse

import cstr
import extract_strings
import sync_check


def main() -> None:
    ap = argparse.ArgumentParser(description="扫描仍是英文的界面文本")
    ap.add_argument("--src", help="源码目录（仓库根或 OptiScaler/menu）")
    ap.add_argument("--dict", dest="dict_path", help="翻译字典，默认 dict_v10.json")
    ap.add_argument("--include-headers", action="store_true", help="同时扫描 *.h / *.hpp")
    ap.add_argument("--top", type=int, default=30, help="每类最多打印条数，默认 30")
    ap.add_argument("--all", action="store_true", help="连日志/其他类也一起列出")
    args = ap.parse_args()

    menu_dir = cstr.resolve_menu_dir(args.src)
    dict_path = cstr.resolve_dict(args.dict_path)
    mapping = cstr.load_dict(dict_path)

    items, _ = extract_strings.build(
        menu_dir,
        include_headers=args.include_headers,
        min_len=cstr.DEFAULT_MIN_LEN,
        ctx_chars=cstr.DEFAULT_CTX_CHARS,
        max_locations=cstr.DEFAULT_MAX_LOCATIONS,
        comments="include",
        sort_key="count",
    )

    def has_cjk(s: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in s)

    # 反向表：中文译文 -> [英文原文...]。
    # 作用：把已经汉化的树"还原成英文"再交给分类器，保证无论 CI 在注入前还是
    # 注入后运行，界面文本总数都稳定。否则中文串普遍没有空格，会被 IDENT_LIKE
    # 判成「其他」类，总数从 1059 掉到 892，Release 说明里的覆盖率就失真了。
    # 同一译文可能对应多个英文原文（如多个英文译成同一中文），所以存列表，
    # 分类时优先采用能判成 ui 的那个原文。
    reverse: dict = {}
    for en, zh in mapping.items():
        if zh and zh != en and has_cjk(zh):
            bucket = reverse.setdefault(zh, [])
            if en not in bucket:
                bucket.append(en)

    def classify(it: dict) -> str:
        value = it["value"]
        candidates = reverse.get(value) if has_cjk(value) else None
        if candidates:
            kinds = []
            for en in candidates:
                probe = dict(it)
                probe["value"] = en
                kinds.append(sync_check.classify(probe))
            return "ui" if "ui" in kinds else kinds[0]
        return sync_check.classify(it)

    pending, unapplied, done, other = [], [], 0, []
    for it in items:
        value = it["value"]
        kind = classify(it)
        if kind != "ui":
            other.append((it, kind))
            continue
        if has_cjk(value):
            done += 1                       # 源码里已经是中文
            continue
        translated = mapping.get(value)
        if translated is None:
            pending.append(it)              # 字典里没有
        elif translated == value:
            done += 1                       # 恒等映射，保留原文
        elif has_cjk(translated):
            unapplied.append(it)            # 有译文但还没写进源码
        else:
            done += 1                       # 有意保留英文写法

    total_ui = len(pending) + len(unapplied) + done
    translated_total = done + len(unapplied)    # 已有中文译文的条数（含已写入/待写入）
    pct = translated_total * 100 / total_ui if total_ui else 0.0
    print(f"源码目录: {menu_dir}")
    print(f"翻译字典: {dict_path}（{len(mapping)} 条）")
    print(f"界面文本: {total_ui} 条，已翻译 {translated_total}（{pct:.1f}%），未翻译 {len(pending)}")
    print(f"  其中已写入源码 {done}，已译未应用 {len(unapplied)}，字典暂无译文 {len(pending)}")
    if done and not unapplied:
        # 树已经汉化过：分类器只能靠反向表推断原文，个别条目的归类可能与英文原树不同
        print("  （源码已是中文：分类靠反向推断，总数会略偏；"
              "CI 在注入前统计的那个数字才是准的）")
    print()

    if unapplied:
        print(f"已译未应用（{len(unapplied)} 条，运行 apply_dict_v10.py 即可写入）：")
        for it in sorted(unapplied, key=lambda x: -x["count"])[: args.top]:
            f0 = it["files"][0]
            print(f'  A [{it["count"]}] {it["value"]!r} @ {f0["file"]}:{f0["line"]}')
        print()

    if pending:
        print(f"待翻译（{len(pending)} 条）：")
        for it in sorted(pending, key=lambda x: -x["count"])[: args.top]:
            f0 = it["files"][0]
            print(f'  ? [{it["count"]}] {it["value"]!r} @ {f0["file"]}:{f0["line"]}')
        print()

    if args.all and other:
        print(f"非界面文本（{len(other)} 条，通常无需翻译）：")
        for it, kind in sorted(other, key=lambda x: -x[0]["count"])[: args.top]:
            f0 = it["files"][0]
            print(f'  {kind:<7} [{it["count"]}] {it["value"]!r} @ {f0["file"]}:{f0["line"]}')


if __name__ == "__main__":
    main()
