import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import models  # noqa: F401 — registers ORM models with Base.metadata
from .database import create_tables
from .routers import (
    actions,
    activities,
    admin,
    assistant,
    audit,
    auth,
    branches,
    closes,
    credits,
    demo,
    emissions,
    export,
    factors,
    feedbacks,
    notifications,
    projects,
    reports,
    sbti,
    telematics,
    units,
    users,
)
from .version import __version__

logger = logging.getLogger("mirai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="MIRAI Site Carbon Navigator",
    description="建設現場CO2排出量算定システム",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware — explicit origins only (no wildcard with credentials).
allowed_origins = [
    o.strip()
    for o in os.getenv(
        "MIRAI_CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,https://carbon.mirai-dx-platform.com",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware: structured request logging
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "ip": request.client.host if request.client else "-",
        },
    )
    return response


# ---------------------------------------------------------------------------
# Middleware: security headers
# ---------------------------------------------------------------------------

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://static.cloudflareinsights.com; "
        "script-src-attr 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cloudflareinsights.com; "
        "font-src 'self'"
    )
    if os.getenv("MIRAI_ENABLE_HSTS", "0") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ---------------------------------------------------------------------------
# Middleware: simple in-memory rate limiting (per IP, /api paths)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    limit = int(os.getenv("MIRAI_RATE_LIMIT_PER_MIN", "300"))
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_hits.setdefault(ip, [])
        hits = [t for t in hits if now - t < 60.0]
        _rate_hits[ip] = hits
        if len(hits) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry later."},
            )
        hits.append(now)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health", include_in_schema=False)
def health():
    return {"status": "ok", "version": __version__, "time": time.time()}


@app.get("/api/health/ready", include_in_schema=False)
def ready():
    from .database import SessionLocal

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ready", "db": "ok", "version": __version__}
    except Exception as exc:
        logger.error("readiness check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "not_ready", "db": "error"})


@app.get("/api/meta", include_in_schema=False)
def meta():
    return {
        "version": __version__,
        "environment": os.getenv("MIRAI_ENV", "development"),
        "demo_mode": os.getenv("MIRAI_DEMO_MODE", "0") == "1",
    }


# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(factors.router)
app.include_router(activities.router)
app.include_router(emissions.router)
app.include_router(reports.router)
app.include_router(actions.router)
app.include_router(audit.router)
app.include_router(notifications.router)
app.include_router(feedbacks.router)
app.include_router(sbti.router)
app.include_router(demo.router)
app.include_router(closes.router)
app.include_router(units.router)
app.include_router(branches.router)
app.include_router(telematics.router)
app.include_router(export.router)
app.include_router(credits.router)
app.include_router(assistant.router)
app.include_router(admin.router)


# Serve static frontend files (frontend/static/ is the document root, so
# references like /static/css/style.css resolve to frontend/static/css/style.css)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
static_dir = os.path.join(frontend_dir, "static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(static_dir, "favicon.svg")
    if os.path.isfile(favicon_path):
        response = FileResponse(favicon_path, media_type="image/svg+xml")
        response.headers["Cache-Control"] = "no-store"
        return response
    return JSONResponse(status_code=404, content={"detail": "favicon not found"})


if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index_path):
            response = FileResponse(index_path)
            # Never cache the SPA shell: CSP/UI updates must reach browsers
            # immediately (Cloudflare edge + browser heuristic caching).
            response.headers["Cache-Control"] = "no-store"
            return response
        return {"message": "MIRAI Site Carbon Navigator API"}
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": "MIRAI Site Carbon Navigator API"}
