"""
Test script to verify mockup task queue behavior.
"""

import asyncio
import time
from task_queue import MockupTaskQueue


async def mock_task(task_id: int, duration: float):
    """Simulate a mockup generation task."""
    print(f"[Task {task_id}] Started (will take {duration}s)")
    await asyncio.sleep(duration)
    print(f"[Task {task_id}] Completed")
    return f"result_{task_id}"


async def test_queue_basic():
    """Test basic queue functionality with sequential tasks."""
    print("\n=== Test 1: Basic Queue (max_concurrent=2) ===")
    queue = MockupTaskQueue(max_concurrent=2)

    # Submit 5 tasks, only 2 should run at once
    tasks = [
        queue.submit(mock_task, i, 2.0)
        for i in range(1, 6)
    ]

    print(f"\nSubmitted 5 tasks. Queue status: {queue.get_queue_status()}")

    # Wait for all to complete
    results = await asyncio.gather(*tasks)
    print(f"\nAll tasks completed. Results: {results}")
    print(f"Final queue status: {queue.get_queue_status()}")


async def test_queue_concurrent_submission():
    """Test submitting tasks concurrently."""
    print("\n=== Test 2: Concurrent Submission (max_concurrent=3) ===")
    queue = MockupTaskQueue(max_concurrent=3)

    # Submit all tasks at once
    start_time = time.time()

    # 6 tasks, 3 concurrent, each takes 1s = should take ~2s total
    results = await asyncio.gather(*[
        queue.submit(mock_task, i, 1.0)
        for i in range(1, 7)
    ])

    elapsed = time.time() - start_time
    print(f"\n6 tasks (3 concurrent) completed in {elapsed:.2f}s")
    print(f"Expected: ~2s (two batches of 3)")
    print(f"Queue status: {queue.get_queue_status()}")


async def test_queue_dynamic_limit():
    """Test dynamically changing the concurrent limit."""
    print("\n=== Test 3: Dynamic Limit Update ===")
    queue = MockupTaskQueue(max_concurrent=1)

    # Submit 3 tasks with limit=1
    task1 = asyncio.create_task(queue.submit(mock_task, 1, 1.0))
    await asyncio.sleep(0.2)  # Let first task start

    print(f"Queue status (limit=1): {queue.get_queue_status()}")

    # Increase limit to 3
    await queue.update_max_concurrent(3)
    print(f"Increased limit to 3")

    # Submit 2 more tasks - should start immediately now
    task2 = asyncio.create_task(queue.submit(mock_task, 2, 1.0))
    task3 = asyncio.create_task(queue.submit(mock_task, 3, 1.0))
    await asyncio.sleep(0.2)

    print(f"Queue status (limit=3): {queue.get_queue_status()}")

    await asyncio.gather(task1, task2, task3)
    print(f"Final queue status: {queue.get_queue_status()}")


async def test_queue_error_handling():
    """Test that errors don't break the queue."""
    print("\n=== Test 4: Error Handling ===")
    queue = MockupTaskQueue(max_concurrent=2)

    async def failing_task(task_id: int):
        print(f"[Task {task_id}] Started (will fail)")
        await asyncio.sleep(0.5)
        raise ValueError(f"Task {task_id} failed intentionally")

    # Submit 4 tasks: 2 normal, 1 failing, 1 normal
    results = []
    for i, func in enumerate([mock_task, failing_task, mock_task, mock_task], 1):
        try:
            if func == mock_task:
                result = await queue.submit(func, i, 0.5)
            else:
                result = await queue.submit(func, i)
            results.append(("success", result))
        except Exception as e:
            results.append(("error", str(e)))
            print(f"[Task {i}] Caught error: {e}")

    print(f"\nResults: {results}")
    print(f"Queue should recover after errors: {queue.get_queue_status()}")


async def main():
    """Run all tests."""
    print("Starting Queue Tests...")

    await test_queue_basic()
    await asyncio.sleep(1)

    await test_queue_concurrent_submission()
    await asyncio.sleep(1)

    await test_queue_dynamic_limit()
    await asyncio.sleep(1)

    await test_queue_error_handling()

    print("\n=== All Tests Completed ===")


if __name__ == "__main__":
    asyncio.run(main())
