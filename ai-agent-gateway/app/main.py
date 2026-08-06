from fastapi import FastAPI
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name, version='1.0.0')
app.include_router(router)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok', 'env': settings.env}
