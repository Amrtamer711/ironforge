"""
Task queue manager for mockup generation.
Limits concurrent mockup generation tasks to prevent memory exhaustion.
"""

import asyncio
import logging
from typing import Callable, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import uuid
import psutil
import os

logger = logging.getLogger(__name__)


def get_ram_usage_mb() -> dict:
    """Get current RAM usage in MB."""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return {
        "rss_mb": round(mem_info.rss / 1024 / 1024, 2),
        "vms_mb": round(mem_info.vms / 1024 / 1024, 2),
    }


@dataclass
class QueuedTask:
    """Represents a task in the queue."""
    task_id: str
    func: Callable
    args: tuple
    kwargs: dict
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[Exception] = None


class MockupTaskQueue:
    """
    Queue manager for mockup generation tasks.
    Limits concurrent executions to prevent memory exhaustion.
    """

    def __init__(self, max_concurrent: int = 3):
        """
        Initialize the task queue.

        Args:
            max_concurrent: Maximum number of concurrent mockup generation tasks (default: 3)
        """
        self.max_concurrent = max_concurrent
        self.current_tasks = 0
        self.queue: list[QueuedTask] = []
        self.active_tasks: dict[str, QueuedTask] = {}
        self.lock = asyncio.Lock()
        logger.info(f"[QUEUE] Initialized mockup task queue (max concurrent: {max_concurrent})")

    async def submit(self, func: Callable, *args, **kwargs) -> Any:
        """
        Submit a task to the queue. If slots available, execute immediately.
        Otherwise, queue and wait for slot.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func execution
        """
        task_id = str(uuid.uuid4())[:8]
        task = QueuedTask(
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            created_at=datetime.now()
        )

        async with self.lock:
            self.queue.append(task)
            queue_position = len([t for t in self.queue if t.started_at is None])
            logger.info(
                f"[QUEUE] Task {task_id} submitted "
                f"(active: {self.current_tasks}/{self.max_concurrent}, "
                f"queued: {queue_position})"
            )

        # Process queue (start tasks if slots available)
        await self._process_queue()

        # Wait for this task to start
        while task.started_at is None:
            await asyncio.sleep(0.1)

        # Task is now running, wait for completion
        while task.completed_at is None:
            await asyncio.sleep(0.1)

        # Task completed, check for errors
        if task.error:
            logger.error(f"[QUEUE] Task {task_id} failed: {task.error}")
            raise task.error

        logger.info(f"[QUEUE] Task {task_id} completed successfully")
        return task.result

    async def _process_queue(self):
        """Process queued tasks if slots are available."""
        async with self.lock:
            # Start as many tasks as we have slots for
            while self.current_tasks < self.max_concurrent:
                # Find next pending task
                pending_task = None
                for task in self.queue:
                    if task.started_at is None:
                        pending_task = task
                        break

                if not pending_task:
                    # No more pending tasks
                    break

                # Start the task
                pending_task.started_at = datetime.now()
                self.current_tasks += 1
                self.active_tasks[pending_task.task_id] = pending_task

                wait_time = (pending_task.started_at - pending_task.created_at).total_seconds()
                ram_start = get_ram_usage_mb()
                logger.info(
                    f"[QUEUE] Starting task {pending_task.task_id} "
                    f"(waited {wait_time:.1f}s, active: {self.current_tasks}/{self.max_concurrent}, "
                    f"RAM: {ram_start['rss_mb']}MB)"
                )

                # Run task in background
                asyncio.create_task(self._run_task(pending_task))

    async def _run_task(self, task: QueuedTask):
        """Run a task and handle completion."""
        ram_before = get_ram_usage_mb()
        logger.info(f"[QUEUE] Task {task.task_id} RAM before execution: {ram_before['rss_mb']}MB")

        try:
            # Execute the task
            result = await task.func(*task.args, **task.kwargs)
            task.result = result
            task.completed_at = datetime.now()

            execution_time = (task.completed_at - task.started_at).total_seconds()
            ram_after = get_ram_usage_mb()
            ram_delta = ram_after['rss_mb'] - ram_before['rss_mb']
            logger.info(
                f"[QUEUE] Task {task.task_id} finished (took {execution_time:.1f}s, "
                f"RAM: {ram_before['rss_mb']}MB → {ram_after['rss_mb']}MB, "
                f"delta: {ram_delta:+.2f}MB)"
            )

        except Exception as e:
            task.error = e
            task.completed_at = datetime.now()
            logger.error(f"[QUEUE] Task {task.task_id} failed: {e}")

        finally:
            # Force aggressive garbage collection before releasing slot
            # This ensures memory from numpy arrays is freed before next task starts
            import gc
            ram_before_gc = get_ram_usage_mb()
            gc.collect()  # Collect generation 0 (recent objects)
            gc.collect()  # Collect generation 1
            gc.collect()  # Collect generation 2 (full collection)

            # Small delay to let OS reclaim memory (numpy arrays use malloc directly)
            await asyncio.sleep(0.1)

            ram_after_gc = get_ram_usage_mb()
            ram_freed = ram_before_gc['rss_mb'] - ram_after_gc['rss_mb']
            logger.info(
                f"[QUEUE] Task {task.task_id} GC complete "
                f"(RAM: {ram_before_gc['rss_mb']}MB → {ram_after_gc['rss_mb']}MB, "
                f"freed: {ram_freed:.2f}MB)"
            )

            # Release slot
            async with self.lock:
                self.current_tasks -= 1
                if task.task_id in self.active_tasks:
                    del self.active_tasks[task.task_id]

                ram_final = get_ram_usage_mb()
                logger.info(
                    f"[QUEUE] Task {task.task_id} slot released "
                    f"(active: {self.current_tasks}/{self.max_concurrent}, "
                    f"RAM: {ram_final['rss_mb']}MB)"
                )

            # Process next queued task
            await self._process_queue()

    def get_queue_status(self) -> dict:
        """Get current queue status for monitoring."""
        pending_count = len([t for t in self.queue if t.started_at is None])
        active_count = self.current_tasks

        return {
            "max_concurrent": self.max_concurrent,
            "active_tasks": active_count,
            "queued_tasks": pending_count,
            "available_slots": self.max_concurrent - active_count,
            "active_task_ids": list(self.active_tasks.keys())
        }

    async def update_max_concurrent(self, new_max: int):
        """
        Update the maximum concurrent tasks limit.

        Args:
            new_max: New maximum concurrent tasks (must be >= 1)
        """
        if new_max < 1:
            raise ValueError("max_concurrent must be >= 1")

        async with self.lock:
            old_max = self.max_concurrent
            self.max_concurrent = new_max
            logger.info(f"[QUEUE] Updated max_concurrent: {old_max} -> {new_max}")

        # If we increased the limit, process queue to start waiting tasks
        if new_max > old_max:
            await self._process_queue()


# Global queue instance
mockup_queue = MockupTaskQueue(max_concurrent=3)
