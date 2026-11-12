"""一次性修复脚本（已执行完毕，仅作追溯留档，请勿重跑）。

作用：把 functions.py 里「残损/退化 DSML 标记兜底」那一段整体替换成定稿版本。

警告：本脚本会**原地重写 functions.py**。锚点行（``MARK``）在当前代码里已
不再是原来那两行，重跑时 ``assert len(idx) == 1`` 大概率直接失败；万一锚点
恰好命中，也会用脚本内硬编码的旧内容覆盖现有实现。历史改动请查 git log，
不要执行本文件。

Run:  python _fix_strip.py   （已执行，不要再次运行）
"""

PATH = "functions.py"

NEW = r'''# 残损/退化 DSML 标记的兜底：结构化正则要求「干净的」标签形状，模型退化时
# 会在竖线之间夹杂其它字符，或成串吐出裸的闭标签装饰串。这些变体与结构化
# 正则均不匹配，会作为正文漏给客户端。全角竖线 U+FF5C 不会出现在正常正文
# 中，因此凡含该字符的尖括号片段一律整段清除；ASCII 竖线刻意保留，以免误删
# 表格与代码。
_FULLWIDTH_PIPE_TAG_RE = re.compile(r"<[^<>]*\uff5c[^<>]*>")


def _clean_tool_arg(value):
    """清除渗入工具调用参数值内部的残损 DSML 标记。

    解析器可能把标记并入参数值，例如文件路径尾部被并入一段闭标签装饰串，
    导致工具调用因文件不存在而失败。仅处理含全角竖线的字符串，正常参数与
    ASCII 竖线不受影响；字典与列表逐项递归。
    """
    if isinstance(value, str):
        if "\uff5c" in value:
            value = _FULLWIDTH_PIPE_TAG_RE.sub("", value).strip()
        return value
    if isinstance(value, dict):
        return {k: _clean_tool_arg(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_tool_arg(v) for v in value]
    return value


def _strip_stray_markers(text):
    """正文路径清洗：只去掉裸 DSML 残片、残损标记与孤立闭标签。

    开标签不在这里清：正文里真的提到 DSML 开标签时不应被静默删除，只有
    纯粹的装饰残片才需要清掉。
    """
    if not text:
        return text
    text = _FULLWIDTH_PIPE_TAG_RE.sub("", text)
    text = re.sub(
        r"</?[｜\|]{0,2}DSML(?![｜\|\s]*[A-Za-z_])[｜\|]{0,2}\s*[>＞]?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return _ORPHAN_CLOSER_RE.sub("", text)


# Tag names _STREAM_ENTRY_RE can open on.
_STREAM_ENTRY_TAGS = (
'''

MARK = "# 残损/退化 DSML 标记的兜底"

with open(PATH, encoding="utf-8") as f:
    lines = f.read().split("\n")
idx = [i for i, ln in enumerate(lines) if ln.startswith(MARK)]
assert len(idx) == 1, idx
i = idx[0]
print("锚点行:", i + 1)
print("原内容:", repr(lines[i : i + 3]))

new_lines = NEW.split("\n")
# NEW 以换行结尾，split 后末元素为空串，去掉
if new_lines and new_lines[-1] == "":
    new_lines.pop()
lines[i : i + 2] = new_lines

with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines))
print("已写回，新行数:", len(lines))