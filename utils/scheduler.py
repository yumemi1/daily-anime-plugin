"""
定时任务管理器
提供定时推送和任务调度功能
"""

import asyncio
import time
from typing import List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

try:
    from src.common.logger import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger("scheduler")


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """定时任务"""

    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = None
    next_run: Optional[datetime] = None
    interval: Optional[int] = None  # 间隔秒数
    enabled: bool = True
    status: TaskStatus = TaskStatus.PENDING
    last_run: Optional[datetime] = None
    run_count: int = 0
    max_retries: int = 3
    retry_count: int = 0

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


class DailyAnimeScheduler:
    """每日动漫定时任务调度器"""

    def __init__(self):
        self.tasks: List[ScheduledTask] = []
        self.running = False
        self.scheduler_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """启动调度器"""
        if self.running:
            return

        self.running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self):
        """停止调度器"""
        if not self.running:
            return

        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass

    async def add_task(self, task: ScheduledTask):
        """添加定时任务"""
        async with self._lock:
            self.tasks.append(task)

    async def remove_task(self, task_name: str) -> bool:
        """移除定时任务"""
        async with self._lock:
            for i, task in enumerate(self.tasks):
                if task.name == task_name:
                    task.status = TaskStatus.CANCELLED
                    del self.tasks[i]
                    return True
        return False

    async def get_task(self, task_name: str) -> Optional[ScheduledTask]:
        """获取定时任务"""
        async with self._lock:
            for task in self.tasks:
                if task.name == task_name:
                    return task
        return None

    async def enable_task(self, task_name: str) -> bool:
        """启用任务"""
        task = await self.get_task(task_name)
        if task:
            task.enabled = True
            return True
        return False

    async def disable_task(self, task_name: str) -> bool:
        """禁用任务"""
        task = await self.get_task(task_name)
        if task:
            task.enabled = False
            return True
        return False

    async def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            try:
                current_time = datetime.now()

                async with self._lock:
                    for task in self.tasks:
                        if not task.enabled:
                            continue

                        # 检查是否需要运行
                        if task.next_run and current_time >= task.next_run:
                            await self._run_task(task)

                # 每分钟检查一次
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器循环出错: {str(e)}")
                await asyncio.sleep(60)

    async def _run_task(self, task: ScheduledTask):
        """运行任务"""
        if task.status == TaskStatus.RUNNING:
            return

        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now()

        try:
            # 异步执行任务
            if asyncio.iscoroutinefunction(task.func):
                await task.func(*task.args, **task.kwargs)
            else:
                task.func(*task.args, **task.kwargs)

            task.status = TaskStatus.COMPLETED
            task.run_count += 1
            task.retry_count = 0

            # 计算下次运行时间
            if task.interval:
                task.next_run = datetime.now() + timedelta(seconds=task.interval)
            else:
                task.next_run = None

        except Exception as e:
            logger.error(f"任务 {task.name} 执行失败: {str(e)}")
            task.status = TaskStatus.FAILED
            task.retry_count += 1

            # 重试逻辑
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.PENDING
                task.next_run = datetime.now() + timedelta(minutes=5)  # 5分钟后重试
            else:
                task.enabled = False

    async def get_task_stats(self) -> dict:
        """获取任务统计信息"""
        async with self._lock:
            stats = {
                "total_tasks": len(self.tasks),
                "enabled_tasks": sum(1 for task in self.tasks if task.enabled),
                "disabled_tasks": sum(1 for task in self.tasks if not task.enabled),
                "running_tasks": sum(1 for task in self.tasks if task.status == TaskStatus.RUNNING),
                "completed_tasks": sum(1 for task in self.tasks if task.status == TaskStatus.COMPLETED),
                "failed_tasks": sum(1 for task in self.tasks if task.status == TaskStatus.FAILED),
                "scheduler_running": self.running,
                "tasks": [],
            }

            for task in self.tasks:
                stats["tasks"].append(
                    {
                        "name": task.name,
                        "status": task.status.value,
                        "enabled": task.enabled,
                        "last_run": task.last_run.isoformat() if task.last_run else None,
                        "next_run": task.next_run.isoformat() if task.next_run else None,
                        "run_count": task.run_count,
                        "retry_count": task.retry_count,
                    }
                )

        return stats


