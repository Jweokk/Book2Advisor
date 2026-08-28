# -*- coding: utf-8 -*-
"""
Method Runtime 集成测试（TASK-P4，真实 LLM 调用，不 mock）。

覆盖验收点：
    - test_ask_direct   ：A 类题「人物怎么看待诚信经营」→ 8 段标题齐全、证据来源非空、含 [第X章] 引用
    - test_ask_novel    ：C 类题「人物会怎么看 AI 大规模替代工厂工人」→ 推演标注段同时含「书中依据」与「推演」
    - test_ask_conflict ：D 类题「如实披露质量问题会失去大客户，怎么办」→ 例外与风险段非空
    - test_bad_key_handling：无效 key → 明确中文报错、不崩溃、输出不含 key 字符串
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from core.runtime.ask import TRACE_SECTIONS, load_method_model, run_chain
from core.runtime.llm import DeepSeekClient, LLMError

MODEL_PATH = os.environ.get("METHOD_MODEL", "")  # 需自备方法模型（见 README）


def _run(question: str) -> dict:
    """加载模型并执行完整 8 步推理链（真实 LLM 调用）。"""
    model = load_method_model(MODEL_PATH)
    client = DeepSeekClient()
    return run_chain(model, question, client=client, verbose=False)


def test_ask_direct():
    """A 类题：输出含全部 8 段标题、证据来源非空、含 [第X章] 引用。"""
    result = _run("人物怎么看待诚信经营？")
    trace = result["trace"]

    # 8 段标题齐全
    for title in TRACE_SECTIONS:
        assert title in trace, f"Method Trace 缺少段落标题：{title}"

    # 证据来源非空
    assert result["evidence"], "证据来源（evidence）为空"

    # 含 [第X章] 引用
    assert re.search(r"\[第\d+章\]", trace), "Method Trace 缺少 [第X章] 引用"

    # 建议段非空
    assert result["reasoning"]["advice"].strip(), "建议段为空"


def test_ask_novel():
    """C 类题：推演标注段同时包含「书中依据」与「推演」两类内容。"""
    result = _run("人物会怎么看 AI 大规模替代工厂工人？")
    annotation = result["reasoning"]["annotation"]

    assert "书中依据" in annotation, "推演标注缺少「书中依据」内容"
    assert "推演" in annotation, "推演标注缺少「推演」内容"
    assert "书中依据" in result["trace"], "Method Trace 未体现依据/推演区分"


def test_ask_conflict():
    """D 类题：例外与风险段非空。"""
    result = _run("如实披露质量问题会失去大客户，怎么办？")
    exceptions = result["reasoning"]["exceptions"]

    assert exceptions.strip(), "例外与风险段为空"
    assert "例外与风险" in result["trace"], "Method Trace 缺少例外与风险段"


def test_bad_key_handling():
    """坏 key：明确中文报错、不崩溃、输出中不含 key 字符串。"""
    bad_key = "sk-invalid-bad-key-0123456789abcdef"
    client = DeepSeekClient(api_key=bad_key)

    with pytest.raises(LLMError) as excinfo:
        client.chat([{"role": "user", "content": "你好"}])

    message = str(excinfo.value)
    assert message, "坏 key 场景没有报错信息"
    # 中文报错（含中文汉字）
    assert re.search(r"[\u4e00-\u9fff]", message), "报错信息不是中文"
    # 不泄密：错误信息中绝不出现 key 本身
    assert bad_key not in message
    # 统一提示文案存在
    assert "API key" in message
