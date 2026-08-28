# -*- coding: utf-8 -*-
"""Book2Advisor — 密码门与会话认证。

- 密码只从环境变量 ADVISOR_PASSWORD 读取；未设置则拒绝启动（禁止硬编码默认密码）
- 登录成功签发随机 session token（secrets.token_hex(32)），服务端内存 dict 保存
- 密码比对使用 hmac.compare_digest
- 中间件：除 /api/auth、/health、静态资源外全部要求登录
    - API 路径未登录 → JSONResponse(401)（禁止 raise HTTPException，会变 500）
    - 页面路径未登录 → 302 跳转 /login.html
- 所有响应统一追加 Cache-Control: no-cache, no-store, must-revalidate（防 CF 缓存）
"""

import hmac
import os
import secrets
import time

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

SESSION_COOKIE = "advisor_session"
SESSION_TTL = 7 * 24 * 3600  # 会话有效期：7 天

# 公开路径：登录接口、健康检查、登录页
PUBLIC_PATHS = {"/api/auth", "/health", "/login.html"}
# 公开静态资源后缀（CSS/JS/图片等；.html 页面本身不在此列，需登录）
STATIC_SUFFIXES = (
    ".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".woff", ".woff2", ".ttf", ".map",
)

PASSWORD = os.environ.get("ADVISOR_PASSWORD", "")

# 服务端内存会话表：token -> 签发时间（单用户场景；进程重启即失效，可接受）
_sessions: dict[str, float] = {}


def validate_config() -> None:
    """启动校验：ADVISOR_PASSWORD 未设置则拒绝启动（fail-fast）。"""
    if not PASSWORD:
        raise RuntimeError(
            "环境变量 ADVISOR_PASSWORD 未设置，拒绝启动"
            "（访问密码必须通过环境变量提供，禁止硬编码默认值）"
        )


def create_session() -> str:
    """签发随机 session token 并登记。"""
    _prune()
    token = secrets.token_hex(32)
    _sessions[token] = time.time()
    return token


def check_session(token) -> bool:
    """校验 token 是否有效（存在且未过期）；过期即清除。"""
    if not token or token not in _sessions:
        return False
    if time.time() - _sessions[token] > SESSION_TTL:
        _sessions.pop(token, None)
        return False
    return True


def _prune() -> None:
    """清理过期会话，防止内存无限增长。"""
    now = time.time()
    expired = [t for t, ts in _sessions.items() if now - ts > SESSION_TTL]
    for t in expired:
        _sessions.pop(t, None)


async def login(request: Request) -> JSONResponse:
    """POST /api/auth：校验密码；成功则签发会话 cookie。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体不是有效 JSON"}, status_code=400)
    password = (body or {}).get("password", "")
    if not isinstance(password, str) or not password:
        return JSONResponse({"error": "缺少密码字段"}, status_code=400)
    if not hmac.compare_digest(password.encode("utf-8"), PASSWORD.encode("utf-8")):
        return JSONResponse({"error": "密码错误"}, status_code=401)
    token = create_session()
    resp = JSONResponse({"ok": True, "message": "登录成功"})
    resp.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_TTL, path="/",
        httponly=True, samesite="lax",
        secure=(request.url.scheme == "https"),
    )
    return resp


class SessionAuthMiddleware:
    """认证 + 统一 Cache-Control 中间件（纯 ASGI，无 BaseHTTPMiddleware 开销）。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path = request.url.path
        is_api = path.startswith("/api/")
        is_public = path in PUBLIC_PATHS or (
            not is_api and path.endswith(STATIC_SUFFIXES)
        )
        if not is_public:
            token = request.cookies.get(SESSION_COOKIE)
            if not check_session(token):
                if is_api:
                    response = JSONResponse(
                        {"error": "未登录或会话已过期"}, status_code=401
                    )
                else:
                    response = RedirectResponse("/login.html", status_code=302)
                await response(scope, receive, send)
                return
        await self._forward(scope, receive, send)

    async def _forward(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # 所有响应禁止缓存（防 Cloudflare 默认缓存 4 小时）
                MutableHeaders(scope=message).append(
                    "Cache-Control", "no-cache, no-store, must-revalidate"
                )
            await send(message)
        await self.app(scope, receive, send_wrapper)
