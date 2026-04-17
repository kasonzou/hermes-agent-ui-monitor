"""
工具管理 API
管理 Hermes Agent 的工具配置和注册
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import verify_api_key, create_response, create_error_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_tools(
    enabled_only: bool = Query(default=False, description="仅显示已启用的工具"),
    _: str = Depends(verify_api_key)
):
    """
    获取工具列表

    返回所有已配置的工具及其状态
    """
    try:
        cli = get_hermes_cli()

        # 获取工具列表
        cmd = ["tool", "ls", "--format", "json"]
        if enabled_only:
            cmd.append("--enabled")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to list tools: {result.stderr}")

        import json
        try:
            tools = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            tools = []

        return create_response({
            "tools": tools,
            "count": len(tools)
        })

    except HermesCLIError as e:
        logger.error(f"Error listing tools: {e}")
        return create_error_response(1005, str(e))


@router.get("/{tool_name}")
async def get_tool(
    tool_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取工具详情
    """
    try:
        cli = get_hermes_cli()

        # 获取工具详情
        result = await cli.run(["tool", "show", tool_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Tool not found: {tool_name}")

        import json
        try:
            tool = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            tool = {"name": tool_name, "raw": result.stdout}

        return create_response(tool)

    except HermesCLIError as e:
        logger.error(f"Error getting tool: {e}")
        return create_error_response(1005, str(e))


@router.post("/{tool_name}/enable")
async def enable_tool(
    tool_name: str,
    _: str = Depends(verify_api_key)
):
    """
    启用工具
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["tool", "enable", tool_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to enable tool: {result.stderr}")

        return create_response({
            "tool": tool_name,
            "enabled": True
        })

    except HermesCLIError as e:
        logger.error(f"Error enabling tool: {e}")
        return create_error_response(1005, str(e))


@router.post("/{tool_name}/disable")
async def disable_tool(
    tool_name: str,
    _: str = Depends(verify_api_key)
):
    """
    禁用工具
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["tool", "disable", tool_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to disable tool: {result.stderr}")

        return create_response({
            "tool": tool_name,
            "enabled": False
        })

    except HermesCLIError as e:
        logger.error(f"Error disabling tool: {e}")
        return create_error_response(1005, str(e))


@router.get("/{tool_name}/config")
async def get_tool_config(
    tool_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取工具配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["tool", "config", "get", tool_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get tool config: {result.stderr}")

        import json
        try:
            config = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            config = {"raw": result.stdout}

        return create_response(config)

    except HermesCLIError as e:
        logger.error(f"Error getting tool config: {e}")
        return create_error_response(1005, str(e))


@router.put("/{tool_name}/config")
async def update_tool_config(
    tool_name: str,
    config: dict,
    _: str = Depends(verify_api_key)
):
    """
    更新工具配置
    """
    try:
        cli = get_hermes_cli()

        # 将配置转换为 JSON
        import json
        config_json = json.dumps(config)

        result = await cli.run(["tool", "config", "set", tool_name, config_json])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to update tool config: {result.stderr}")

        return create_response({
            "tool": tool_name,
            "updated": True
        })

    except HermesCLIError as e:
        logger.error(f"Error updating tool config: {e}")
        return create_error_response(1005, str(e))


@router.post("/reload")
async def reload_tools(
    _: str = Depends(verify_api_key)
):
    """
    重新加载工具配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["tool", "reload"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to reload tools: {result.stderr}")

        return create_response({
            "reloaded": True
        })

    except HermesCLIError as e:
        logger.error(f"Error reloading tools: {e}")
        return create_error_response(1005, str(e))


@router.get("/{tool_name}/schema")
async def get_tool_schema(
    tool_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取工具的 JSON Schema
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["tool", "schema", tool_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get tool schema: {result.stderr}")

        import json
        try:
            schema = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            schema = {"raw": result.stdout}

        return create_response(schema)

    except HermesCLIError as e:
        logger.error(f"Error getting tool schema: {e}")
        return create_error_response(1005, str(e))


@router.post("/{tool_name}/test")
async def test_tool(
    tool_name: str,
    params: dict,
    _: str = Depends(verify_api_key)
):
    """
    测试工具执行
    """
    try:
        cli = get_hermes_cli()

        import json
        params_json = json.dumps(params)

        result = await cli.run(["tool", "test", tool_name, params_json])

        import json
        try:
            test_result = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            test_result = {"output": result.stdout}

        return create_response({
            "tool": tool_name,
            "success": result.returncode == 0,
            "result": test_result,
            "error": result.stderr if result.returncode != 0 else None
        })

    except HermesCLIError as e:
        logger.error(f"Error testing tool: {e}")
        return create_error_response(1005, str(e))
