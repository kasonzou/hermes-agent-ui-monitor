"""
API v1 路由聚合
"""
from fastapi import APIRouter
from app.api.v1.endpoints import (
    sessions, config, gateway, auth, skills,
    logs, insights, system, proxy
)

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(gateway.router, prefix="/gateway", tags=["gateway"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(proxy.router, prefix="/proxy", tags=["proxy"])
