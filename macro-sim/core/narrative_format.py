"""叙事文本规范化工具（macro-sim · 天璇）。

本模块把 LLM 返回的「叙事报告」文本规范化为结构化的行片段，供
``run.py`` 的报告生成逻辑直接 ``lines += format_narrative(...)`` 拼接。

关联 B1 bug 修复
---------------
上游报告叙事分隔符原本约定使用 ``【label】``，但 GLM 真实输出为 Markdown
加粗 ``**label**``。修复方式是把两种分隔符统一归一成 ``【label】``，使既有
的 ``【】`` 拆分 / 标签美化逻辑无需改动即可正确工作。该归一化逻辑原先内联在
``run.py`` 的报告生成函数里，本模块将其抽取为纯函数以便单元测试覆盖，行为
保持逐字节等价（零变化）。

行为契约（format_narrative）
----------------------------
- 命中多段分隔符（>=2 个 label）时：返回
  ``['', '**label1**：content1', '**label2**：content2', ..., '']``，
  其中 content 为空的行会被跳过。
- 否则：返回 ``['', <归一化+清理后的文本>, '']``。
- 兼容 GLM 真实输出 ``**label**`` 与约定 ``【label】`` 两种分隔符。
"""

import re

# 清理 LLM 可能输出的数字前缀（"1. " "2.\n" 等）。
_DIGIT_PREFIX_RE = re.compile(r'\n\d+\.\s*\n?')
# 兼容 GLM 实际输出 `**label**`（Markdown 加粗）与约定 `【label】` 两种分隔符：
# 统一归一成 `【label】`，下方既有 `【】` 拆分/标签逻辑无需改动即可正确美化（B1）。
_BOLD_LABEL_RE = re.compile(r'\*\*(.+?)\*\*\s*')
_SECTION_SPLIT_RE = re.compile(r'【[^】]+】')
_SECTION_FIND_RE = re.compile(r'【([^】]+)】')


def format_narrative(raw: str) -> list[str]:
    """将 LLM 叙事文本规范化为结构化行列表，返回要插入报告 lines 的片段。

    行为契约：
    - 命中多段分隔符（>=2 个 label）时：返回
      ``['', '**label1**：content1', '**label2**：content2', ..., '']``
      （空 content 的行跳过）。
    - 否则：返回 ``['', <归一化+清理后的文本>, '']``。
    兼容 GLM 真实输出 ``**label**`` 与约定 ``【label】`` 两种分隔符（B1 修复）。

    Args:
        raw: 原始叙事文本（通常来自 ``path.narrative``）。

    Returns:
        要拼接进报告 ``lines`` 的字符串列表。若 ``raw`` 为空（对应原调用处
        ``if path.narrative:`` 不进入分支），返回空列表 ``[]``，与原内联逻辑
        在任意输入下的行为逐字节一致。
    """
    if not raw:
        return []

    # 清理 LLM 可能输出的数字前缀（"1. " "2.\n" 等）
    narrative = _DIGIT_PREFIX_RE.sub('\n', raw).strip()
    # 兼容 GLM 实际输出 `**label**`（Markdown 加粗）与约定 `【label】` 两种分隔符：
    # 统一归一成 `【label】`，下方既有 `【】` 拆分/标签逻辑无需改动即可正确美化（B1）。
    narrative = _BOLD_LABEL_RE.sub(r'【\1】', narrative)

    parts = _SECTION_SPLIT_RE.split(narrative)
    labels = _SECTION_FIND_RE.findall(narrative)

    if len(labels) >= 2 and len(parts) >= 2:
        out: list[str] = [""]
        for label, content in zip(labels, parts[1:]):
            content = content.strip().lstrip('：:').strip()
            if content:
                out.append(f"**{label}**：{content}")
        out.append("")
        return out

    return ["", narrative, ""]
