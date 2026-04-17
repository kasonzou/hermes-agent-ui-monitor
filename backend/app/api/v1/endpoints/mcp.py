"""
MCP (Model Context Protocol) 管理 API
管理 Hermes Agent 的 MCP 服务器配置
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import verify_api_key, create_response, create_error_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

logger = logging.getLogger(__name__)
router = APIRouter()


class MCPServerCreate(BaseModel):
    """创建 MCP 服务器请求"""
    name: str = Field(..., description="服务器名称")
    command: str = Field(..., description="启动命令")
    args: list[str] = Field(default=[], description="命令参数")
    env: Optional[dict] = Field(default=None, description="环境变量")
    enabled: bool = Field(default=True, description="是否启用")


class MCPServerUpdate(BaseModel):
    """更新 MCP 服务器请求"""
    command: Optional[str] = Field(default=None, description="启动命令")
    args: Optional[list[str]] = Field(default=None, description="命令参数")
    env: Optional[dict] = Field(default=None, description="环境变量")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


@router.get("")
async def list_mcp_servers(
    enabled_only: bool = Query(default=False, description="仅显示已启用的服务器"),
    _: str = Depends(verify_api_key)
):
    """
    获取 MCP 服务器列表
    """
    try:
        cli = get_hermes_cli()

        cmd = ["mcp", "--format", "json"]
        if enabled_only:
            cmd.append("--enabled")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to list MCP servers: {result.stderr}")

        import json
        try:
            servers = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            servers = []

        return create_response({
            "servers": servers,
            "count": len(servers)
        })

    except HermesCLIError as e:
        logger.error(f"Error listing MCP servers: {e}")
        return create_error_response(1005, str(e))


@router.post("")
async def create_mcp_server(
    server: MCPServerCreate,
    _: str = Depends(verify_api_key)
):
    """
    创建 MCP 服务器配置
    """
    try:
        cli = get_hermes_cli()

        cmd = ["mcp", "add", server.name, "--command", server.command]

        if server.args:
            for arg in server.args:
                cmd.extend(["--arg", arg])

        if server.env:
            for key, value in server.env.items():
                cmd.extend(["--env", f"{key}={value}"])

        if not server.enabled:
            cmd.append("--disabled")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to create MCP server: {result.stderr}")

        return create_response({
            "name": server.name,
            "command": server.command,
            "enabled": server.enabled,
            "created": True
        })

    except HermesCLIError as e:
        logger.error(f"Error creating MCP server: {e}")
        return create_error_response(1005, str(e))


@router.get("/{server_name}")
async def get_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取 MCP 服务器详情
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "show", server_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"MCP server not found: {server_name}")

        import json
        try:
            server = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            server = {"name": server_name, "raw": result.stdout}

        return create_response(server)

    except HermesCLIError as e:
        logger.error(f"Error getting MCP server: {e}")
        return create_error_response(1005, str(e))


@router.put("/{server_name}")
async def update_mcp_server(
    server_name: str,
    update: MCPServerUpdate,
    _: str = Depends(verify_api_key)
):
    """
    更新 MCP 服务器配置
    """
    try:
        cli = get_hermes_cli()

        cmd = ["mcp", "update", server_name]

        if update.command:
            cmd.extend(["--command", update.command])

        if update.args is not None:
            for arg in update.args:
                cmd.extend(["--arg", arg])

        if update.env is not None:
            for key, value in update.env.items():
                cmd.extend(["--env", f"{key}={value}"])

        if update.enabled is not None:
            cmd.append("--enable" if update.enabled else "--disable")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to update MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "updated": True
        })

    except HermesCLIError as e:
        logger.error(f"Error updating MCP server: {e}")
        return create_error_response(1005, str(e))


@router.delete("/{server_name}")
async def delete_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    删除 MCP 服务器配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "delete", server_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to delete MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "deleted": True
        })

    except HermesCLIError as e:
        logger.error(f"Error deleting MCP server: {e}")
        return create_error_response(1005, str(e))


@router.post("/{server_name}/enable")
async def enable_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    启用 MCP 服务器
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "enable", server_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to enable MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "enabled": True
        })

    except HermesCLIError as e:
        logger.error(f"Error enabling MCP server: {e}")
        return create_error_response(1005, str(e))


@router.post("/{server_name}/disable")
async def disable_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    禁用 MCP 服务器
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "disable", server_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to disable MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "enabled": False
        })

    except HermesCLIError as e:
        logger.error(f"Error disabling MCP server: {e}")
        return create_error_response(1005, str(e))


@router.post("/{server_name}/start")
async def start_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    启动 MCP 服务器
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "start", server_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to start MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "started": True
        })

    except HermesCLIError as e:
        logger.error(f"Error starting MCP server: {e}")
        return create_error_response(1005, str(e))


@router.post("/{server_name}/stop")
async def stop_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    停止 MCP 服务器
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "stop", server_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to stop MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "stopped": True
        })

    except HermesCLIError as e:
        logger.error(f"Error stopping MCP server: {e}")
        return create_error_response(1005, str(e))


@router.post("/{server_name}/restart")
async def restart_mcp_server(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    重启 MCP 服务器
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "restart", server_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to restart MCP server: {result.stderr}")

        return create_response({
            "name": server_name,
            "restarted": True
        })

    except HermesCLIError as e:
        logger.error(f"Error restarting MCP server: {e}")
        return create_error_response(1005, str(e))


@router.get("/{server_name}/status")
async def get_mcp_server_status(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取 MCP 服务器运行状态
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "status", server_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get MCP server status: {result.stderr}")

        import json
        try:
            status = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            status = {"raw": result.stdout}

        return create_response(status)

    except HermesCLIError as e:
        logger.error(f"Error getting MCP server status: {e}")
        return create_error_response(1005, str(e))


@router.get("/{server_name}/tools")
async def get_mcp_server_tools(
    server_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取 MCP 服务器提供的工具列表
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "tools", server_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get MCP tools: {result.stderr}")

        import json
        try:
            tools = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            tools = []

        return create_response({
            "server": server_name,
            "tools": tools,
            "count": len(tools)
        })

    except HermesCLIError as e:
        logger.error(f"Error getting MCP tools: {e}")
        return create_error_response(1005, str(e))


@router.post("/reload")
async def reload_mcp(
    _: str = Depends(verify_api_key)
):
    """
    重新加载 MCP 配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["mcp", "reload"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to reload MCP: {result.stderr}")

        return create_response({
            "reloaded": True
        })

    except HermesCLIError as e:
        logger.error(f"Error reloading MCP: {e}")
        return create_error_response(1005, str(e))
