"""
WebSocket 连接管理器
管理客户端连接、订阅和消息广播
"""
import asyncio
import json
import logging
import time
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # 活跃连接: client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

        # 订阅管理: event_type -> set of client_ids
        self.subscriptions: Dict[str, Set[str]] = {}

        # 会话订阅: session_id -> set of client_ids
        self.session_subscriptions: Dict[str, Set[str]] = {}

        # 客户端元数据: client_id -> metadata
        self.client_metadata: Dict[str, Dict[str, Any]] = {}

        # 心跳管理
        self.last_heartbeat: Dict[str, float] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> bool:
        """
        建立 WebSocket 连接

        Returns:
            bool: 连接是否成功
        """
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.last_heartbeat[client_id] = time.time()
            self.client_metadata[client_id] = {
                "connected_at": time.time(),
                "subscriptions": []
            }

            logger.info(f"WebSocket client connected: {client_id}")

            # 发送连接成功消息
            await self.send_to(client_id, {
                "id": f"conn_{int(time.time() * 1000)}",
                "type": "connected",
                "direction": "S->C",
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "code": 0,
                    "reason": "success",
                    "data": {
                        "client_id": client_id,
                        "message": "Connected to Hermes Monitor"
                    }
                }
            })

            return True

        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {e}")
            return False

    def disconnect(self, client_id: str):
        """断开连接并清理资源"""
        logger.info(f"WebSocket client disconnected: {client_id}")

        # 从活跃连接中移除
        if client_id in self.active_connections:
            del self.active_connections[client_id]

        # 从订阅中移除
        for event_type in list(self.subscriptions.keys()):
            self.subscriptions[event_type].discard(client_id)
            if not self.subscriptions[event_type]:
                del self.subscriptions[event_type]

        # 从会话订阅中移除
        for session_id in list(self.session_subscriptions.keys()):
            self.session_subscriptions[session_id].discard(client_id)
            if not self.session_subscriptions[session_id]:
                del self.session_subscriptions[session_id]

        # 清理元数据
        if client_id in self.client_metadata:
            del self.client_metadata[client_id]

        if client_id in self.last_heartbeat:
            del self.last_heartbeat[client_id]

    async def send_to(self, client_id: str, message: dict) -> bool:
        """
        发送消息给特定客户端

        Returns:
            bool: 发送是否成功
        """
        if client_id not in self.active_connections:
            return False

        try:
            websocket = self.active_connections[client_id]
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to {client_id}: {e}")
            self.disconnect(client_id)
            return False

    async def broadcast(self, message: dict) -> int:
        """
        广播给所有客户端

        Returns:
            int: 成功发送的客户端数量
        """
        disconnected = []
        success_count = 0

        for client_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.send_json(message)
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to {client_id}: {e}")
                disconnected.append(client_id)

        # 清理断开的连接
        for client_id in disconnected:
            self.disconnect(client_id)

        return success_count

    async def broadcast_to_subscribers(self, event_type: str, message: dict) -> int:
        """
        广播给特定事件的订阅者

        Returns:
            int: 成功发送的客户端数量
        """
        subscribers = self.subscriptions.get(event_type, set())
        if not subscribers:
            return 0

        success_count = 0
        disconnected = []

        for client_id in subscribers:
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].send_json(message)
                    success_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to subscriber {client_id}: {e}")
                    disconnected.append(client_id)
            else:
                disconnected.append(client_id)

        # 清理断开的连接
        for client_id in disconnected:
            self.disconnect(client_id)

        return success_count

    async def broadcast_to_session_subscribers(self, session_id: str, message: dict) -> int:
        """
        广播给特定会话的订阅者

        Returns:
            int: 成功发送的客户端数量
        """
        subscribers = self.session_subscriptions.get(session_id, set())
        if not subscribers:
            return 0

        success_count = 0
        disconnected = []

        for client_id in subscribers:
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].send_json(message)
                    success_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to session subscriber {client_id}: {e}")
                    disconnected.append(client_id)
            else:
                disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)

        return success_count

    def subscribe(self, client_id: str, event_types: list[str]):
        """订阅事件"""
        for event_type in event_types:
            if event_type not in self.subscriptions:
                self.subscriptions[event_type] = set()
            self.subscriptions[event_type].add(client_id)

            # 更新客户端元数据
            if client_id in self.client_metadata:
                if event_type not in self.client_metadata[client_id]["subscriptions"]:
                    self.client_metadata[client_id]["subscriptions"].append(event_type)

        logger.debug(f"Client {client_id} subscribed to: {event_types}")

    def unsubscribe(self, client_id: str, event_types: list[str]):
        """取消订阅事件"""
        for event_type in event_types:
            if event_type in self.subscriptions:
                self.subscriptions[event_type].discard(client_id)
                if not self.subscriptions[event_type]:
                    del self.subscriptions[event_type]

            # 更新客户端元数据
            if client_id in self.client_metadata:
                if event_type in self.client_metadata[client_id]["subscriptions"]:
                    self.client_metadata[client_id]["subscriptions"].remove(event_type)

        logger.debug(f"Client {client_id} unsubscribed from: {event_types}")

    def subscribe_session(self, client_id: str, session_id: str):
        """订阅特定会话的消息"""
        if session_id not in self.session_subscriptions:
            self.session_subscriptions[session_id] = set()
        self.session_subscriptions[session_id].add(client_id)
        logger.debug(f"Client {client_id} subscribed to session: {session_id}")

    def unsubscribe_session(self, client_id: str, session_id: str):
        """取消订阅会话"""
        if session_id in self.session_subscriptions:
            self.session_subscriptions[session_id].discard(client_id)
            if not self.session_subscriptions[session_id]:
                del self.session_subscriptions[session_id]
        logger.debug(f"Client {client_id} unsubscribed from session: {session_id}")

    def update_heartbeat(self, client_id: str):
        """更新心跳时间"""
        self.last_heartbeat[client_id] = time.time()

    async def check_heartbeats(self, timeout: float = 60.0):
        """
        检查心跳，断开超时连接

        Args:
            timeout: 超时时间（秒）
        """
        now = time.time()
        disconnected = []

        for client_id, last_time in list(self.last_heartbeat.items()):
            if now - last_time > timeout:
                logger.warning(f"Client {client_id} heartbeat timeout")
                disconnected.append(client_id)

        for client_id in disconnected:
            # 尝试发送关闭消息
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].close()
                except:
                    pass
            self.disconnect(client_id)

    def get_stats(self) -> dict:
        """获取连接统计"""
        return {
            "total_connections": len(self.active_connections),
            "event_subscriptions": {k: len(v) for k, v in self.subscriptions.items()},
            "session_subscriptions": {k: len(v) for k, v in self.session_subscriptions.items()},
            "clients": list(self.active_connections.keys())
        }


# 全局 WebSocket 管理器实例
_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """获取 WebSocket 管理器单例"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