def create_daily_push_task(push_func, push_time: str, chat_ids: List[str]) -> ScheduledTask:
    """创建每日推送任务"""

    async def daily_push_wrapper():
        """每日推送包装函数"""
        try:
            await push_func(chat_ids)
        except Exception as e:
            logger.error(f"每日推送执行失败: {str(e)}")

    # 计算今天的推送时间
    now = datetime.now()
    hour, minute = map(int, push_time.split(":"))
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 如果今天的推送时间已过，则设置为明天
    if next_run <= now:
        next_run += timedelta(days=1)

    return ScheduledTask(
        name="daily_anime_push",
        func=daily_push_wrapper,
        next_run=next_run,
        interval=86400,  # 24小时间隔
        max_retries=3,
    )


# 全局调度器实例
_global_scheduler: Optional[DailyAnimeScheduler] = None


def get_global_scheduler() -> DailyAnimeScheduler:
    """获取全局调度器实例"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = DailyAnimeScheduler()
    return _global_scheduler


async def start_scheduler():
    """启动全局调度器"""
    scheduler = get_global_scheduler()
    await scheduler.start()


async def stop_scheduler():
    """停止全局调度器"""
    scheduler = get_global_scheduler()
    await scheduler.stop()


async def add_daily_push_task(push_func, push_time: str, chat_ids: List[str]):
    """添加每日推送任务"""
    scheduler = get_global_scheduler()

    # 先移除旧的任务
    await scheduler.remove_task("daily_anime_push")

    # 添加新任务
    task = create_daily_push_task(push_func, push_time, chat_ids)
    await scheduler.add_task(task)

    return task


async def update_daily_push_task(push_time: str, chat_ids: List[str]):
    """更新每日推送任务"""
    scheduler = get_global_scheduler()
    task = await scheduler.get_task("daily_anime_push")

    if task:
        # 更新现有任务
        now = datetime.now()
        hour, minute = map(int, push_time.split(":"))
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if next_run <= now:
            next_run += timedelta(days=1)

        task.next_run = next_run

        # 更新推送函数的chat_ids参数
        if len(task.kwargs) > 0:
            task.kwargs["chat_ids"] = chat_ids
        else:
            task.kwargs = {"chat_ids": chat_ids}

    return task


def create_cron_task(task_func, cron_time: str, task_name: str, interval_seconds: int = 86400) -> ScheduledTask:
    """创建cron风格定时任务"""

    async def task_wrapper():
        """任务包装函数"""
        try:
            if asyncio.iscoroutinefunction(task_func):
                await task_func()
            else:
                task_func()
        except Exception as e:
            logger.error(f"定时任务 {task_name} 执行失败: {str(e)}")

    # 计算下次运行时间
    now = datetime.now()
    hour, minute = map(int, cron_time.split(":"))
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 如果今天的执行时间已过，则设置为明天
    if next_run <= now:
        next_run += timedelta(days=1)

    return ScheduledTask(
        name=task_name,
        func=task_wrapper,
        next_run=next_run,
        interval=interval_seconds,  # 默认24小时间隔
        max_retries=3,
    )


async def add_cron_task(task_func, cron_time: str, task_name: str, interval_seconds: int = 86400):
    """添加cron风格定时任务"""
    scheduler = get_global_scheduler()

    # 先移除旧的任务
    await scheduler.remove_task(task_name)

    # 添加新任务
    task = create_cron_task(task_func, cron_time, task_name, interval_seconds)
    await scheduler.add_task(task)

    return task
