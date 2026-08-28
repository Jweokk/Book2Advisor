# -*- coding: utf-8 -*-
"""Book2Advisor — run_chain 的薄包装。

原样调用 core/runtime/ask.run_chain（禁止修改 core/ 任何文件）：
    - client 传 None：run_chain 内部自建 DeepSeekClient()，API key 自动从
      环境变量 DEEPSEEK_API_KEY 或 ~/.book2advisor/tokens.env 读取（逻辑见 llm.py）
    - 返回 8 段 Method Trace 的结构化字典，/api/ask 原样转 JSON 返回
"""

import logging

from core.runtime.ask import METHOD_MODEL_PATH, load_method_model, run_chain

logger = logging.getLogger("book2advisor.advisor")

# Method Model 只加载一次（进程内缓存；加载失败不缓存，下次重试）
_model = None


def ask(question: str) -> dict:
    """执行 8 步推理链，返回完整 Method Trace 字典。"""
    global _model
    if _model is None:
        _model = load_method_model(METHOD_MODEL_PATH)
        logger.info("Method Model 已加载：%s", METHOD_MODEL_PATH)
    # client=None → run_chain 内部自建 DeepSeekClient()，本模块不接触 API key
    return run_chain(_model, question, client=None, verbose=False)
