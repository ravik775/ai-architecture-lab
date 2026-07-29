from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Callable, TypeVar

T = TypeVar("T")

class ExecutionTimeoutError(RuntimeError):
    """Raised when execution exceeds the configured timeout."""


def execute_with_timeout(timeout_seconds: float, func: Callable[[], T],) -> T:
    """
    Executes a synchronous function with a timeout.

    A dedicated executor is used because the current runtime
    is synchronous. This implementation can later be replaced
    with asyncio.wait_for() without changing TimeoutPolicy.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError as ex:
            future.cancel()
            raise ExecutionTimeoutError(f"Execution exceeded {timeout_seconds} seconds.") from ex