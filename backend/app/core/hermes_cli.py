"""
Hermes CLI 执行器
封装所有 hermes 命令调用，支持同步执行、异步执行和流式输出
"""
import asyncio
import os
import json
import re
from dataclasses import dataclass
from typing import Optional, AsyncGenerator, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class CLIResult:
    """CLI 执行结果"""
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int


class HermesCLIError(Exception):
    """Hermes CLI 执行错误"""
    pass


class HermesCLI:
    """Hermes CLI 执行器"""

    def __init__(self, timeout: int = 30, profile: Optional[str] = None):
        self.timeout = timeout
        self.profile = profile or os.environ.get("HERMES_PROFILE", "default")
        self.env = self._prepare_env()

    def _prepare_env(self) -> Dict[str, str]:
        """准备环境变量，确保 hermes 在 PATH 中"""
        home = os.environ.get("HOME", "")
        path = os.environ.get("PATH", "")

        # 添加可能的 hermes 安装路径
        hermes_paths = [
            f"{home}/.local/bin",
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/usr/bin",
        ]

        new_path = ":".join(hermes_paths + [path])

        env = {
            **os.environ,
            "PATH": new_path,
            "HERMES_PROFILE": self.profile,
        }

        return env

    def _build_command(self, args: List[str]) -> List[str]:
        """构建命令列表"""
        cmd = ["hermes"]

        # 添加 profile 参数（如果不是 default）
        if self.profile and self.profile != "default":
            cmd.extend(["--profile", self.profile])

        cmd.extend(args)
        return cmd

    async def run(
        self,
        args: List[str],
        timeout: Optional[int] = None,
        capture_output: bool = True
    ) -> CLIResult:
        """
        异步执行 hermes CLI 命令

        Args:
            args: 命令参数列表
            timeout: 超时时间（秒），默认使用初始化时的 timeout
            capture_output: 是否捕获输出

        Returns:
            CLIResult: 执行结果

        Raises:
            HermesCLIError: 执行失败或超时
        """
        cmd = self._build_command(args)
        timeout = timeout or self.timeout

        logger.debug(f"Executing: {' '.join(cmd)}")

        start_time = asyncio.get_event_loop().time()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                env=self.env
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )

            duration_ms = int(
                (asyncio.get_event_loop().time() - start_time) * 1000
            )

            result = CLIResult(
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
                returncode=proc.returncode,
                duration_ms=duration_ms
            )

            logger.debug(f"Command completed in {duration_ms}ms, returncode={proc.returncode}")

            if proc.returncode != 0 and capture_output:
                logger.warning(f"Command failed: {result.stderr}")

            return result

        except asyncio.TimeoutError:
            proc.kill()
            raise HermesCLIError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        except FileNotFoundError:
            raise HermesCLIError(f"hermes command not found in PATH. Please ensure hermes is installed.")

    async def stream(
        self,
        args: List[str]
    ) -> AsyncGenerator[str, None]:
        """
        流式执行命令（如 logs -f）

        Args:
            args: 命令参数列表

        Yields:
            str: 每一行输出
        """
        cmd = self._build_command(args)

        logger.debug(f"Streaming: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env
        )

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", errors="replace").rstrip()
        finally:
            proc.kill()
            await proc.wait()

    # ===== 常用命令封装 =====

    async def get_status(self) -> Dict[str, Any]:
        """获取 hermes 状态"""
        result = await self.run(["status", "--json"])

        if result.returncode != 0:
            # 尝试解析文本输出
            return self._parse_status_text(result.stdout)

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return self._parse_status_text(result.stdout)

    def _parse_status_text(self, output: str) -> Dict[str, Any]:
        """解析文本格式的状态输出"""
        lines = output.strip().split("\n")
        status = {
            "version": "unknown",
            "config_loaded": False,
            "auth_status": "unknown",
            "components": {}
        }

        for line in lines:
            if "version" in line.lower():
                match = re.search(r'version[:\s]+([^\s]+)', line, re.IGNORECASE)
                if match:
                    status["version"] = match.group(1)
            elif "config" in line.lower() and "loaded" in line.lower():
                status["config_loaded"] = "yes" in line.lower() or "true" in line.lower()

        return status

    async def get_config(self) -> Dict[str, Any]:
        """获取 hermes 配置"""
        result = await self.run(["config", "show"])

        if result.returncode != 0:
            raise HermesCLIError(result.stderr)

        # 尝试解析 YAML/JSON 输出
        try:
            import yaml
            return yaml.safe_load(result.stdout) or {}
        except ImportError:
            # 如果没有 PyYAML，返回原始文本
            return {"raw": result.stdout}
        except Exception:
            return {"raw": result.stdout}

    async def set_config(self, key: str, value: str) -> CLIResult:
        """设置配置项"""
        return await self.run(["config", "set", key, value])

    async def list_sessions(
        self,
        source: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取会话列表"""
        args = ["sessions", "list", "--limit", str(limit)]
        if source:
            args.extend(["--source", source])

        result = await self.run(args)

        if result.returncode != 0:
            raise HermesCLIError(result.stderr)

        # 尝试解析 JSON 输出
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            # 解析表格格式
            return self._parse_table_output(result.stdout)

    def _parse_table_output(self, output: str) -> List[Dict[str, Any]]:
        """解析 hermes 表格输出为字典列表"""
        lines = output.strip().split("\n")
        if len(lines) < 2:
            return []

        # 查找表头行（通常是第一个非空行）
        header_idx = 0
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith("-"):
                header_idx = i
                break

        headers = [h.strip().lower().replace(" ", "_") for h in lines[header_idx].split()]
        results = []

        for line in lines[header_idx + 1:]:
            line = line.strip()
            if not line or line.startswith("-") or line.startswith("="):
                continue

            # 简单的表格解析（假设空格分隔）
            values = line.split()
            if len(values) >= len(headers):
                row = {}
                for i, header in enumerate(headers):
                    row[header] = values[i] if i < len(values) else ""
                results.append(row)

        return results

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话详情（通过导出）"""
        result = await self.run([
            "sessions", "export", "-",
            "--session-id", session_id
        ])

        if result.returncode != 0:
            return None

        try:
            lines = result.stdout.strip().split("\n")
            if lines:
                return json.loads(lines[0])
        except json.JSONDecodeError:
            pass

        return None

    async def rename_session(self, session_id: str, title: str) -> CLIResult:
        """重命名会话"""
        return await self.run(["sessions", "rename", session_id, title])

    async def delete_session(self, session_id: str, confirm: bool = False) -> CLIResult:
        """删除会话"""
        args = ["sessions", "delete", session_id]
        if confirm:
            args.append("--yes")
        return await self.run(args)

    async def prune_sessions(
        self,
        older_than_days: int = 90,
        source: Optional[str] = None,
        confirm: bool = False
    ) -> CLIResult:
        """清理旧会话"""
        args = ["sessions", "prune", "--older-than", str(older_than_days)]
        if source:
            args.extend(["--source", source])
        if confirm:
            args.append("--yes")
        return await self.run(args)

    async def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        result = await self.run(["sessions", "stats"])

        if result.returncode != 0:
            raise HermesCLIError(result.stderr)

        # 解析统计输出
        lines = result.stdout.strip().split("\n")
        stats = {
            "total_sessions": 0,
            "total_messages": 0,
            "by_source": {},
            "raw": result.stdout
        }

        for line in lines:
            if "total sessions" in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    stats["total_sessions"] = int(match.group(1))
            elif "total messages" in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    stats["total_messages"] = int(match.group(1))

        return stats

    async def get_gateway_status(self) -> Dict[str, Any]:
        """获取网关状态"""
        result = await self.run(["gateway", "status"])

        # 解析输出
        output = result.stdout.lower()

        if "running" in output or "active" in output:
            return {
                "running": True,
                "service_type": "systemd" if "systemd" in output else "foreground",
                "raw": result.stdout
            }
        else:
            return {
                "running": False,
                "service_type": "none",
                "raw": result.stdout
            }

    async def start_gateway(self) -> CLIResult:
        """启动网关"""
        return await self.run(["gateway", "start"], timeout=10)

    async def stop_gateway(self) -> CLIResult:
        """停止网关"""
        return await self.run(["gateway", "stop"], timeout=10)

    async def restart_gateway(self) -> CLIResult:
        """重启网关"""
        return await self.run(["gateway", "restart"], timeout=10)

    async def list_skills(self) -> List[Dict[str, Any]]:
        """获取已安装技能列表"""
        result = await self.run(["skills", "list"])

        if result.returncode != 0:
            return []

        return self._parse_table_output(result.stdout)

    async def search_skills(self, query: str) -> List[Dict[str, Any]]:
        """搜索技能"""
        result = await self.run(["skills", "search", query])

        if result.returncode != 0:
            return []

        return self._parse_table_output(result.stdout)

    async def install_skill(self, name: str) -> CLIResult:
        """安装技能"""
        return await self.run(["skills", "install", name], timeout=120)

    async def uninstall_skill(self, name: str) -> CLIResult:
        """卸载技能"""
        return await self.run(["skills", "uninstall", name])

    async def list_auth_providers(self) -> List[Dict[str, Any]]:
        """获取认证提供商列表"""
        result = await self.run(["auth", "list"])

        if result.returncode != 0:
            return []

        return self._parse_table_output(result.stdout)

    async def get_insights(self, days: int = 30) -> Dict[str, Any]:
        """获取使用洞察"""
        result = await self.run(["insights", "--days", str(days)])

        if result.returncode != 0:
            return {"raw": result.stdout}

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"raw": result.stdout}

    async def run_doctor(self) -> Dict[str, Any]:
        """运行诊断"""
        result = await self.run(["doctor"])

        return {
            "healthy": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr if result.returncode != 0 else None
        }


# 全局 CLI 实例
_hermes_cli: Optional[HermesCLI] = None


def get_hermes_cli(profile: Optional[str] = None) -> HermesCLI:
    """获取 Hermes CLI 实例"""
    global _hermes_cli
    if _hermes_cli is None or (profile and _hermes_cli.profile != profile):
        from app.config import settings
        _hermes_cli = HermesCLI(
            timeout=30,
            profile=profile or settings.hermes_profile
        )
    return _hermes_cli
