import time

import structlog
from fastapi import FastAPI, Request

from app.api.router import api_router
from app.core.logging import setup_logging

setup_logging()

logger = structlog.get_logger(__name__)

app = FastAPI(title="CatRuler_Reborn")
app.include_router(api_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    return response
