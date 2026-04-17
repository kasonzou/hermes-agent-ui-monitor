"""
WebSocket 消息处理器
处理各类 WebSocket 消息（S->C 和 C->S）
"""
import logging
import time
from typing import Optional
from app.api.ws.manager import get_websocket_manager
from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.core.state_db import get_state_db

logger = logging.getLogger(__name__)


class MessageHandler:
    """WebSocket 消息处理器"""

    def __init__(self):
        self.ws_manager = get_websocket_manager()
        self.cli = get_hermes_cli()
        self.db = get_state_db()

    async def handle_message(self, client_id: str, message: dict):
        """
        处理客户端消息
        """
        msg_type = message.get("type")
        payload = message.get("payload", {})
        msg_id = message.get("id", f"msg_{int(time.time() * 1000)}")

        logger.debug(f"Handling message from {client_id}: {msg_type}")

        handlers = {
            "subscribe": self._handle_subscribe,
            "unsubscribe": self._handle_unsubscribe,
            "approval.response": self._handle_approval_response,
            "interrupt": self._handle_interrupt,
            "command.execute": self._handle_command_execute,
            "ping": self._handle_ping,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(client_id, msg_id, payload)
        else:
            logger.warning(f"Unknown message type: {msg_type}")
            await self._send_error(client_id, msg_id, f"Unknown message type: {msg_type}")

    async def _handle_subscribe(self, client_id: str, msg_id: str, payload: dict):
        """处理订阅请求"""
        events = payload.get("events", [])
        session_id = payload.get("session_id")

        if events:
            self.ws_manager.subscribe(client_id, events)

        if session_id:
            self.ws_manager.subscribe_session(client_id, session_id)

        await self.ws_manager.send_to(client_id, {
            "id": msg_id,
            "type": "subscribe.response",
            "direction": "S->C",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "code": 0,
                "reason": "success",
                "data": {
                    "subscribed": events,
                    "session_id": session_id
                }
            }
        })

    async def _handle_unsubscribe(self, client_id: str, msg_id: str, payload: dict):
        """处理取消订阅请求"""
        events = payload.get("events", [])

        if events:
            self.ws_manager.unsubscribe(client_id, events)

        await self.ws_manager.send_to(client_id, {
            "id": msg_id,
            "type": "unsubscribe.response",
            "direction": "S->C",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "code": 0,
                "reason": "success",
                "data": {"unsubscribed": events}
            }
        })

    async def _handle_approval_response(self, client_id: str, msg_id: str, payload: dict):
        """处理审批响应"""
        request_id = payload.get("request_id")
        approved = payload.get("approved", False)
        reason = payload.get("reason", "")

        logger.info(f"Approval response from {client_id}: request={request_id}, approved={approved}")

        await self.ws_manager.send_to(client_id, {
            "id": msg_id,
            "type": "approval.response.response",
            "direction": "S->C",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "code": 0,
                "reason": "success",
                "data": {
                    "request_id": request_id,
                    "processed": True
                }
            }
        })

    async def _handle_interrupt(self, client_id: str, msg_id: str, payload: dict):
        """处理中断请求"""
        session_id = payload.get("session_id")

        logger.info(f"Interrupt request from {client_id} for session {session_id}")

        await self.ws_manager.send_to(client_id, {
            "id": msg_id,
            "type": "interrupt.response",
            "direction": "S->C",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "code": 0,
                "reason": "success",
                "data": {
                    "session_id": session_id,
                    "interrupted": True
                }
            }
        })

    async def _handle_command_execute(self, client_id: str, msg_id: str, payload: dict):
        """处理命令执行请求"""
        command = payload.get("command", [])
        is_async = payload.get("async", False)

        if not command:
            await self._send_error(client_id, msg_id, "Command is required")
            return

        try:
            if is_async:
                await self.ws_manager.send_to(client_id, {
                    "id": msg_id,
                    "type": "command.execute.response",
                    "direction": "S->C",
                    "timestamp": int(time.time() * 1000),
                    "payload": {
                        "code": 0,
                        "reason": "success",
                        "data": {
                            "task_id": f"task_{int(time.time() * 1000)}",
                            "status": "pending"
                        }
                    }
                })
            else:
                result = await self.cli.run(command)

                await self.ws_manager.send_to(client_id, {
                    "id": msg_id,
                    "type": "command.execute.response",
                    "direction": "S->C",
                    "timestamp": int(time.time() * 1000),
                    "payload": {
                        "code": 0 if result.returncode == 0 else 1005,
                        "reason": "success" if result.returncode == 0 else result.stderr,
                        "data": {
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "returncode": result.returncode,
                            "duration_ms": result.duration_ms
                        }
                    }
                })

        except HermesCLIError as e:
            await self._send_error(client_id, msg_id, str(e))

    async def _handle_ping(self, client_id: str, msg_id: str, payload: dict):
        """处理心跳 ping"""
        self.ws_manager.update_heartbeat(client_id)

        await self.ws_manager.send_to(client_id, {
            "id": msg_id,
            "type": "pong",
            "direction": "S->C",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "code": 0,
                "reason": "success",
                "data": {
                    "server_time": int(time.time() * 1000)
                }
            }
        })

    async def _send_error(self, client_id: str, msg_id: str, error_message: str, code: int = 1000):
        """发送错误响应"""
        await self.ws_manager.send_to(client_id, {
            "id": msg_id,
            "type": "error",
            "direction": "S->C",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "code": code,
                "reason": error_message,
                "data": None
            }
        })


