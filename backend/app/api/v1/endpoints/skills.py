"""
技能管理 API 端点
"""
from fastapi import APIRouter, Depends
from app.core.security import verify_api_key, create_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

router = APIRouter()


@router.get("")
async def list_skills(_: str = Depends(verify_api_key)):
    """获取已安装技能列表"""
    try:
        cli = get_hermes_cli()
        skills = await cli.list_skills()
        return create_response(data={"skills": skills})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.get("/search")
async def search_skills(query: str, _: str = Depends(verify_api_key)):
    """搜索技能"""
    try:
        cli = get_hermes_cli()
        skills = await cli.search_skills(query)
        return create_response(data={"skills": skills})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.post("/install")
async def install_skill(request: dict, _: str = Depends(verify_api_key)):
    """安装技能"""
    try:
        name = request.get("name")
        if not name:
            return create_response(code=1002, reason="Skill name is required", data=None)

        cli = get_hermes_cli()
        result = await cli.install_skill(name)

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"name": name, "installed": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)


@router.delete("/{name}")
async def uninstall_skill(name: str, _: str = Depends(verify_api_key)):
    """卸载技能"""
    try:
        cli = get_hermes_cli()
        result = await cli.uninstall_skill(name)

        if result.returncode != 0:
            return create_response(code=1005, reason=result.stderr, data=None)

        return create_response(data={"name": name, "uninstalled": True})
    except HermesCLIError as e:
        return create_response(code=1005, reason=str(e), data=None)
