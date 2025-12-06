"""
Background Job Queue.

Provides a general-purpose async job queue for long-running operations with:
- Job status tracking (pending, running, completed, failed)
- Job result/error storage
- Configurable concurrency limits
- Job timeout handling
- Optional persistence for job status

Usage:
    from utils.job_queue import get_job_queue, JobStatus

    # Get queue instance
    queue = get_job_queue()

    # Submit a job
    job_id = await queue.submit(my_async_function, arg1, arg2, name="my_job")

    # Check job status
    status = queue.get_job_status(job_id)
    print(status.state)  # JobState.RUNNING

    # Wait for job completion
    result = await queue.wait_for_job(job_id)

Configuration:
    JOB_QUEUE_MAX_CONCURRENT: Max concurrent jobs (default: 5)
    JOB_QUEUE_DEFAULT_TIMEOUT: Default job timeout in seconds (default: 600)
"""

import asyncio
import os
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from utils.logging import get_logger
from utils.time import get_uae_time

logger = get_logger("utils.job_queue")


class JobState(str, Enum):
    """Job execution states."""
    PENDING = "pending"       # Waiting in queue
    RUNNING = "running"       # Currently executing
    COMPLETED = "completed"   # Finished successfully
    FAILED = "failed"         # Finished with error
    CANCELLED = "cancelled"   # Cancelled before completion
    TIMEOUT = "timeout"       # Timed out during execution


