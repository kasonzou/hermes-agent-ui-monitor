"""
系统状态 API 端点
"""
from fastapi import APIRouter, Depends
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

router = APIRouter()


@router.get("/status")
async def get_system_status(_: str = Depends(verify_api_key)):
    """获取系统整体状态"""
    try:
        cli = get_hermes_cli()
        status = await cli.get_status()
        return create_response(data=status)
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.get("/doctor")
async def run_doctor(_: str = Depends(verify_api_key)):
    """运行诊断检查"""
    try:
        cli = get_hermes_cli()
        result = await cli.run_doctor()
        return create_response(data=result)
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.get("/version")
async def get_version(_: str = Depends(verify_api_key)):
    """获取版本信息"""
    try:
        cli = get_hermes_cli()
        result = await cli.run(["version"])
        return create_response(data={
            "version": result.stdout.strip(),
            "raw": result.stdout
        })
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.get("/health")
async def health_check():
    """健康检查（无需认证）"""
    return create_response(data={"status": "healthy"})
