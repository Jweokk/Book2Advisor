# Book2Advisor Web Advisor 镜像
# 构建上下文 = 项目根（docker-compose.yml 中 build.context: ..）
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制运行时所需目录（容器布局：core/schemas/data/methods/web）
COPY core/ ./core/
COPY schemas/ ./schemas/
COPY data/methods/ ./data/methods/
COPY web/ ./web/

# 非 root 运行
RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "web.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
