"""
日志查询 API 端点
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.core.security import verify_api_key, create_response
from app.core.state_db import get_state_db

router = APIRouter()


@router.get("")
async def get_logs(
    component: Optional[str] = Query(None, description="组件过滤"),
    level: Optional[str] = Query(None, description="日志级别"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key)
):
    """查询日志"""
    try:
        db = get_state_db()
        logs = db.get_recent_logs(limit=limit, level=level, component=component)

        return create_response(data={
            "logs": logs,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": len(logs)
            }
        })
    except Exception as e:
        return create_response(code=1000, reason=str(e), data=None)


@router.get("/errors")
async def get_error_logs(
    limit: int = Query(50, ge=1, le=500),
    _: str = Depends(verify_api_key)
):
    """获取错误日志"""
    try:
        db = get_state_db()
        logs = db.get_recent_logs(limit=limit, level="ERROR")

        return create_response(data={"logs": logs})
    except Exception as e:
        return create_response(code=1000, reason=str(e), data=None)
