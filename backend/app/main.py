"""
FastAPI 主应用入口
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v1.router import api_router
from app.api.ws.router import router as ws_router
from app.services import get_monitor_service, get_log_collector, get_job_queue

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # 启动服务
    monitor_service = get_monitor_service()
    log_collector = get_log_collector()
    job_queue = get_job_queue()

    await job_queue.start()
    await log_collector.start()
    await monitor_service.start()

    logger.info("All services started")

    yield

    # 关闭时的清理
    logger.info(f"Shutting down {settings.app_name}")

    await monitor_service.stop()
    await log_collector.stop()
    await job_queue.stop()

    logger.info("All services stopped")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Hermes Agent Monitor API - 监控和管理 Hermes Agent",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 1000,
            "reason": f"Internal server error: {str(exc)}",
            "data": None
        }
    )


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "code": 0,
        "reason": "success",
        "data": {
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version
        }
    }


# 注册 API 路由
app.include_router(api_router, prefix="/api/v1")

# 注册 WebSocket 路由
app.include_router(ws_router)


@app.get("/")
async def root():
    """根路径重定向到文档"""
    return {
        "code": 0,
        "reason": "success",
        "data": {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "api": "/api/v1"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers
    )
