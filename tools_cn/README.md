# tools_cn —— OptiScaler 中文化工具链

针对 **OptiScaler v10.0.0.1**（master）与 `extracted_strings.json` 对齐的一套脚本。  
所有脚本都可以在仓库根目录或 `tools_cn/` 目录下运行，路径解析基于脚本自身位置，  
不再依赖当前工作目录。

> 用 GitHub Actions 自动出 nightly 包（与官方 optiscaler-nightly 同结构）见仓库根目录的
> [BUILD_ZH.md](../BUILD_ZH.md)。CI 只需要 `tools_cn/`（含 `assets/CJK_Compressed.h`）与 workflow 文件。

## 依赖

- Python 3.8+（仅标准库即可跑通完整流程）
- 可选：`fonttools`（只有裁剪/校验字体时才需要：`pip install fonttools`）

## 文件总览

| 文件                            | 作用                                             |
| ----------------------------- | ---------------------------------------------- |
| `cstr.py`                     | **公共模块**：C 字符串编解码、词法级扫描、批量替换、路径与字典解析           |
| `extract_strings.py`          | 从源码抽取字符串，输出与 `extracted_strings.json` 同构的 JSON |
| `sync_check.py`               | **核对**：JSON vs 最新源码是否漂移 + 字典覆盖率/过期键审计          |
| `update_upstream.py`          | **上游更新后一站式维护**：出新待翻译清单、可选同步源码树、清理过期键  |
| `cjk_patch.py`                | 注入「内嵌 CJK 字体」补丁（升级上游源码后必跑，幂等，自带 `--check`）   |
| `apply_dict_v10.py`           | **唯一的字典应用入口**：把 `dict_v10.json` 写入源码（保留 BOM/行尾，幂等） |
| `filter_ui.py`                | 把字符串分成「界面文本 / 非界面文本 / 仅注释」三类，输出评审清单            |
| `scan_remaining.py`           | 列出「待翻译」与「已译未应用」的界面文本                           |
| `build_charset.py`            | 汇总界面所需字符集，可选裁剪 CJK 字体                          |
| `verify_font_chars.py`        | 校验字体是否覆盖界面用到的全部中文                              |
| `dict_v10.json`               | v10 翻译字典（1381 条，唯一在用的字典）                      |
| `assets/CJK_Compressed.h`     | 内嵌中文字体子集（1.35 MB），CI 里用它补进上游源码树              |

## 典型流程

```bash
# 1) 抽取字符串（默认本仓库源码；--src 指向任意源码树，如最新 master）
python tools_cn/extract_strings.py --stats

# 2) 核对：现有 JSON 是否与最新源码一致；字典还缺什么
python tools_cn/sync_check.py \
    --src "C:/ALL/下载/压缩/OptiScaler-master" \
    --strings "C:/ALL/下载/压缩/extracted_strings.json" \
    --json sync_report.json

# 3) 补译 dict_v10.json，然后应用到源码（先 dry-run 看影响面）
python tools_cn/apply_dict_v10.py --dry-run
python tools_cn/apply_dict_v10.py

# 4) 检查还有哪些界面文本没翻译 / 没应用
python tools_cn/scan_remaining.py

# 5) 字符集与字体
python tools_cn/build_charset.py
python tools_cn/build_charset.py --font C:/Windows/Fonts/msyh.ttc
python tools_cn/verify_font_chars.py
```

## 上游更新后怎么维护（日常）

管一条命令：

```bash
# 1) 只看上游新增了什么（不动任何源码，只写 review/todo-YYYYMMDD.md|json）
python tools_cn/update_upstream.py --src "C:/ALL/下载/压缩/OptiScaler-master"

# 2) 翻译 review/todo-*.md 里列出的条目，补进 dict_v10.json
#    （表里最后一列 "可复用旧译文" 是脚本用相似度猜的，上游改原文时直接抄就行）

# 3) 复查：待翻译应为 0
python tools_cn/update_upstream.py --src "C:/ALL/下载/压缩/OptiScaler-master"
```

如果本地也要能编译最新源码，加 `--sync-tree`（会把上游 `OptiScaler/` 覆盖进本仓库，
同步根目录的 ini/sln/bat，然后自动补字体、重新注入译文）：

```bash
python tools_cn/update_upstream.py --src "C:/ALL/下载/压缩/OptiScaler-master" --sync-tree
```

其他开关：

| 参数 | 作用 |
| --- | --- |
| `--prune-stale` | 报告字典里上游已删/已改的键 |
| `--prune-stale --apply-prune` | 真删这些键（先写 `dict_v10.json.bak`） |
| `--strict` | 有未翻译条目时返回码 1（可挂 CI 卡口） |
| `--json` | 输出机器可读摘要 |
| `--out DIR` | 清单输出目录，默认 `tools_cn/review/` |

**用 GitHub Actions 的话可以完全不动手**：流水线每天拉上游、构建时会把
`review/` 作为 `translation-backlog` artifact 上传，新增/待翻译条目都在里面；
译文没跟上时，新功能按钮会显示英文，不会崩也不会缺字。

## 升级到最新 nightly 的固定流程

