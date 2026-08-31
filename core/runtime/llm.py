# -*- coding: utf-8 -*-
"""
Method Advisor — DeepSeek LLM 封装。

职责：
    1. API key 读取：环境变量 DEEPSEEK_API_KEY → 项目根 .env 文件（KEY=VALUE 格式）
    2. OpenAI 兼容调用：base_url/model 可用环境变量 LLM_BASE_URL/LLM_MODEL 覆盖（默认 DeepSeek）
    3. 150s 超时 + 指数退避重试：429 / 500 / 502 / 503 / 超时 → 最多重试 3 次（1s / 2s / 4s）
       —— 区分超时（TimeoutError 类）与 HTTP 状态错误（HTTPStatusError 类）单独处理
    4. 异常细化：统一转中文 LLMError；严禁把 API key 打印到 stdout / stderr / 日志
"""

import json
import os
import time
from pathlib import Path

import openai

# LLM 服务参数（可用环境变量覆盖，默认 DeepSeek——任意 OpenAI 兼容端点均可）：
#   LLM_BASE_URL  覆盖 base_url（如 https://api.anthropic.com/v1 或自建网关）
#   LLM_MODEL     覆盖模型名（如 claude-sonnet-4-5 / gpt-4o）
DEEPSEEK_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
REQUEST_TIMEOUT = 150.0         # 硬性：单次请求超时 150s（推理模型思考计入 max_tokens，16000 输出需 90-150s）
MAX_RETRIES = 3                 # 硬性：最多重试 3 次
RETRYABLE_STATUS = {429, 500, 502, 503}   # 硬性：可重试的 HTTP 状态码
KEY_HINT = "API key 未配置或无效"          # 硬性：坏 key 只允许显示这句话


class LLMError(Exception):
    """LLM 调用失败的统一中文异常（不携带任何 key 内容）。"""


def load_api_key() -> str | None:
    """按顺序读取 API key：环境变量 DEEPSEEK_API_KEY → 项目根 .env 文件。

    本函数及所有调用方都严禁打印 key 内容；未配置时返回 None。
    """
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key.strip():
        return key.strip()
    # 回退：项目根 .env（KEY=VALUE 格式，逐行解析；同名键取最后一个非空值）
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "DEEPSEEK_API_KEY" and value.strip():
                key = value.strip()
    return key or None


def _sanitize(text: str) -> str:
    """把文本中可能出现的 API key 片段替换为 ***，防止任何路径泄密。"""
    if not text:
        return text
    key = load_api_key()
    if key and key in text:
        text = text.replace(key, "***")
    return text


def _safe_message(exc: Exception) -> str:
    """从底层异常提取安全的中文消息（经过 key 清洗）。"""
    return _sanitize(str(exc))[:300]


def extract_json(text: str) -> dict:
    """从 LLM 输出中容错提取 JSON 对象（支持 ```json 围栏与前后杂文）。"""
    if not text:
        raise LLMError("LLM 返回空内容，无法解析")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError(f"LLM 输出不是有效 JSON（缺少大括号）：{_sanitize(text[:200])}")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM 输出 JSON 解析失败：{exc}") from exc


class DeepSeekClient:
    """DeepSeek（OpenAI 兼容）客户端：150s 超时 + 指数退避重试 + 中文异常。"""

    def __init__(self, api_key: str | None = None,
                 base_url: str = DEEPSEEK_BASE_URL,
                 model: str = DEEPSEEK_MODEL) -> None:
        self.api_key = api_key or load_api_key()
        if not self.api_key:
            raise LLMError(f"{KEY_HINT}（未在环境变量 DEEPSEEK_API_KEY 或项目根 .env 中找到）")
        self.model = model
        # max_retries=0：禁用 SDK 内置重试，由本类按指数退避策略自行控制
        self._client = openai.OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=REQUEST_TIMEOUT,
            max_retries=0,
        )

    def chat(self, messages: list[dict], temperature: float = 0.3,
             max_tokens: int = 2048) -> str:
        """带指数退避重试的单轮对话，返回 assistant 的文本内容。

        重试策略（硬性）：
            - 可重试：429 / 500 / 502 / 503 / 请求超时 / 连接错误 → 指数退避 1s/2s/4s，最多 3 次
            - 不可重试：401 / 400 / 403 / 404 等 → 立即以中文 LLMError 抛出
        """
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content or ""
                if not content.strip():
                    # 推理模型偶发返回空（HTTP 200 但无内容）：显式报错，避免下游 JSON 解析出不可理解的错误
                    raise LLMError("模型返回空响应（服务波动或推理超时），请重试")
                return content
            except openai.APITimeoutError as exc:
                # 超时（TimeoutError 类）：单独处理
                last_error = f"请求超时（>{REQUEST_TIMEOUT:.0f}s）"
                if attempt == MAX_RETRIES:
                    raise LLMError(
                        f"LLM 调用失败：{last_error}，已按指数退避重试 {MAX_RETRIES} 次仍失败"
                    ) from exc
            except openai.APIConnectionError as exc:
                # 连接类错误：按可重试处理
                last_error = "无法连接 DeepSeek 服务（网络错误）"
                if attempt == MAX_RETRIES:
                    raise LLMError(
                        f"LLM 调用失败：{last_error}，已按指数退避重试 {MAX_RETRIES} 次仍失败"
                    ) from exc
            except openai.APIStatusError as exc:
                # HTTP 状态错误（HTTPStatusError 类）：单独处理
                if exc.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                    last_error = f"服务端错误 HTTP {exc.status_code}"
                elif exc.status_code == 401:
                    # 坏 key：只提示统一文案，不暴露任何 key 相关内容
                    raise LLMError(f"{KEY_HINT}（DeepSeek 认证失败，HTTP 401）") from exc
                else:
                    raise LLMError(
                        f"LLM 调用失败：HTTP {exc.status_code} —— {_safe_message(exc)}"
                    ) from exc
            # 指数退避：第 0 次失败后等 1s，第 1 次等 2s，第 2 次等 4s
            time.sleep(2 ** attempt)
        raise LLMError(f"LLM 调用失败：{last_error}，已按指数退避重试 {MAX_RETRIES} 次仍失败")
