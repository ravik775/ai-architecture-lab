from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class ExecutionContext:
    """
    Runtime metadata for a single AI execution.

    This object should NEVER contain business data.
    It only tracks runtime execution state.
    """

    execution_id: UUID = field(default_factory=uuid4)

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    provider: str = ""

    model: str = ""

    attempt: int = 1