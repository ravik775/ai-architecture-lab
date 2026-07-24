import uvicorn
import logging
from fastapi import FastAPI
from app.routers.expense import router as expense_router
from app.routers.health import router as health_router

# Configure global logging level
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="Expense AI", version="1.0.0")
app.include_router(health_router)
app.include_router(expense_router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)