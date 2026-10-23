#!/usr/bin/env python3
"""统计中文界面需要的字符集，并按需裁剪字体（生成 CJK 子集）。

字符来源（三者合并）：
  1) 字典里的全部译文
  2) 已翻译源码中实际出现的中文（--src 指向已应用字典的源码树）
  3) ASCII 可打印字符 + 常用中文标点

用法：
  python tools_cn/build_charset.py                       # 只生成 tools_cn/cjk_chars.txt
  python tools_cn/build_charset.py --font C:/Windows/Fonts/msyh.ttc --out tools_cn/msyh_cjk.ttf
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cstr

CJK_PUNCT = "，。！？：；（）【】《》〈〉「」『』…—–·、％℃×÷＝＋－＊／＃＠＆［］｛｝“”‘’"


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF        # 基本汉字
            or 0x3400 <= o <= 0x4DBF     # 扩展 A
            or 0x3000 <= o <= 0x303F     # 中文标点
            or 0xFF00 <= o <= 0xFFEF     # 全角字符
            or ch in CJK_PUNCT)


def collect_chars(mapping: dict, src_dirs: list) -> set:
    chars = set()
    for value in mapping.values():
        for ch in value:
            if ord(ch) >= 0x20:
                chars.add(ch)
    for menu_dir in src_dirs:
        for f in cstr.list_sources(menu_dir, include_headers=True):
            for ch in cstr.read_source(f):
                if is_cjk(ch):
                    chars.add(ch)
    for cp in range(0x20, 0x7F):          # ASCII 可打印字符
        chars.add(chr(cp))
    chars.update(CJK_PUNCT)
    return chars


def subset_font(font_path: Path, chars: set, out_path: Path) -> bool:
    """用 fontTools 裁剪字体；缺少依赖时返回 False。"""
    try:
        from fontTools import subset
    except ImportError:
        print("提示：未安装 fontTools，跳过字体裁剪（pip install fonttools）。")
        print(f"      可用字符集文件手工裁剪：{out_path.parent / 'cjk_chars.txt'}")
        return False

    args = [str(font_path), f"--text={''.join(sorted(chars))}", f"--output-file={out_path}",
            "--layout-features=*", "--glyph-names", "--symbol-cmap", "--legacy-cmap",
            "--notdef-glyph", "--notdef-outline", "--recommended-glyphs"]
    print(f"裁剪字体：{font_path} -> {out_path}")
    subset.main(args)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="生成中文界面字符集并按需裁剪字体")
    ap.add_argument("--dict", dest="dict_path", help="翻译字典，默认 dict_v10.json")
    ap.add_argument("--src", action="append",
                    help="额外统计中文的源码目录（可重复），默认本仓库")
    ap.add_argument("--out", default=str(cstr.TOOLS_DIR / "cjk_chars.txt"), help="字符集输出路径")
    ap.add_argument("--font", help="需要裁剪的字体（ttf/ttc）")
    ap.add_argument("--font-out", default=str(cstr.TOOLS_DIR / "msyh_cjk.ttf"),
                    help="裁剪后的字体输出路径")
    args = ap.parse_args()

    mapping = cstr.load_dict(cstr.resolve_dict(args.dict_path))
    src_dirs = [cstr.resolve_menu_dir(s) for s in (args.src or [None])]

    chars = collect_chars(mapping, src_dirs)
    text = "".join(sorted(chars))

    out = Path(args.out)
    if not out.is_absolute():
        out = (cstr.TOOLS_DIR / out).resolve()
    out.write_text(text, encoding="utf-8")

    non_ascii = [c for c in sorted(chars) if ord(c) > 0x7F]
    print(f"字典条目      : {len(mapping)}")
    print(f"字符总数      : {len(chars)}（非 ASCII {len(non_ascii)}）")
    print(f"字符集已写入  : {out}")
    print(f"非 ASCII 示例 : {''.join(non_ascii[:80])}")

    if args.font:
        font = Path(args.font)
        if not font.is_file():
            raise SystemExit(f"错误：字体文件不存在：{font}")
        font_out = Path(args.font_out)
        if not font_out.is_absolute():
            font_out = (cstr.TOOLS_DIR / font_out).resolve()
        subset_font(font, chars, font_out)


if __name__ == "__main__":
    main()
