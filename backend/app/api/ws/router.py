"""
WebSocket 路由
处理 WebSocket 连接和消息
"""
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.config import settings
from app.api.ws.manager import get_websocket_manager
from app.api.ws.handlers import get_message_handler

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="认证令牌"),
    profile: str = Query(default="default", description="Hermes profile")
):
    """
    WebSocket 连接端点

    连接参数:
    - token: API 认证令牌 (?token=xxx)
    - profile: Hermes profile 名称 (?profile=default)
    """
    # 验证 token
    if token != settings.api_key:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    # 生成客户端 ID
    client_id = f"{profile}_{uuid.uuid4().hex[:8]}"

    # 获取管理器和处理器
    ws_manager = get_websocket_manager()
    msg_handler = get_message_handler()

    # 建立连接
    connected = await ws_manager.connect(websocket, client_id)
    if not connected:
        await websocket.close(code=4000, reason="Failed to establish connection")
        return

    logger.info(f"WebSocket connection established: {client_id}")

    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            logger.debug(f"Received message from {client_id}: {data}")

            # 处理消息
            await msg_handler.handle_message(client_id, data)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        ws_manager.disconnect(client_id)


@router.websocket("/ws/stream")
async def websocket_stream_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="认证令牌"),
    event_types: str = Query(default="log.stream", description="订阅的事件类型，逗号分隔")
):
    """
    WebSocket 流式数据端点（简化版）

    仅用于接收流式数据推送，如日志、状态更新等
    """
    # 验证 token
    if token != settings.api_key:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    client_id = f"stream_{uuid.uuid4().hex[:8]}"
    ws_manager = get_websocket_manager()

    # 建立连接
    connected = await ws_manager.connect(websocket, client_id)
    if not connected:
        return

    # 自动订阅指定事件
    events = [e.strip() for e in event_types.split(",")]
    ws_manager.subscribe(client_id, events)

    logger.info(f"WebSocket stream connection established: {client_id}, events: {events}")

    try:
        while True:
            # 保持连接，接收心跳
            data = await websocket.receive_json()

            # 只处理 ping
            if data.get("type") == "ping":
                ws_manager.update_heartbeat(client_id)
                await websocket.send_json({
                    "id": data.get("id", f"pong_{uuid.uuid4().hex[:8]}"),
                    "type": "pong",
                    "direction": "S->C",
                    "timestamp": int(__import__('time').time() * 1000),
                    "payload": {
                        "code": 0,
                        "reason": "success",
                        "data": {"server_time": int(__import__('time').time() * 1000)}
                    }
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket stream disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket stream error for {client_id}: {e}")
    finally:
        ws_manager.disconnect(client_id)
