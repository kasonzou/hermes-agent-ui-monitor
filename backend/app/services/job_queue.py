"""
任务队列服务
管理异步任务执行，如长时间运行的 CLI 命令
"""
import asyncio
import logging
import time
import uuid
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

from app.core.hermes_cli import get_hermes_cli, HermesCLIError
from app.api.ws.handlers import push_session_event

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """任务定义"""
    id: str
    name: str
    command: list[str]
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "command": " ".join(self.command),
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "metadata": self.metadata,
            "duration_ms": self._get_duration()
        }

    def _get_duration(self) -> Optional[int]:
        """获取执行时长（毫秒）"""
        if self.started_at:
            end = self.completed_at or time.time()
            return int((end - self.started_at) * 1000)
        return None


class JobQueue:
    """任务队列 - 管理异步任务"""

    def __init__(self):
        self.cli = get_hermes_cli()

        # 任务存储
        self._jobs: Dict[str, Job] = {}
        self._job_order: list[str] = []  # 按创建顺序排列的任务 ID

        # 队列和处理
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._max_concurrent = 5  # 最大并发任务数

        # 回调
        self._callbacks: Dict[str, list[Callable[[Job], None]]] = {}

        # 状态
        self._started = False
        self._worker_task: Optional[asyncio.Task] = None

        # 历史记录限制
        self._max_history = 1000

    async def start(self):
        """启动任务队列"""
        if self._started:
            return

        self._started = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Job queue started")

    async def stop(self):
        """停止任务队列"""
        if not self._started:
            return

        self._started = False
        logger.info("Stopping job queue...")

        # 取消所有正在运行的任务
        for task in self._running_tasks.values():
            task.cancel()

        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        # 停止工作循环
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("Job queue stopped")

    def submit(
        self,
        name: str,
        command: list[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Job:
        """提交新任务"""
        job_id = f"job_{uuid.uuid4().hex[:12]}_{int(time.time())}"

        job = Job(
            id=job_id,
            name=name,
            command=command,
            metadata=metadata or {}
        )

        self._jobs[job_id] = job
        self._job_order.append(job_id)

        # 限制历史记录
        if len(self._job_order) > self._max_history:
            old_id = self._job_order.pop(0)
            if old_id in self._jobs:
                del self._jobs[old_id]

        # 加入队列
        asyncio.create_task(self._queue.put(job_id))

        logger.info(f"Job submitted: {job_id} - {name}")
        return job

    async def _worker_loop(self):
        """工作循环 - 处理队列中的任务"""
        while self._started:
            try:
                # 等待队列中的任务
                job_id = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )

                # 检查并发限制
                while len(self._running_tasks) >= self._max_concurrent:
                    await asyncio.sleep(0.1)

                # 执行任务
                task = asyncio.create_task(self._execute_job(job_id))
                self._running_tasks[job_id] = task

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker loop error: {e}")

    async def _execute_job(self, job_id: str):
        """执行单个任务"""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING
        job.started_at = time.time()

        logger.info(f"Job started: {job_id}")

        try:
            # 执行命令
            result = await self.cli.run(job.command, timeout=300)  # 5 分钟超时

            job.completed_at = time.time()

            if result.returncode == 0:
                job.status = JobStatus.COMPLETED
                job.result = {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
                logger.info(f"Job completed: {job_id}")
            else:
                job.status = JobStatus.FAILED
                job.error = result.stderr or f"Command failed with code {result.returncode}"
                logger.warning(f"Job failed: {job_id} - {job.error}")

        except asyncio.TimeoutError:
            job.status = JobStatus.FAILED
            job.error = "Job timed out after 5 minutes"
            job.completed_at = time.time()
            logger.warning(f"Job timeout: {job_id}")

        except HermesCLIError as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = time.time()
            logger.error(f"Job error: {job_id} - {e}")

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = f"Unexpected error: {str(e)}"
            job.completed_at = time.time()
            logger.error(f"Job error: {job_id} - {e}")

        finally:
            # 清理
            if job_id in self._running_tasks:
                del self._running_tasks[job_id]

            # 触发回调
            await self._trigger_callbacks(job)

            # 推送事件（如果有 session_id）
            if job.metadata.get("session_id"):
                await push_session_event(
                    "job.completed" if job.status == JobStatus.COMPLETED else "job.failed",
                    job.metadata["session_id"],
                    {"job": job.to_dict()}
                )

    async def _trigger_callbacks(self, job: Job):
        """触发任务回调"""
        callbacks = self._callbacks.get(job.id, [])
        for callback in callbacks:
            try:
                callback(job)
            except Exception as e:
                logger.error(f"Job callback error: {e}")

    def cancel_job(self, job_id: str) -> bool:
        """取消任务"""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
            return False

        # 取消正在运行的任务
        if job_id in self._running_tasks:
            self._running_tasks[job_id].cancel()

        job.status = JobStatus.CANCELLED
        job.completed_at = time.time()
        logger.info(f"Job cancelled: {job_id}")

        return True

    def get_job(self, job_id: str) -> Optional[Job]:
        """获取任务信息"""
        return self._jobs.get(job_id)

    def get_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[Job]:
        """获取任务列表"""
        jobs = []

        # 按时间倒序遍历
        for job_id in reversed(self._job_order):
            job = self._jobs.get(job_id)
            if not job:
                continue

            if status and job.status != status:
                continue

            jobs.append(job)

        # 分页
        return jobs[offset:offset + limit]

    def on_job_complete(self, job_id: str, callback: Callable[[Job], None]):
        """注册任务完成回调"""
        if job_id not in self._callbacks:
            self._callbacks[job_id] = []
        self._callbacks[job_id].append(callback)

    def get_stats(self) -> dict:
        """获取队列统计"""
        status_counts = {}
        for job in self._jobs.values():
            status = job.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_jobs": len(self._jobs),
            "running_jobs": len(self._running_tasks),
            "queued_jobs": self._queue.qsize(),
            "status_counts": status_counts,
            "max_concurrent": self._max_concurrent
        }


# 全局任务队列实例
_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """获取任务队列单例"""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue
