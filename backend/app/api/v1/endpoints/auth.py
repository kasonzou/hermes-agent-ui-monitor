"""
认证管理 API 端点
"""
from fastapi import APIRouter, Depends
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

router = APIRouter()


@router.get("/providers")
async def list_auth_providers(_: str = Depends(verify_api_key)):
    """获取认证提供商列表"""
    try:
        cli = get_hermes_cli()
        providers = await cli.list_auth_providers()
        return create_response(data={"providers": providers})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/login")
async def login(request: dict, _: str = Depends(verify_api_key)):
    """添加认证"""
    try:
        provider = request.get("provider")
        api_key = request.get("api_key")

        if not provider or not api_key:
            return create_response(code=1002, reason="Provider and api_key are required", data=None)

        cli = get_hermes_cli()
        result = await cli.run(["login", provider], timeout=30)

        # 注意：实际登录可能需要交互，这里简化处理
        return create_response(data={"provider": provider, "login_initiated": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/logout")
async def logout(request: dict, _: str = Depends(verify_api_key)):
    """清除认证"""
    try:
        provider = request.get("provider")

        if not provider:
            return create_response(code=1002, reason="Provider is required", data=None)

        cli = get_hermes_cli()
        result = await cli.run(["logout", provider])

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"provider": provider, "logged_out": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)
