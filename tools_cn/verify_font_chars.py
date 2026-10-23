#!/usr/bin/env python3
"""校验界面用到的每一个中文字符都能在裁剪后的字体里找到。

用法：
  python tools_cn/verify_font_chars.py
  python tools_cn/verify_font_chars.py --font tools_cn/msyh_cjk.ttf \
      --src "C:/ALL/下载/压缩/OptiScaler-master"

缺少 fontTools 或字体文件时会给出提示并以退出码 2 结束（不算致命错误）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cstr


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF
            or 0x3400 <= o <= 0x4DBF
            or 0x3000 <= o <= 0x303F
            or 0xFF00 <= o <= 0xFFEF
            or ch in "，。！？：；（）【】《》〈〉「」『』…—–·、％℃×÷＝＋－＊／＃＠＆")


def used_chars(menu_dir: Path, include_headers: bool) -> set:
    used = set()
    for f in cstr.list_sources(menu_dir, include_headers=include_headers):
        for ch in cstr.read_source(f):
            if is_cjk(ch):
                used.add(ch)
    return used


def main() -> None:
    ap = argparse.ArgumentParser(description="校验字体是否覆盖界面所需中文字符")
    ap.add_argument("--font", default=str(cstr.TOOLS_DIR / "msyh_cjk.ttf"), help="裁剪后的字体")
    ap.add_argument("--src", help="源码目录（仓库根或 OptiScaler/menu）")
    ap.add_argument("--include-headers", action="store_true", help="同时统计 *.h / *.hpp")
    ap.add_argument("--extra-text", action="append",
                    help="额外校验的文本文件（例如 tools_cn/cjk_chars.txt），可重复")
    args = ap.parse_args()

    font_path = Path(args.font)
    if not font_path.is_absolute():
        font_path = (cstr.TOOLS_DIR / font_path).resolve()

    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print("提示：未安装 fontTools，无法校验字体覆盖（pip install fonttools）。")
        print(f"      需要覆盖的字符见：{cstr.TOOLS_DIR / 'cjk_chars.txt'}")
        sys.exit(2)

    if not font_path.is_file():
        print(f"提示：字体文件不存在：{font_path}")
        print("      先用 build_charset.py --font <系统字体> 生成裁剪字体。")
        sys.exit(2)

    cmap = TTFont(str(font_path)).getBestCmap()
    used = used_chars(cstr.resolve_menu_dir(args.src), args.include_headers)
    for extra in args.extra_text or []:
        p = Path(extra)
        if not p.is_absolute():
            p = (cstr.TOOLS_DIR / p).resolve()
        if p.is_file():
            used.update(ch for ch in p.read_text(encoding="utf-8") if is_cjk(ch))

    missing = sorted(ch for ch in used if ord(ch) not in cmap)
    print(f"字体      : {font_path}")
    print(f"界面字符  : {len(used)} 个（中文/标点）")
    if missing:
        print(f"缺少 {len(missing)} 个字符: {''.join(missing)}")
        sys.exit(1)
    print("全部字符均存在于字体中 - OK")


if __name__ == "__main__":
    main()
