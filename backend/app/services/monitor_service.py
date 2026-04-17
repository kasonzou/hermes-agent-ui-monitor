"""
监控服务
定期收集系统状态、Agent 状态，并推送 WebSocket 事件
"""
import asyncio
import logging
import time
from typing import Optional
from datetime import datetime, timedelta

from app.api.ws.handlers import (
    push_system_status,
    push_agent_status,
    push_gateway_status,
    push_heartbeat,
)
from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.core.state_db import get_state_db
from app.api.ws.manager import get_websocket_manager

logger = logging.getLogger(__name__)


class MonitorService:
    """监控服务 - 定期收集和推送状态信息"""

    def __init__(self):
        self.cli = get_hermes_cli()
        self.db = get_state_db()
        self.ws_manager = get_websocket_manager()

        self._running = False
        self._tasks = []

        # 监控配置
        self.system_status_interval = 30  # 系统状态推送间隔（秒）
        self.agent_status_interval = 10   # Agent 状态推送间隔（秒）
        self.heartbeat_interval = 60      # 心跳推送间隔（秒）
        self.gateway_check_interval = 30  # 网关状态检查间隔（秒）
        self.connection_check_interval = 60  # 连接检查间隔（秒）

    async def start(self):
        """启动监控服务"""
        if self._running:
            return

        self._running = True
        logger.info("Starting monitor service...")

        # 启动后台任务
        self._tasks = [
            asyncio.create_task(self._system_status_loop()),
            asyncio.create_task(self._agent_status_loop()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._gateway_status_loop()),
            asyncio.create_task(self._connection_check_loop()),
        ]

        logger.info("Monitor service started")

    async def stop(self):
        """停止监控服务"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping monitor service...")

        # 取消所有任务
        for task in self._tasks:
            task.cancel()

        # 等待任务完成
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks = []
        logger.info("Monitor service stopped")

    async def _system_status_loop(self):
        """系统状态监控循环"""
        while self._running:
            try:
                await self._collect_and_push_system_status()
            except Exception as e:
                logger.error(f"Error collecting system status: {e}")

            await asyncio.sleep(self.system_status_interval)

    async def _agent_status_loop(self):
        """Agent 状态监控循环"""
        while self._running:
            try:
                await self._collect_and_push_agent_status()
            except Exception as e:
                logger.error(f"Error collecting agent status: {e}")

            await asyncio.sleep(self.agent_status_interval)

    async def _heartbeat_loop(self):
        """心跳推送循环"""
        while self._running:
            try:
                await push_heartbeat()
                logger.debug("Heartbeat pushed")
            except Exception as e:
                logger.error(f"Error pushing heartbeat: {e}")

            await asyncio.sleep(self.heartbeat_interval)

    async def _gateway_status_loop(self):
        """网关状态监控循环"""
        while self._running:
            try:
                await self._check_and_push_gateway_status()
            except Exception as e:
                logger.error(f"Error checking gateway status: {e}")

            await asyncio.sleep(self.gateway_check_interval)

    async def _connection_check_loop(self):
        """连接检查循环 - 检查心跳超时"""
        while self._running:
            try:
                await self.ws_manager.check_heartbeats(timeout=120)
            except Exception as e:
                logger.error(f"Error checking connections: {e}")

            await asyncio.sleep(self.connection_check_interval)

    async def _collect_and_push_system_status(self):
        """收集并推送系统状态"""
        try:
            # 获取系统状态
            result = await self.cli.run(["status", "--format", "json"])

            if result.returncode == 0:
                import json
                try:
                    status_data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    status_data = {"raw": result.stdout}
            else:
                status_data = {
                    "error": result.stderr,
                    "available": False
                }

            # 添加额外信息
            status_data["timestamp"] = int(time.time() * 1000)
            status_data["connections"] = len(self.ws_manager.active_connections)

            # 推送状态
            await push_system_status(status_data)
            logger.debug("System status pushed")

        except HermesCLIError as e:
            logger.warning(f"Failed to get system status: {e}")
            await push_system_status({
                "error": str(e),
                "available": False,
                "timestamp": int(time.time() * 1000)
            })

    async def _collect_and_push_agent_status(self):
        """收集并推送 Agent 状态"""
        try:
            # 获取活跃 Agent
            agents_result = await self.cli.run(["agent", "ls", "--format", "json"])

            if agents_result.returncode == 0:
                import json
                try:
                    agents_data = json.loads(agents_result.stdout)
                    agents = agents_data if isinstance(agents_data, list) else []
                except json.JSONDecodeError:
                    agents = []
            else:
                agents = []

            # 获取会话列表
            sessions_result = await self.cli.run(["session", "ls", "--format", "json"])

            if sessions_result.returncode == 0:
                import json
                try:
                    sessions_data = json.loads(sessions_result.stdout)
                    sessions = sessions_data if isinstance(sessions_data, list) else []
                except json.JSONDecodeError:
                    sessions = []
            else:
                sessions = []

            # 计算统计信息
            active_sessions = len(sessions)
            total_messages = sum(s.get("message_count", 0) for s in sessions)

            status = {
                "agents": agents,
                "agent_count": len(agents),
                "active_sessions": active_sessions,
                "total_messages": total_messages,
                "timestamp": int(time.time() * 1000)
            }

            await push_agent_status("all", status)
            logger.debug(f"Agent status pushed: {len(agents)} agents, {active_sessions} sessions")

        except HermesCLIError as e:
            logger.warning(f"Failed to get agent status: {e}")

    async def _check_and_push_gateway_status(self):
        """检查并推送网关状态"""
        try:
            result = await self.cli.run(["gateway", "status", "--format", "json"])

            if result.returncode == 0:
                import json
                try:
                    gateway_data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    gateway_data = {"running": "unknown", "raw": result.stdout}
            else:
                gateway_data = {"running": False, "error": result.stderr}

            gateway_data["timestamp"] = int(time.time() * 1000)

            await push_gateway_status(gateway_data)
            logger.debug("Gateway status pushed")

        except HermesCLIError as e:
            logger.warning(f"Failed to get gateway status: {e}")

    def get_stats(self) -> dict:
        """获取监控服务统计"""
        return {
            "running": self._running,
            "active_tasks": len(self._tasks),
            "intervals": {
                "system_status": self.system_status_interval,
                "agent_status": self.agent_status_interval,
                "heartbeat": self.heartbeat_interval,
                "gateway_check": self.gateway_check_interval,
                "connection_check": self.connection_check_interval,
            }
        }


# 全局监控服务实例
_monitor_service: Optional[MonitorService] = None


def get_monitor_service() -> MonitorService:
    """获取监控服务单例"""
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = MonitorService()
    return _monitor_service
