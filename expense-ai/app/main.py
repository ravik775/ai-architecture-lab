import uvicorn
from fastapi import FastAPI
from app.routers.expense import router as expense_router
from app.routers.health import router as health_router
app = FastAPI(title="Expense AI", version="1.0.0")
app.include_router(health_router)
app.include_router(expense_router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)