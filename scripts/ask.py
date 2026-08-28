#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method Advisor — CLI 入口（TASK-P4）。

用法：
    python3 scripts/ask.py "问题" [--verbose]

示例：
    python3 scripts/ask.py "目标人物怎么看待诚信经营"
    python3 scripts/ask.py "目标人物会怎么看 AI 大规模替代工厂工人" --verbose

输出：8 段 Method Trace（Markdown）。
--verbose：额外打印每步 LLM 调用的输入/输出摘要（不含 API key）。
错误信息只提示「API key 未配置或无效」，绝不打印 key。
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime.ask import METHOD_MODEL_PATH, load_method_model, run_chain  # noqa: E402
from core.runtime.llm import DeepSeekClient, LLMError  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Method Advisor：按人物方法诊断推演现实问题，输出 Method Trace"
    )
    parser.add_argument("question", help="要咨询的现实问题（如：目标人物怎么看待诚信经营）")
    parser.add_argument("--verbose", action="store_true",
                        help="打印每步 LLM 调用的输入/输出摘要（不含 API key）")
    args = parser.parse_args(argv)

    # 初始化客户端（此处只报 key 缺失，不打印 key）
    try:
        client = DeepSeekClient()
    except LLMError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    # 执行 8 步推理链（每步失败给出明确中文错误并终止）
    try:
        model = load_method_model(METHOD_MODEL_PATH)
        result = run_chain(model, args.question, client=client, verbose=args.verbose)
    except (LLMError, RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(result["trace"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
