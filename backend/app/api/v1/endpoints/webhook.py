"""
Webhook 管理 API
管理 Hermes Agent 的 Webhook 配置
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from app.core.security import verify_api_key
from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.schemas.response import create_response, create_error_response

logger = logging.getLogger(__name__)
router = APIRouter()


class WebhookCreate(BaseModel):
    """创建 Webhook 请求"""
    name: str = Field(..., description="Webhook 名称")
    url: str = Field(..., description="Webhook URL")
    events: list[str] = Field(default=[], description="订阅的事件类型")
    secret: Optional[str] = Field(default=None, description="签名密钥")
    enabled: bool = Field(default=True, description="是否启用")


class WebhookUpdate(BaseModel):
    """更新 Webhook 请求"""
    url: Optional[str] = Field(default=None, description="Webhook URL")
    events: Optional[list[str]] = Field(default=None, description="订阅的事件类型")
    secret: Optional[str] = Field(default=None, description="签名密钥")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


@router.get("")
async def list_webhooks(
    enabled_only: bool = Query(default=False, description="仅显示已启用的 Webhook"),
    _: str = Depends(verify_api_key)
):
    """
    获取 Webhook 列表
    """
    try:
        cli = get_hermes_cli()

        cmd = ["webhook", "ls", "--format", "json"]
        if enabled_only:
            cmd.append("--enabled")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to list webhooks: {result.stderr}")

        import json
        try:
            webhooks = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            webhooks = []

        return create_response({
            "webhooks": webhooks,
            "count": len(webhooks)
        })

    except HermesCLIError as e:
        logger.error(f"Error listing webhooks: {e}")
        return create_error_response(1005, str(e))


@router.post("")
async def create_webhook(
    webhook: WebhookCreate,
    _: str = Depends(verify_api_key)
):
    """
    创建 Webhook
    """
    try:
        cli = get_hermes_cli()

        cmd = ["webhook", "add", webhook.name, "--url", webhook.url]

        if webhook.events:
            for event in webhook.events:
                cmd.extend(["--event", event])

        if webhook.secret:
            cmd.extend(["--secret", webhook.secret])

        if not webhook.enabled:
            cmd.append("--disabled")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to create webhook: {result.stderr}")

        return create_response({
            "name": webhook.name,
            "url": webhook.url,
            "events": webhook.events,
            "enabled": webhook.enabled,
            "created": True
        })

    except HermesCLIError as e:
        logger.error(f"Error creating webhook: {e}")
        return create_error_response(1005, str(e))


@router.get("/{webhook_name}")
async def get_webhook(
    webhook_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取 Webhook 详情
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "show", webhook_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Webhook not found: {webhook_name}")

        import json
        try:
            webhook = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            webhook = {"name": webhook_name, "raw": result.stdout}

        return create_response(webhook)

    except HermesCLIError as e:
        logger.error(f"Error getting webhook: {e}")
        return create_error_response(1005, str(e))


@router.put("/{webhook_name}")
async def update_webhook(
    webhook_name: str,
    update: WebhookUpdate,
    _: str = Depends(verify_api_key)
):
    """
    更新 Webhook
    """
    try:
        cli = get_hermes_cli()

        cmd = ["webhook", "update", webhook_name]

        if update.url:
            cmd.extend(["--url", update.url])

        if update.events is not None:
            for event in update.events:
                cmd.extend(["--event", event])

        if update.secret is not None:
            cmd.extend(["--secret", update.secret])

        if update.enabled is not None:
            cmd.append("--enable" if update.enabled else "--disable")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to update webhook: {result.stderr}")

        return create_response({
            "name": webhook_name,
            "updated": True
        })

    except HermesCLIError as e:
        logger.error(f"Error updating webhook: {e}")
        return create_error_response(1005, str(e))


@router.delete("/{webhook_name}")
async def delete_webhook(
    webhook_name: str,
    _: str = Depends(verify_api_key)
):
    """
    删除 Webhook
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "remove", webhook_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to delete webhook: {result.stderr}")

        return create_response({
            "name": webhook_name,
            "deleted": True
        })

    except HermesCLIError as e:
        logger.error(f"Error deleting webhook: {e}")
        return create_error_response(1005, str(e))


@router.post("/{webhook_name}/enable")
async def enable_webhook(
    webhook_name: str,
    _: str = Depends(verify_api_key)
):
    """
    启用 Webhook
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "enable", webhook_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to enable webhook: {result.stderr}")

        return create_response({
            "name": webhook_name,
            "enabled": True
        })

    except HermesCLIError as e:
        logger.error(f"Error enabling webhook: {e}")
        return create_error_response(1005, str(e))


@router.post("/{webhook_name}/disable")
async def disable_webhook(
    webhook_name: str,
    _: str = Depends(verify_api_key)
):
    """
    禁用 Webhook
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "disable", webhook_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to disable webhook: {result.stderr}")

        return create_response({
            "name": webhook_name,
            "enabled": False
        })

    except HermesCLIError as e:
        logger.error(f"Error disabling webhook: {e}")
        return create_error_response(1005, str(e))


@router.post("/{webhook_name}/test")
async def test_webhook(
    webhook_name: str,
    _: str = Depends(verify_api_key)
):
    """
    测试 Webhook
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "test", webhook_name])

        return create_response({
            "name": webhook_name,
            "success": result.returncode == 0,
            "output": result.stdout if result.stdout else None,
            "error": result.stderr if result.returncode != 0 else None
        })

    except HermesCLIError as e:
        logger.error(f"Error testing webhook: {e}")
        return create_error_response(1005, str(e))


@router.get("/{webhook_name}/logs")
async def get_webhook_logs(
    webhook_name: str,
    limit: int = Query(default=10, le=100),
    _: str = Depends(verify_api_key)
):
    """
    获取 Webhook 调用日志
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "logs", webhook_name, "--limit", str(limit), "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get webhook logs: {result.stderr}")

        import json
        try:
            logs = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            logs = []

        return create_response({
            "webhook": webhook_name,
            "logs": logs,
            "count": len(logs)
        })

    except HermesCLIError as e:
        logger.error(f"Error getting webhook logs: {e}")
        return create_error_response(1005, str(e))


@router.get("/{webhook_name}/delivery-stats")
async def get_webhook_delivery_stats(
    webhook_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取 Webhook 投递统计
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["webhook", "stats", webhook_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get webhook stats: {result.stderr}")

        import json
        try:
            stats = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            stats = {"raw": result.stdout}

        return create_response(stats)

    except HermesCLIError as e:
        logger.error(f"Error getting webhook stats: {e}")
        return create_error_response(1005, str(e))
