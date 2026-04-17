"""
网关管理 API 端点
"""
from fastapi import APIRouter, Depends
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

router = APIRouter()


@router.get("/status")
async def get_gateway_status(_: str = Depends(verify_api_key)):
    """获取网关状态"""
    try:
        cli = get_hermes_cli()
        status = await cli.get_gateway_status()
        return create_response(data=status)
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/start")
async def start_gateway(_: str = Depends(verify_api_key)):
    """启动网关"""
    try:
        cli = get_hermes_cli()
        result = await cli.start_gateway()

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"started": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/stop")
async def stop_gateway(_: str = Depends(verify_api_key)):
    """停止网关"""
    try:
        cli = get_hermes_cli()
        result = await cli.stop_gateway()

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"stopped": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/restart")
async def restart_gateway(_: str = Depends(verify_api_key)):
    """重启网关"""
    try:
        cli = get_hermes_cli()
        result = await cli.restart_gateway()

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"restarted": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)
