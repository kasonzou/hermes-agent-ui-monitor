"""
配置管理 API 端点
"""
from typing import Optional
from fastapi import APIRouter, Depends
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

router = APIRouter()


@router.get("")
async def get_config(_: str = Depends(verify_api_key)):
    """获取完整配置"""
    try:
        cli = get_hermes_cli()
        config = await cli.get_config()
        return create_response(data=config)
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.get("/{key}")
async def get_config_item(key: str, _: str = Depends(verify_api_key)):
    """获取特定配置项"""
    try:
        cli = get_hermes_cli()
        config = await cli.get_config()

        # 支持嵌套键，如 "terminal.backend"
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break

        return create_response(data={"key": key, "value": value})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("")
async def set_config(request: dict, _: str = Depends(verify_api_key)):
    """设置配置项"""
    try:
        key = request.get("key")
        value = request.get("value")

        if not key or value is None:
            return create_response(code=1002, reason="Key and value are required", data=None)

        cli = get_hermes_cli()

        # 获取旧值
        config = await cli.get_config()
        keys = key.split(".")
        old_value = config
        for k in keys:
            if isinstance(old_value, dict):
                old_value = old_value.get(k)
            else:
                old_value = None
                break

        result = await cli.set_config(key, str(value))

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={
            "key": key,
            "value": value,
            "previous_value": old_value
        })
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/batch")
async def set_config_batch(request: dict, _: str = Depends(verify_api_key)):
    """批量设置配置"""
    try:
        config = request.get("config", {})

        if not config:
            return create_response(code=1002, reason="Config is required", data=None)

        cli = get_hermes_cli()
        results = []

        for key, value in config.items():
            result = await cli.set_config(key, str(value))
            results.append({
                "key": key,
                "value": value,
                "success": result.returncode == 0,
                "error": result.stderr if result.returncode != 0 else None
            })

        return create_response(data={"results": results})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)
