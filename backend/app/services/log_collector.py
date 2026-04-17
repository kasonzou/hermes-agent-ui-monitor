"""
日志收集服务
实时监控和收集 Hermes 日志，推送到 WebSocket
"""
import asyncio
import logging
import json
import re
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from dataclasses import dataclass, asdict

from app.api.ws.handlers import push_log_entry
from app.core.hermes_cli import get_hermes_cli
from app.api.ws.manager import get_websocket_manager

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str
    source: str
    message: str
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "metadata": self.metadata or {}
        }


class LogCollector:
    """日志收集器 - 实时监控 Hermes 日志"""

    # 日志级别映射
    LOG_LEVELS = {
        "DEBUG": "debug",
        "INFO": "info",
        "WARNING": "warning",
        "WARN": "warning",
        "ERROR": "error",
        "CRITICAL": "critical",
        "FATAL": "critical",
    }

    def __init__(self):
        self.cli = get_hermes_cli()
        self.ws_manager = get_websocket_manager()

        self._running = False
        self._collect_task = None
        self._callbacks: list[Callable[[LogEntry], None]] = []

        # 日志解析正则表达式
        self._log_patterns = [
            # 标准格式: 2024-01-15 10:30:45,123 [INFO] module: message
            re.compile(
                r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d{3})?)\s+\[(\w+)\]\s+(\S+):\s+(.*)$"
            ),
            # JSON 格式
            re.compile(r"^\{.*\}$"),
            # 简化格式: [LEVEL] message
            re.compile(r"^\[(\w+)\]\s+(.*)$"),
        ]

        # 统计
        self.stats = {
            "total_logs": 0,
            "logs_by_level": {},
            "start_time": None,
        }

    async def start(self):
        """启动日志收集"""
        if self._running:
            return

        self._running = True
        self.stats["start_time"] = time.time()
        logger.info("Starting log collector...")

        self._collect_task = asyncio.create_task(self._collect_logs())
        logger.info("Log collector started")

    async def stop(self):
        """停止日志收集"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping log collector...")

        if self._collect_task:
            self._collect_task.cancel()
            try:
                await self._collect_task
            except asyncio.CancelledError:
                pass

        self._collect_task = None
        logger.info("Log collector stopped")

    def add_callback(self, callback: Callable[[LogEntry], None]):
        """添加日志回调函数"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[LogEntry], None]):
        """移除日志回调函数"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _collect_logs(self):
        """收集日志的主循环"""
        # 使用 hermes logs -f 命令实时获取日志
        command = ["logs", "-f", "-n", "100"]

        try:
            process = await asyncio.create_subprocess_exec(
                self.cli.hermes_path or "hermes",
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            logger.info(f"Started log collection process: {process.pid}")

            while self._running:
                try:
                    # 使用 wait_for 避免阻塞
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=1.0
                    )

                    if not line:
                        # 进程可能已结束
                        if process.returncode is not None:
                            logger.warning("Log process ended, restarting...")
                            await asyncio.sleep(2)
                            process = await asyncio.create_subprocess_exec(
                                self.cli.hermes_path or "hermes",
                                *command,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            continue
                        else:
                            await asyncio.sleep(0.1)
                            continue

                    # 解析日志行
                    log_line = line.decode("utf-8", errors="replace").strip()
                    if log_line:
                        await self._process_log_line(log_line)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error reading log line: {e}")

        except Exception as e:
            logger.error(f"Log collection error: {e}")

    async def _process_log_line(self, line: str):
        """处理单行日志"""
        entry = self._parse_log_line(line)

        # 更新统计
        self.stats["total_logs"] += 1
        self.stats["logs_by_level"][entry.level] = \
            self.stats["logs_by_level"].get(entry.level, 0) + 1

        # 推送到 WebSocket
        await push_log_entry(entry.to_dict())

        # 调用回调函数
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                logger.error(f"Log callback error: {e}")

    def _parse_log_line(self, line: str) -> LogEntry:
        """解析日志行"""
        # 尝试 JSON 格式
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                return LogEntry(
                    timestamp=data.get("timestamp", datetime.now().isoformat()),
                    level=self.LOG_LEVELS.get(
                        data.get("level", "INFO").upper(),
                        "info"
                    ),
                    source=data.get("source", "hermes"),
                    message=data.get("message", line),
                    session_id=data.get("session_id"),
                    agent_id=data.get("agent_id"),
                    metadata=data.get("metadata")
                )
            except json.JSONDecodeError:
                pass

        # 尝试标准格式
        for pattern in self._log_patterns[:-1]:  # 排除 JSON 模式
            match = pattern.match(line)
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    return LogEntry(
                        timestamp=groups[0],
                        level=self.LOG_LEVELS.get(groups[1].upper(), "info"),
                        source=groups[2],
                        message=groups[3]
                    )
                elif len(groups) == 2:
                    return LogEntry(
                        timestamp=datetime.now().isoformat(),
                        level=self.LOG_LEVELS.get(groups[0].upper(), "info"),
                        source="hermes",
                        message=groups[1]
                    )

        # 默认格式
        return LogEntry(
            timestamp=datetime.now().isoformat(),
            level="info",
            source="hermes",
            message=line
        )

    async def get_recent_logs(self, lines: int = 100, level: Optional[str] = None) -> list:
        """获取最近的日志"""
        try:
            result = await self.cli.run(["logs", "-n", str(lines)])

            if result.returncode != 0:
                logger.warning(f"Failed to get recent logs: {result.stderr}")
                return []

            log_entries = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    entry = self._parse_log_line(line)
                    if level and entry.level != level.lower():
                        continue
                    log_entries.append(entry.to_dict())

            return log_entries

        except Exception as e:
            logger.error(f"Error getting recent logs: {e}")
            return []

    async def search_logs(
        self,
        query: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """搜索日志"""
        # 先获取最近的日志
        logs = await self.get_recent_logs(lines=1000)

        # 过滤
        results = []
        for log in logs:
            # 关键词过滤
            if query and query.lower() not in log.get("message", "").lower():
                continue

            # 级别过滤
            if level and log.get("level") != level.lower():
                continue

            # 时间过滤
            if start_time and log.get("timestamp", "") < start_time:
                continue
            if end_time and log.get("timestamp", "") > end_time:
                continue

            results.append(log)

            if len(results) >= limit:
                break

        return results

    def get_stats(self) -> dict:
        """获取收集器统计"""
        return {
            "running": self._running,
            "total_logs": self.stats["total_logs"],
            "logs_by_level": self.stats["logs_by_level"].copy(),
            "uptime_seconds": time.time() - self.stats["start_time"]
            if self.stats["start_time"] else 0,
            "callback_count": len(self._callbacks)
        }


# 全局日志收集器实例
_log_collector: Optional[LogCollector] = None


def get_log_collector() -> LogCollector:
    """获取日志收集器单例"""
    global _log_collector
    if _log_collector is None:
        _log_collector = LogCollector()
    return _log_collector
