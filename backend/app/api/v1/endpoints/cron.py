"""
定时任务管理 API
管理 Hermes Agent 的定时任务配置
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import verify_api_key, create_response, create_error_response
from app.core.hermes_cli import get_hermes_cli, HermesCLIError

logger = logging.getLogger(__name__)
router = APIRouter()


class CronJobCreate(BaseModel):
    """创建定时任务请求"""
    name: str = Field(..., description="任务名称")
    schedule: str = Field(..., description="Cron 表达式")
    command: list[str] = Field(..., description="要执行的命令")
    enabled: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(default=None, description="任务描述")


class CronJobUpdate(BaseModel):
    """更新定时任务请求"""
    schedule: Optional[str] = Field(default=None, description="Cron 表达式")
    command: Optional[list[str]] = Field(default=None, description="要执行的命令")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    description: Optional[str] = Field(default=None, description="任务描述")


@router.get("")
async def list_cron_jobs(
    enabled_only: bool = Query(default=False, description="仅显示已启用的任务"),
    _: str = Depends(verify_api_key)
):
    """
    获取定时任务列表
    """
    try:
        cli = get_hermes_cli()

        cmd = ["cron", "--format", "json"]
        if enabled_only:
            cmd.append("--enabled")

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to list cron jobs: {result.stderr}")

        import json
        try:
            jobs = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            jobs = []

        return create_response({
            "jobs": jobs,
            "count": len(jobs)
        })

    except HermesCLIError as e:
        logger.error(f"Error listing cron jobs: {e}")
        return create_error_response(1005, str(e))


@router.post("")
async def create_cron_job(
    job: CronJobCreate,
    _: str = Depends(verify_api_key)
):
    """
    创建定时任务
    """
    try:
        cli = get_hermes_cli()

        # 构建命令
        cmd = ["cron", "add", job.name, "--schedule", job.schedule]

        if job.description:
            cmd.extend(["--description", job.description])

        if not job.enabled:
            cmd.append("--disabled")

        # 添加要执行的命令
        cmd.append("--")
        cmd.extend(job.command)

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to create cron job: {result.stderr}")

        return create_response({
            "name": job.name,
            "schedule": job.schedule,
            "enabled": job.enabled,
            "created": True
        })

    except HermesCLIError as e:
        logger.error(f"Error creating cron job: {e}")
        return create_error_response(1005, str(e))


@router.get("/{job_name}")
async def get_cron_job(
    job_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取定时任务详情
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "show", job_name, "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Cron job not found: {job_name}")

        import json
        try:
            job = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            job = {"name": job_name, "raw": result.stdout}

        return create_response(job)

    except HermesCLIError as e:
        logger.error(f"Error getting cron job: {e}")
        return create_error_response(1005, str(e))


@router.put("/{job_name}")
async def update_cron_job(
    job_name: str,
    update: CronJobUpdate,
    _: str = Depends(verify_api_key)
):
    """
    更新定时任务
    """
    try:
        cli = get_hermes_cli()

        # 构建更新命令
        cmd = ["cron", "update", job_name]

        if update.schedule:
            cmd.extend(["--schedule", update.schedule])

        if update.description is not None:
            cmd.extend(["--description", update.description or ""])

        if update.enabled is not None:
            cmd.append("--enable" if update.enabled else "--disable")

        if update.command:
            cmd.append("--")
            cmd.extend(update.command)

        result = await cli.run(cmd)

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to update cron job: {result.stderr}")

        return create_response({
            "name": job_name,
            "updated": True
        })

    except HermesCLIError as e:
        logger.error(f"Error updating cron job: {e}")
        return create_error_response(1005, str(e))


@router.delete("/{job_name}")
async def delete_cron_job(
    job_name: str,
    _: str = Depends(verify_api_key)
):
    """
    删除定时任务
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "delete", job_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to delete cron job: {result.stderr}")

        return create_response({
            "name": job_name,
            "deleted": True
        })

    except HermesCLIError as e:
        logger.error(f"Error deleting cron job: {e}")
        return create_error_response(1005, str(e))


@router.post("/{job_name}/enable")
async def enable_cron_job(
    job_name: str,
    _: str = Depends(verify_api_key)
):
    """
    启用定时任务
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "enable", job_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to enable cron job: {result.stderr}")

        return create_response({
            "name": job_name,
            "enabled": True
        })

    except HermesCLIError as e:
        logger.error(f"Error enabling cron job: {e}")
        return create_error_response(1005, str(e))


@router.post("/{job_name}/disable")
async def disable_cron_job(
    job_name: str,
    _: str = Depends(verify_api_key)
):
    """
    禁用定时任务
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "disable", job_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to disable cron job: {result.stderr}")

        return create_response({
            "name": job_name,
            "enabled": False
        })

    except HermesCLIError as e:
        logger.error(f"Error disabling cron job: {e}")
        return create_error_response(1005, str(e))


@router.post("/{job_name}/run")
async def run_cron_job_now(
    job_name: str,
    _: str = Depends(verify_api_key)
):
    """
    立即执行定时任务
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "run", job_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to run cron job: {result.stderr}")

        return create_response({
            "name": job_name,
            "executed": True,
            "output": result.stdout if result.stdout else None
        })

    except HermesCLIError as e:
        logger.error(f"Error running cron job: {e}")
        return create_error_response(1005, str(e))


@router.get("/{job_name}/history")
async def get_cron_job_history(
    job_name: str,
    limit: int = Query(default=10, le=100),
    _: str = Depends(verify_api_key)
):
    """
    获取定时任务执行历史
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "history", job_name, "--limit", str(limit), "--format", "json"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get cron job history: {result.stderr}")

        import json
        try:
            history = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            history = []

        return create_response({
            "job": job_name,
            "history": history,
            "count": len(history)
        })

    except HermesCLIError as e:
        logger.error(f"Error getting cron job history: {e}")
        return create_error_response(1005, str(e))


@router.get("/{job_name}/next-run")
async def get_next_run_time(
    job_name: str,
    _: str = Depends(verify_api_key)
):
    """
    获取定时任务下次执行时间
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "next-run", job_name])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to get next run time: {result.stderr}")

        return create_response({
            "job": job_name,
            "next_run": result.stdout.strip() if result.stdout else None
        })

    except HermesCLIError as e:
        logger.error(f"Error getting next run time: {e}")
        return create_error_response(1005, str(e))


@router.post("/reload")
async def reload_cron(
    _: str = Depends(verify_api_key)
):
    """
    重新加载定时任务配置
    """
    try:
        cli = get_hermes_cli()

        result = await cli.run(["cron", "reload"])

        if result.returncode != 0:
            return create_error_response(1005, f"Failed to reload cron: {result.stderr}")

        return create_response({
            "reloaded": True
        })

    except HermesCLIError as e:
        logger.error(f"Error reloading cron: {e}")
        return create_error_response(1005, str(e))
