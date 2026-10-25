"""Meridian — FastAPI entrypoint. One process: /api/* + built SPA."""

from __future__ import annotations

import json
import logging
import signal
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from .config import get_settings
from .routers import data, genie, health

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
    stream=sys.stdout,
)
logging.getLogger().handlers[0].formatter = logging.Formatter(
    '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
)
log = logging.getLogger("meridian")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Meridian", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    try:
        response = await call_next(request)
    except HTTPException:
        raise
    except Exception as e:  # single error envelope
        log.error(json.dumps({"request_id": request_id, "path": request.url.path, "error": repr(e)}))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL", "message": "Internal error",
                               "request_id": request_id, "retryable": False}},
        )
    response.headers["X-Request-Id"] = request_id
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self' data:"
    )
    return response


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={
        "error": {"code": detail.get("code", "HTTP_ERROR"),
                  "message": detail.get("message", str(exc.detail)),
                  "request_id": "", "retryable": detail.get("retryable", False)}})


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "error": {"code": "VALIDATION", "message": "Invalid request",
                  "request_id": "", "retryable": False}})


@app.exception_handler(ValueError)
async def value_exc(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={
        "error": {"code": "BAD_REQUEST", "message": str(exc), "request_id": "", "retryable": False}})


app.include_router(health.router)
app.include_router(data.router)
app.include_router(genie.router)


class SpaFiles(StaticFiles):
    """Static files with SPA fallback → index.html for client routes."""

    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 404 and not path.startswith("api/"):
            return await super().get_response("index.html", scope)
        return resp


if STATIC_DIR.exists():
    app.mount("/", SpaFiles(directory=str(STATIC_DIR), html=True), name="spa")


@app.on_event("startup")
def _startup() -> None:
    settings = get_settings()
    log.info(json.dumps({"event": "startup", "app_mode": settings.app_mode,
                         "auth_mode": settings.auth_mode,
                         "warehouse": bool(settings.warehouse_id),
                         "genie_space": bool(settings.genie_space_id)}))


def _sigterm(*_):
    log.info('{"event":"sigterm"}')
    sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm)
