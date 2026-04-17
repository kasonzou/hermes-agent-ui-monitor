"""
会话管理 API 端点
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.core.state_db import get_state_db

router = APIRouter()


@router.get("")
async def list_sessions(
    source: Optional[str] = Query(None, description="按来源过滤"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key)
):
    """获取会话列表"""
    try:
        db = get_state_db()
        sessions = db.get_sessions(limit=limit, offset=offset, source=source)
        total = db.get_session_count(source=source)

        return create_response(data={
            "sessions": sessions,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(sessions) < total
            }
        })
    except Exception as e:
        # 降级到 CLI
        try:
            cli = get_hermes_cli()
            sessions = await cli.list_sessions(source=source, limit=limit)
            return create_response(data={
                "sessions": sessions,
                "pagination": {"total": len(sessions), "limit": limit, "offset": offset, "has_more": False}
            })
        except HermesCLIError as ce:
            return create_response(code=1005, reason=str(ce), data=None)


@router.get("/{session_id}")
async def get_session(session_id: str, _: str = Depends(verify_api_key)):
    """获取单个会话详情"""
    try:
        db = get_state_db()
        session = db.get_session(session_id)

        if not session:
            return create_response(code=1001, reason=f"Session not found: {session_id}", data=None)

        # 获取消息
        messages = db.get_session_messages(session_id, limit=100)
        session["messages"] = messages

        return create_response(data=session)
    except Exception as e:
        return create_response(code=1000, reason=str(e), data=None)


@router.post("/{session_id}/rename")
async def rename_session(
    session_id: str,
    request: dict,
    _: str = Depends(verify_api_key)
):
    """重命名会话"""
    try:
        title = request.get("title")
        if not title:
            return create_response(code=1002, reason="Title is required", data=None)

        cli = get_hermes_cli()
        result = await cli.rename_session(session_id, title)

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"id": session_id, "title": title})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    confirm: bool = False,
    _: str = Depends(verify_api_key)
):
    """删除会话"""
    try:
        cli = get_hermes_cli()
        result = await cli.delete_session(session_id, confirm=confirm)

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"id": session_id, "deleted": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/prune")
async def prune_sessions(
    request: dict,
    _: str = Depends(verify_api_key)
):
    """清理旧会话"""
    try:
        older_than = request.get("older_than", 90)
        source = request.get("source")
        confirm = request.get("confirm", False)

        cli = get_hermes_cli()
        result = await cli.prune_sessions(
            older_than_days=older_than,
            source=source,
            confirm=confirm
        )

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"pruned": True, "output": result.stdout})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.get("/stats")
async def get_session_stats(_: str = Depends(verify_api_key)):
    """获取会话统计"""
    try:
        db = get_state_db()
        stats = db.get_stats()
        return create_response(data=stats)
    except Exception as e:
        # 降级到 CLI
        try:
            cli = get_hermes_cli()
            stats = await cli.get_session_stats()
            return create_response(data=stats)
        except HermesCLIError as ce:
            return create_response(code=1005, reason=str(ce), data=None)
