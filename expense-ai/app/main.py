from contextlib import asynccontextmanager

import uvicorn
import logging
from fastapi import FastAPI

from app.agents.expense_approval_graph import close_checkpointer_resources
from app.handlers import register_exception_handlers
from app.observability.middleware import RequestContextMiddleware
from app.observability.metrics import configure_metrics
from app.observability.tracing import tracing_configurator
from app.routers.expense import router as expense_router
from app.routers.health import router as health_router

# Configure global logging level
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",force=True,)
logging.getLogger("expense_ai").setLevel(logging.INFO)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application-level resources.

    PostgreSQL resources are created lazily by agentic mode and closed
    when the FastAPI process shuts down.
    """
    try:
        yield
    finally:
        close_checkpointer_resources()
app = FastAPI(title="Expense AI", version="1.0.0", lifespan=lifespan,)
app.add_middleware(RequestContextMiddleware)
tracing_configurator.configure(app)
configure_metrics()
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(expense_router)



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)