本仓库源码树当前 = **v10.0.0.1（2026-10-22 nightly / pre1）** 且已注入汉化。
上游 nightly 更新后按下面四步走，顺序不能变：

```bash
# 1) 用最新上游源码覆盖本仓库的源码树（保留 menu/font/CJK_Compressed.h）
#    外部依赖 external/ 不需要动
# 2) 把 CJK 字体资源放回 menu/font/CJK_Compressed.h，然后注入补丁
python tools_cn/cjk_patch.py --check     # 先看上游代码结构是否仍然匹配
python tools_cn/cjk_patch.py             # 注入 include + [CN] 字体合并块 + vcxproj 条目
# 3) 重新注入译文
python tools_cn/apply_dict_v10.py
# 4) 复核
python tools_cn/scan_remaining.py
```

`cjk_patch.py` 找不到锚点时会明确报错（上游改了字体初始化代码结构），
这时需要手工对照 `_backup` 或旧版本补齐补丁块——**不要跳过**，跳过会导致中文全部显示为方框。

## 与 `extracted_strings.json` 的一致性

`extract_strings.py` 的默认参数刻意保持旧版语义，因此对未汉化的  
`OptiScaler-master`（英文原树）重新抽取后，结果与 `extracted_strings.json` **逐字段相等**  
（1569 条唯一字符串 / 2020 处出现，`count`、`file`、`line`、`ctx` 全部一致）。
注意：汉化后的本仓库源码树抽取出来是 1540 条 / 1994 处，差异来自"不同英文译成同一中文"后的去重，属正常：

```bash
python tools_cn/extract_strings.py \
    --src "C:/ALL/下载/压缩/OptiScaler-master" \
    --out /tmp/check.json --no-comment-flag
# 与 extracted_strings.json 做 JSON 比较 -> True
```

- 默认输出会多两个字段：`comment_only`（该串只出现在注释里）与每处位置的  
  `comment` 标记；加 `--no-comment-flag` 可输出与旧文件完全同构的内容。
- `--comments skip` 用于剔除仅注释项（旧清单里有 16 条这类噪音）。

## 抽取规则（与旧脚本一致的部分）

- 仅扫描 `OptiScaler/menu/*.cpp`（`--include-headers` 可加 `*.h/*.hpp`）
- 只统计解码后长度 ≥ 2 的字面量（`--min-len`）
- 每条字符串最多记录 6 处位置（`--max-locations`），`count` 仍为真实总数
- 上下文 `ctx` 截断 160 字符（`--ctx-chars`），按行 `strip()`

## 改进点（相对旧脚本）

1. **词法级扫描**：维护 `//`、`/* */` 状态并跳过字符常量 `'x'` 与数字分隔符  
   `1'000`，不再用逐行正则盲抓引号；注释内字面量会被标记而非混进正文。
2. **抽取/替换共用一套逻辑**（`cstr.iter_literals` / `rewrite_literals`），  
   不会出现"抽取到但替换不到"的口径差异。
3. **路径全部参数化**：`--src` / `--dict` / `--strings` / `--out`，  
   也可用环境变量 `OPTISCALER_SRC`；不再依赖 `cwd`。
4. **只保留一份字典**：v10 起统一使用 `dict_v10.json`；旧的 `dict.json`（0.7.x，832 条）
   是它的严格子集（键与译文 100% 重合），已随旧 `apply_dict.py` 一起退役。
5. **写盘更安全**：逐字节保留 BOM 与 CRLF/LF；内容无变化时不重写文件（保留 mtime）；  
   `--dry-run` 只统计。
6. **新增 `sync_check.py`**：把"JSON 与源码是否一致 + 字典覆盖率 + 过期键"固化成可重复命令，  
   `--strict` 可在有漂移时返回退出码 1。

## 当前状态（2026-10-23 核对，v10.0.0.1 / 2026-10-22 nightly）

- 源码树：`OptiScaler/` = 最新 master 全量替换，另加 `menu/font/CJK_Compressed.h` 与 `[CN]` 字体补丁
- 根部同步：`OptiScaler.ini`、`OptiScaler.sln`（新 sln 已去掉 32 位 x86 平台）
- 汉化结果：`menu_common.cpp` 内 10371 个中文字符；抽取唯一字符串 1540 条（英文合并后同译项会去重）
- `dict_v10.json`：1381 条，**界面文本 1026/1059（96.9%）已译**，剩 33 条
  （`PRESET A..O`、`FFX Dx12`、`D3D11 w/DX12`、Vulkan AntiLag、若干状态标记、wiki 链接）
- 137~158 条字典键在最新源码中已失配（旧界面文字被删/改名），可清理但无害
- 抽查确认：`##2` 这类 ImGui ID、`%.1f%%` 这类格式符在译文里都完整保留

## 注意事项

- 字符串中的 `##xxx` 是 ImGui 的 ID 分隔符，翻译时**必须原样保留**（例如 `纹理##2`）。
- `%s`、`{0:X}`、`\n` 等格式符要保留，否则运行时会崩或错位。
- 只出现在注释里的字符串不会被替换（`--translate-comments` 可强制，但通常不需要）。
