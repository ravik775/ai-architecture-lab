import uvicorn
import logging
from fastapi import FastAPI

from app.ai.providers import ProviderRegistry
from app.ai.models import Provider
from app.config import settings
from app.handlers import register_exception_handlers
from app.observability.middleware import RequestContextMiddleware
from app.observability.metrics import configure_metrics
from app.observability.tracing import tracing_configurator
from app.routers.expense import router as expense_router
from app.routers.health import router as health_router

# Configure global logging level
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
app = FastAPI(title="Expense AI", version="1.0.0")
app.add_middleware(RequestContextMiddleware)
tracing_configurator.configure(app)
configure_metrics()
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(expense_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)