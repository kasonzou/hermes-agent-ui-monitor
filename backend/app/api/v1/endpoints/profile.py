"""
Profile 管理 API
管理 Hermes Agent 的配置文件
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.schemas.response import create_response, create_error_response

logger = logging.getLogger(__name__)
router = APIRouter()


class ProfileCreate(BaseModel):
    """创建 Profile 请求"""
    name: str = Field(..., description="Profile 名称")
    base_profile: Optional[str] = Field(default=None, description="基于哪个 Profile 创建")
    config: Optional[dict] = Field(default=None, description="初始配置")


class ProfileUpdate(BaseModel):
    """更新 Profile 请求"""
    config: Optional[dict] = Field(default=None, description="配置项")


@router.get("")
async def list_profiles(
    _: dict = Depends(get_current_user)
):
    """
    获取所有 Profile 列表
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "ls", "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to list profiles: {result.stderr}")

        import json
        try:
            profiles = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            profiles = []

        return create_response({
            "profiles": profiles,
            "count": len(profiles)
        })

    except HermesCLIError as e:
        logger.error(f"Error listing profiles: {e}")
        return create_error_response(1005, str(e))


@router.post("")
async def create_profile(
    profile: ProfileCreate,
    _: dict = Depends(get_current_user)
):
    """
    创建新的 Profile
    """
    try:
        cli = get_hermes_cli()

        cmd = ["profile", "create", profile.name]

        if profile.base_profile:
            cmd.extend(["--from", profile.base_profile])

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to create profile: {result.stderr}")

        # 如果有初始配置，设置配置
        if profile.config:
            for key, value in profile.config.items():
                import json
                value_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                await cli.run(["config", "set", "-p", profile.name, key, value_str])

        return create_response({
            "name": profile.name,
            "base_profile": profile.base_profile,
            "created": True
        })

    except HermesCLIError as e:
        logger.error(f"Error creating profile: {e}")
        return create_error_response(1005, str(e))


@router.get("/{profile_name}")
async def get_profile(
    profile_name: str,
    _: dict = Depends(get_current_user)
):
    """
    获取 Profile 详情
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "show", profile_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Profile not found: {profile_name}")

        import json
        try:
            profile = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            profile = {"name": profile_name, "raw": result.stdout}

        return create_response(profile)

    except HermesCLIError as e:
        logger.error(f"Error getting profile: {e}")
        return create_error_response(1005, str(e))


@router.delete("/{profile_name}")
async def delete_profile(
    profile_name: str,
    force: bool = Query(default=False, description="强制删除"),
    _: dict = Depends(get_current_user)
):
    """
    删除 Profile
    """
    try:
        cli = get_hermes_cli()

        cmd = ["profile", "delete", profile_name]
        if force:
            cmd.append("--force")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to delete profile: {result.stderr}")

        return create_response({
            "name": profile_name,
            "deleted": True
        })

    except HermesCLIError as e:
        logger.error(f"Error deleting profile: {e}")
        return create_error_response(1005, str(e))


@router.post("/{profile_name}/switch")
async def switch_profile(
    profile_name: str,
    _: dict = Depends(get_current_user)
):
    """
    切换到指定 Profile
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "switch", profile_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to switch profile: {result.stderr}")

        return create_response({
            "name": profile_name,
            "switched": True
        })

    except HermesCLIError as e:
        logger.error(f"Error switching profile: {e}")
        return create_error_response(1005, str(e))


@router.get("/{profile_name}/config")
async def get_profile_config(
    profile_name: str,
    _: dict = Depends(get_current_user)
):
    """
    获取 Profile 配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["config", "get", "-p", profile_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get profile config: {result.stderr}")

        import json
        try:
            config = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            config = {"raw": result.stdout}

        return create_response(config)

    except HermesCLIError as e:
        logger.error(f"Error getting profile config: {e}")
        return create_error_response(1005, str(e))


@router.put("/{profile_name}/config")
async def update_profile_config(
    profile_name: str,
    config: dict,
    _: dict = Depends(get_current_user)
):
    """
    更新 Profile 配置
    """
    try:
        cli = get_hermes_cli()

        updated = []
        failed = []

        for key, value in config.items():
            import json
            value_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            result = await cli.run(["config", "set", "-p", profile_name, key, value_str])

            if result.returncode == 0:
                updated.append(key)
            else:
                failed.append({"key": key, "error": result.stderr})

        return create_response({
            "profile": profile_name,
            "updated": updated,
            "failed": failed,
            "success": len(failed) == 0
        })

    except HermesCLIError as e:
        logger.error(f"Error updating profile config: {e}")
        return create_error_response(1005, str(e))


@router.get("/current")
async def get_current_profile(
    _: dict = Depends(get_current_user)
):
    """
    获取当前使用的 Profile
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "current", "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get current profile: {result.stderr}")

        import json
        try:
            profile = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            profile = {"name": result.stdout.strip()}

        return create_response(profile)

    except HermesCLIError as e:
        logger.error(f"Error getting current profile: {e}")
        return create_error_response(1005, str(e))


@router.post("/{profile_name}/duplicate")
async def duplicate_profile(
    profile_name: str,
    new_name: str,
    _: dict = Depends(get_current_user)
):
    """
    复制 Profile
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "duplicate", profile_name, new_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to duplicate profile: {result.stderr}")

        return create_response({
            "source": profile_name,
            "new_name": new_name,
            "duplicated": True
        })

    except HermesCLIError as e:
        logger.error(f"Error duplicating profile: {e}")
        return create_error_response(1005, str(e))


@router.get("/{profile_name}/export")
async def export_profile(
    profile_name: str,
    _: dict = Depends(get_current_user)
):
    """
    导出 Profile 配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "export", profile_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to export profile: {result.stderr}")

        import json
        try:
            config = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            config = {"raw": result.stdout}

        return create_response({
            "profile": profile_name,
            "config": config
        })

    except HermesCLIError as e:
        logger.error(f"Error exporting profile: {e}")
        return create_error_response(1005, str(e))


@router.post("/import")
async def import_profile(
    name: str,
    config: dict,
    _: dict = Depends(get_current_user)
):
    """
    导入 Profile 配置
    """
    try:
        cli = get_hermes_cli()

        import json
        config_json = json.dumps(config)

        result = await cli.run(["profile", "import", name, config_json])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to import profile: {result.stderr}")

        return create_response({
            "name": name,
            "imported": True
        })

    except HermesCLIError as e:
        logger.error(f"Error importing profile: {e}")
        return create_error_response(1005, str(e))


@router.get("/{profile_name}/validate")
async def validate_profile(
    profile_name: str,
    _: dict = Depends(get_current_user)
):
    """
    验证 Profile 配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["profile", "validate", profile_name, "--format", "json"])

        import json
        try:
            validation = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            validation = {"valid": result.returncode == 0, "raw": result.stdout}

        return create_response({
            "profile": profile_name,
            "valid": result.returncode == 0,
            "details": validation,
            "errors": result.stderr if result.returncode != 0 else None
        })

    except HermesCLIError as e:
        logger.error(f"Error validating profile: {e}")
        return create_error_response(1005, str(e))
