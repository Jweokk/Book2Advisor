# -*- coding: utf-8 -*-
"""Book2Advisor — FastAPI 入口（异步任务版）。

路由：
    GET    /health         健康检查（供 Docker healthcheck）
    POST   /api/ask        提交问题 → 立即返回 {task_id}（后台异步推理，不阻塞）
    GET    /api/task/<id>  查询任务状态 {status: pending|running|done|error, result?}
    GET    /{path:path}    静态文件 catch-all（必须放在所有 API 路由之后）

异步化动机：/api/ask 的 run_chain 平均 60-80s，波动可超 100s —— 提交即返回
task_id，前端轮询结果，避免同步长连接被网关超时中断。

任务存储：进程内 dict（单容器够用）；任务带创建时间，超过 30 分钟清理。
"""

import logging
import mimetypes
import sys
import threading
import time
import uuid
from pathlib import Path

# 项目根（web/app/main.py → 项目根），保证 `cd web && uvicorn app.main:app` 能 import core.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import advisor


logger = logging.getLogger("book2advisor.web")

app = FastAPI(title="Book2Advisor", docs_url=None, redoc_url=None, openapi_url=None)

# ---------- 异步任务存储（进程内） ----------
# {task_id: {"status": ..., "created": float, "result": dict|None, "error": str|None, "question": str}}
TASKS: dict[str, dict] = {}
TASKS_LOCK = threading.Lock()
TASK_TTL = 30 * 60  # 30 分钟


def _cleanup_tasks() -> None:
    """清理超过 TTL 的过期任务（防止内存泄漏）。"""
    now = time.time()
    with TASKS_LOCK:
        stale = [tid for tid, t in TASKS.items() if now - t["created"] > TASK_TTL]
        for tid in stale:
            del TASKS[tid]


def _run_task(task_id: str, question: str) -> None:
    """后台线程：执行 run_chain，结果写回 TASKS[task_id]。"""
    try:
        result = advisor.ask(question)
        with TASKS_LOCK:
            TASKS[task_id]["status"] = "done"
            TASKS[task_id]["result"] = result
    except Exception:
        logger.exception("后台任务 %s 失败：%s", task_id, question[:100])
        with TASKS_LOCK:
            TASKS[task_id]["status"] = "error"
            TASKS[task_id]["error"] = "分析失败，请稍后重试"


@app.get("/health")
def health():
    """无认证健康检查（供 Docker healthcheck）。"""
    return {"status": "ok"}


async def _read_json(request: Request) -> dict:
    """读取请求 JSON；非法请求体返回空 dict 由调用方按 400 处理。"""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


@app.post("/api/ask")
async def api_ask(request: Request):
    """提交问题 → 创建后台任务 → 立即返回 {task_id}（不阻塞，无 CF 超时风险）。"""
    body = await _read_json(request)
    question = (body.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "问题不能为空"}, status_code=400)

    _cleanup_tasks()
    task_id = uuid.uuid4().hex[:16]
    with TASKS_LOCK:
        TASKS[task_id] = {
            "status": "pending",
            "created": time.time(),
            "result": None,
            "error": None,
            "question": question,
        }

    def _worker():
        with TASKS_LOCK:
            TASKS[task_id]["status"] = "running"
        _run_task(task_id, question)

    threading.Thread(target=_worker, daemon=True).start()
    return JSONResponse({"task_id": task_id, "status": "pending"})


@app.get("/api/task/{task_id}")
async def api_task_status(task_id: str):
    """查询任务状态：pending / running / done / error。"""
    with TASKS_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return JSONResponse({"error": "任务不存在或已过期"}, status_code=404)
        resp = {
            "task_id": task_id,
            "status": task["status"],
            "question": task["question"],
        }
        if task["status"] == "done":
            resp["result"] = task["result"]
        elif task["status"] == "error":
            resp["error"] = task["error"]
    return JSONResponse(resp)


# ---------- 静态文件 catch-all（必须放在所有 API 路由定义之后） ----------

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/{path:path}", include_in_schema=False)
def static_files(path: str):
    """静态文件服务：/ → index.html；防目录穿越；404 返回中文 JSON。
    """
    filename = "index.html" if path in ("", "/") else path
    target = (STATIC_DIR / filename).resolve()
    static_root = STATIC_DIR.resolve()
    if not target.is_relative_to(static_root) or not target.is_file():
        return JSONResponse({"error": "页面不存在"}, status_code=404)
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type or "application/octet-stream")