# 消息推送辅助函数

async def push_system_status(status: dict):
    """推送系统状态更新"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast_to_subscribers("system.status", {
        "id": f"sys_{int(time.time() * 1000)}",
        "type": "system.status",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": status
        }
    })


async def push_agent_status(agent_id: str, status: dict):
    """推送 Agent 状态更新"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast_to_subscribers("agent.status", {
        "id": f"agent_{int(time.time() * 1000)}",
        "type": "agent.status",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": {
                "agent_id": agent_id,
                **status
            }
        }
    })


async def push_log_entry(log_entry: dict):
    """推送日志条目"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast_to_subscribers("log.stream", {
        "id": f"log_{int(time.time() * 1000)}",
        "type": "log.stream",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": log_entry
        }
    })


async def push_tool_progress(tool_call_id: str, progress: dict):
    """推送工具执行进度"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast_to_subscribers("tool.progress", {
        "id": f"tool_{int(time.time() * 1000)}",
        "type": "tool.progress",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": {
                "tool_call_id": tool_call_id,
                **progress
            }
        }
    })


async def push_approval_request(request_id: str, request: dict):
    """推送审批请求"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast_to_subscribers("approval.request", {
        "id": f"approval_{int(time.time() * 1000)}",
        "type": "approval.request",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": {
                "request_id": request_id,
                **request
            }
        }
    })


async def push_session_event(event_type: str, session_id: str, data: dict):
    """推送会话事件"""
    ws_manager = get_websocket_manager()

    message = {
        "id": f"session_{int(time.time() * 1000)}",
        "type": "session.event",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": {
                "event_type": event_type,
                "session_id": session_id,
                **data
            }
        }
    }

    await ws_manager.broadcast_to_subscribers("session.event", message)
    await ws_manager.broadcast_to_session_subscribers(session_id, message)


async def push_gateway_status(status: dict):
    """推送网关状态"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast_to_subscribers("gateway.status", {
        "id": f"gateway_{int(time.time() * 1000)}",
        "type": "gateway.status",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": status
        }
    })


async def push_heartbeat():
    """推送服务端心跳"""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast({
        "id": f"hb_{int(time.time() * 1000)}",
        "type": "heartbeat",
        "direction": "S->C",
        "timestamp": int(time.time() * 1000),
        "payload": {
            "code": 0,
            "reason": "success",
            "data": {
                "server_time": int(time.time() * 1000),
                "connections": len(ws_manager.active_connections)
            }
        }
    })


_message_handler: Optional[MessageHandler] = None


def get_message_handler() -> MessageHandler:
    """获取消息处理器单例"""
    global _message_handler
    if _message_handler is None:
        _message_handler = MessageHandler()
    return _message_handler
