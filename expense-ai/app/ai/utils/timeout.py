from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Callable, TypeVar

T = TypeVar("T")

class ExecutionTimeoutError(RuntimeError):
    """Raised when execution exceeds the configured timeout."""

# Shared global thread pool executor to avoid overhead and latency spikes
# under high concurrency on every single call.
_GLOBAL_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="timeout_worker")


def execute_with_timeout(timeout_seconds: float, func: Callable[[], T]) -> T:
    """
    Executes a synchronous function with a timeout using a shared global thread pool.

    This implementation avoids the overhead of creating a new ThreadPoolExecutor
    on every call and can later be replaced with asyncio.wait_for() without
    changing the timeout policy.
    """
    future = _GLOBAL_EXECUTOR.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    except TimeoutError as ex:
        future.cancel()
        raise ExecutionTimeoutError(f"Execution exceeded {timeout_seconds} seconds.") from ex