@dataclass
class JobStatus:
    """Status information for a job."""
    job_id: str
    name: str
    state: JobState
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    progress: Optional[float] = None  # 0.0 to 1.0
    progress_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_done(self) -> bool:
        """Check if job has finished (success, fail, or cancelled)."""
        return self.state in (
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.TIMEOUT,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get job duration in seconds."""
        if not self.started_at:
            return None
        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "job_id": self.job_id,
            "name": self.name,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "metadata": self.metadata,
            # Note: result not included as it may not be JSON serializable
        }


@dataclass
class Job:
    """Internal job representation."""
    job_id: str
    name: str
    func: Callable
    args: tuple
    kwargs: dict
    timeout: Optional[float]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    state: JobState = JobState.PENDING
    result: Any = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    progress: Optional[float] = None
    progress_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_event: asyncio.Event = field(default_factory=asyncio.Event)
    completed_event: asyncio.Event = field(default_factory=asyncio.Event)
    _task: Optional[asyncio.Task] = None

    def get_status(self) -> JobStatus:
        """Get current job status."""
        return JobStatus(
            job_id=self.job_id,
            name=self.name,
            state=self.state,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            result=self.result,
            error=self.error,
            error_traceback=self.error_traceback,
            progress=self.progress,
            progress_message=self.progress_message,
            metadata=self.metadata,
        )


class JobQueue:
    """
    Async job queue with status tracking.

    Features:
    - Concurrent job execution with configurable limits
    - Job status tracking with progress updates
    - Timeout handling per job
    - Result/error storage
    - Job cancellation
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        default_timeout: float = 600.0,
        max_history: int = 1000,
    ):
        """
        Initialize job queue.

        Args:
            max_concurrent: Maximum concurrent jobs
            default_timeout: Default job timeout in seconds
            max_history: Maximum completed jobs to keep in history
        """
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.max_history = max_history

        self._jobs: Dict[str, Job] = {}
        self._pending_queue: List[str] = []
        self._active_count = 0
        self._lock = asyncio.Lock()
        self._history: List[str] = []  # Completed job IDs for cleanup

        logger.info(
            f"[JOB_QUEUE] Initialized (max_concurrent={max_concurrent}, "
            f"default_timeout={default_timeout}s)"
        )

    async def submit(
        self,
        func: Callable,
        *args,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Submit a job to the queue.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            name: Human-readable job name
            timeout: Job timeout in seconds (None = use default)
            metadata: Additional job metadata
            **kwargs: Keyword arguments for func

        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        job_name = name or func.__name__
        job_timeout = timeout if timeout is not None else self.default_timeout

        job = Job(
            job_id=job_id,
            name=job_name,
            func=func,
            args=args,
            kwargs=kwargs,
            timeout=job_timeout,
            created_at=get_uae_time(),
            metadata=metadata or {},
        )

        async with self._lock:
            self._jobs[job_id] = job
            self._pending_queue.append(job_id)

            pending_count = len(self._pending_queue)
            logger.info(
                f"[JOB_QUEUE] Job '{job_name}' submitted (id={job_id[:8]}, "
                f"pending={pending_count}, active={self._active_count}/{self.max_concurrent})"
            )

        # Try to start jobs
        await self._process_queue()

        return job_id

    async def _process_queue(self) -> None:
        """Start pending jobs if slots are available."""
        async with self._lock:
            while self._active_count < self.max_concurrent and self._pending_queue:
                job_id = self._pending_queue.pop(0)
                job = self._jobs.get(job_id)

                if not job or job.state != JobState.PENDING:
                    continue

                # Start the job
                job.state = JobState.RUNNING
                job.started_at = get_uae_time()
                self._active_count += 1

                wait_time = (job.started_at - job.created_at).total_seconds()
                logger.info(
                    f"[JOB_QUEUE] Starting job '{job.name}' (id={job_id[:8]}, "
                    f"waited={wait_time:.1f}s, active={self._active_count}/{self.max_concurrent})"
                )

                # Signal that job has started
                job.started_event.set()

                # Run job in background
                job._task = asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: Job) -> None:
        """Execute a job with timeout handling."""
        try:
            # Execute with timeout
            if job.timeout:
                result = await asyncio.wait_for(
                    job.func(*job.args, **job.kwargs),
                    timeout=job.timeout,
                )
            else:
                result = await job.func(*job.args, **job.kwargs)

            job.result = result
            job.state = JobState.COMPLETED
            job.completed_at = get_uae_time()

            duration = job.duration_seconds or 0
            logger.info(
                f"[JOB_QUEUE] Job '{job.name}' completed (id={job.job_id[:8]}, "
                f"duration={duration:.1f}s)"
            )

        except asyncio.TimeoutError:
            job.state = JobState.TIMEOUT
            job.error = f"Job timed out after {job.timeout} seconds"
            job.completed_at = get_uae_time()
            logger.warning(
                f"[JOB_QUEUE] Job '{job.name}' timed out (id={job.job_id[:8]})"
            )

        except asyncio.CancelledError:
            job.state = JobState.CANCELLED
            job.completed_at = get_uae_time()
            logger.info(
                f"[JOB_QUEUE] Job '{job.name}' cancelled (id={job.job_id[:8]})"
            )

        except Exception as e:
            job.state = JobState.FAILED
            job.error = str(e)
            job.error_traceback = traceback.format_exc()
            job.completed_at = get_uae_time()
            logger.error(
                f"[JOB_QUEUE] Job '{job.name}' failed (id={job.job_id[:8]}): {e}"
            )

        finally:
            # Signal completion
            job.completed_event.set()

            # Release slot and process queue
            async with self._lock:
                self._active_count -= 1
                self._history.append(job.job_id)

                # Cleanup old history
                while len(self._history) > self.max_history:
                    old_id = self._history.pop(0)
                    if old_id in self._jobs:
                        del self._jobs[old_id]

            # Start next jobs
            await self._process_queue()

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Get status of a job by ID."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        return job.get_status()

    def get_job_result(self, job_id: str) -> Any:
        """
        Get result of a completed job.

        Raises:
            KeyError: Job not found
            RuntimeError: Job not completed or failed
        """
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job {job_id} not found")

        if job.state == JobState.FAILED:
            raise RuntimeError(f"Job failed: {job.error}")
        if job.state == JobState.TIMEOUT:
            raise RuntimeError(f"Job timed out: {job.error}")
        if job.state == JobState.CANCELLED:
            raise RuntimeError("Job was cancelled")
        if job.state != JobState.COMPLETED:
            raise RuntimeError(f"Job not completed (state={job.state})")

        return job.result

    async def wait_for_job(
        self,
        job_id: str,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Wait for a job to complete and return its result.

        Args:
            job_id: Job ID to wait for
            timeout: Optional timeout in seconds

        Returns:
            Job result

        Raises:
            KeyError: Job not found
            asyncio.TimeoutError: Wait timeout exceeded
            RuntimeError: Job failed
        """
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job {job_id} not found")

        # Wait for completion
        if timeout:
            await asyncio.wait_for(job.completed_event.wait(), timeout=timeout)
        else:
            await job.completed_event.wait()

        return self.get_job_result(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending or running job.

        Returns:
            True if job was cancelled, False if already done
        """
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.is_done:
            return False

        async with self._lock:
            if job.state == JobState.PENDING:
                # Remove from pending queue
                if job_id in self._pending_queue:
                    self._pending_queue.remove(job_id)
                job.state = JobState.CANCELLED
                job.completed_at = get_uae_time()
                job.completed_event.set()
                logger.info(f"[JOB_QUEUE] Job '{job.name}' cancelled (pending)")
                return True

            elif job.state == JobState.RUNNING and job._task:
                # Cancel running task
                job._task.cancel()
                logger.info(f"[JOB_QUEUE] Job '{job.name}' cancellation requested")
                return True

        return False

    def update_progress(
        self,
        job_id: str,
        progress: float,
        message: Optional[str] = None,
    ) -> bool:
        """
        Update job progress (call from within job function).

        Args:
            job_id: Job ID
            progress: Progress value 0.0 to 1.0
            message: Optional progress message

        Returns:
            True if updated, False if job not found
        """
        job = self._jobs.get(job_id)
        if not job:
            return False

        job.progress = max(0.0, min(1.0, progress))
        job.progress_message = message
        return True

    def list_jobs(
        self,
        state: Optional[JobState] = None,
        limit: int = 100,
    ) -> List[JobStatus]:
        """
        List jobs, optionally filtered by state.

        Args:
            state: Filter by job state
            limit: Maximum jobs to return

        Returns:
            List of job statuses (most recent first)
        """
        jobs = list(self._jobs.values())

        if state:
            jobs = [j for j in jobs if j.state == state]

        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return [j.get_status() for j in jobs[:limit]]

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        states = {}
        for job in self._jobs.values():
            state_name = job.state.value
            states[state_name] = states.get(state_name, 0) + 1

        return {
            "max_concurrent": self.max_concurrent,
            "active_jobs": self._active_count,
            "pending_jobs": len(self._pending_queue),
            "total_jobs": len(self._jobs),
            "jobs_by_state": states,
        }


# Global queue instance
_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Get or create the global job queue."""
    global _queue
    if _queue is None:
        from app_settings import settings

        _queue = JobQueue(
            max_concurrent=settings.job_queue_max_concurrent,
            default_timeout=settings.job_queue_default_timeout,
        )
    return _queue


def set_job_queue(queue: JobQueue) -> None:
    """Set a custom job queue (for testing)."""
    global _queue
    _queue = queue
