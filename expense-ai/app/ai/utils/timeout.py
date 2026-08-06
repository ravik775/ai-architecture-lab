import contextvars
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

    The calling thread's context (including any active OpenTelemetry span) is
    captured via contextvars.copy_context() and replayed inside the worker
    thread via ctx.run(func). Without this, ThreadPoolExecutor.submit() starts
    the worker with an empty context, so any span created inside `func` (e.g.
    the LiteLLM "chat {model}" span) has no parent and shows up in LangSmith
    as a disconnected root trace instead of nesting under the caller.
    """
    ctx = contextvars.copy_context()
    future = _GLOBAL_EXECUTOR.submit(ctx.run,func)
    try:
        return future.result(timeout=timeout_seconds)
    except TimeoutError as ex:
        future.cancel()
        raise ExecutionTimeoutError(f"Execution exceeded {timeout_seconds} seconds.") from ex