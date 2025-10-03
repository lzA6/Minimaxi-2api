# main.py (v8.4 终极修正版)

import time
import sys
import json
import uuid
import traceback
from typing import Optional, List, Dict, Any, Callable, Awaitable

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
from loguru import logger

from app.core.config import settings
from app.providers.minimaxi_provider import MinimaxiProvider

# --- 配置 Loguru (保持不变) ---
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True,
    serialize=False
)

# --- 创建 FastAPI 应用 (保持不变) ---
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.DESCRIPTION
)

# 实例化 Provider
provider = MinimaxiProvider()


# --- 高级日志中间件 (已修正请求体重复读取问题) ---
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # 👇 关键修正 1: 使用 try...except 块来处理客户端断开连接
        try:
            # 👇 关键修正 2: 读取 body 并将其存储在 request.state 中
            body = await request.body()
            setattr(request.state, "body", body)

            model_name = "N/A"
            if "/v1/chat/completions" in request.url.path and body:
                try:
                    json_body = json.loads(body)
                    model_name = json_body.get("model", "N/A")
                except json.JSONDecodeError:
                    pass

            logger.info(f"--> [{request.client.host}] Request ID: {request_id} | {request.method} {request.url.path} | Model: {model_name}")

            response = await call_next(request)

        except ClientDisconnect:
            # 当客户端在服务器完全读取请求体之前断开连接时，会发生此情况
            logger.warning(f"--> [{request.client.host}] Request ID: {request_id} | Client disconnected before request was fully processed.")
            return Response(status_code=499, content="Client Closed Request")

        process_time = (time.time() - start_time) * 1000
        formatted_process_time = f"{process_time:.2f}ms"
        
        # 日志记录部分保持不变
        if response.status_code >= 500:
            logger.error(f"<-- [{request.client.host}] Request ID: {request_id} | Finished in {formatted_process_time} with status {response.status_code}")
        elif response.status_code >= 400:
            logger.warning(f"<-- [{request.client.host}] Request ID: {request_id} | Finished in {formatted_process_time} with status {response.status_code}")
        else:
            logger.success(f"<-- [{request.client.host}] Request ID: {request_id} | Finished in {formatted_process_time} with status {response.status_code}")

        return response

app.add_middleware(LoggingMiddleware)


# --- 认证依赖项 (保持不变) ---
async def verify_api_key(authorization: Optional[str] = Header(None)):
    if not settings.API_MASTER_KEY:
        logger.warning("API_MASTER_KEY 未配置，服务将对所有请求开放！")
        return
    if authorization is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization header.")
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer": raise ValueError("Invalid scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authentication scheme. Use 'Bearer <your_api_key>'.")
    if token != settings.API_MASTER_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key.")


# --- API 路由 (已修正以从 request.state 读取 body) ---

@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request):
    try:
        # 👇 关键修正 3: 从 request.state.body 解析 JSON，而不是再次调用 request.json()
        request_data = json.loads(request.state.body)
        return await provider.chat_completion(request_data, request)
    except Exception as e:
        logger.error(f"在 chat_completions 路由中发生严重错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models():
    model_names: List[str] = settings.SUPPORTED_MODELS
    model_data: List[Dict[str, Any]] = []
    for name in model_names:
        model_data.append({
            "id": name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "system"
        })
    return {"object": "list", "data": model_data}


@app.get("/")
def root():
    return {"message": f"Welcome to {settings.APP_NAME}", "version": settings.APP_VERSION}