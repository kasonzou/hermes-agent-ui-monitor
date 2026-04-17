"""
数据分析 API 端点
"""
from fastapi import APIRouter, Depends, Query
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.core.state_db import get_state_db

router = APIRouter()


@router.get("")
async def get_insights(
    days: int = Query(30, ge=1, le=365),
    _: str = Depends(verify_api_key)
):
    """获取使用洞察"""
    try:
        # 从数据库获取统计
        db = get_state_db()
        stats = db.get_stats()

        # 尝试从 CLI 获取更多洞察
        try:
            cli = get_hermes_cli()
            cli_insights = await cli.get_insights(days=days)
        except HermesCLIError:
            cli_insights = {}

        return create_response(data={
            "period": {"days": days},
            "stats": stats,
            "insights": cli_insights
        })
    except Exception as e:
        return create_response(code=1000, reason=str(e), data=None)


@router.get("/models")
async def get_model_stats(_: str = Depends(verify_api_key)):
    """获取模型使用统计"""
    try:
        db = get_state_db()
        # 这里需要根据实际数据库结构查询
        # 简化返回基本统计
        stats = db.get_stats()
        return create_response(data={"model_stats": stats})
    except Exception as e:
        return create_response(code=1000, reason=str(e), data=None)
