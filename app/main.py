from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .database import create_tables
from . import models  # noqa: F401 — registers ORM models with Base.metadata
import os

from .routers import (
    actions,
    activities,
    audit,
    auth,
    emissions,
    factors,
    notifications,
    projects,
    reports,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="MIRAI Site Carbon Navigator",
    description="建設現場CO2排出量算定システム",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — wildcard origin is not allowed with credentials, so make
# the origin list explicit and configurable via MIRAI_CORS_ORIGINS.
allowed_origins = [
    o.strip()
    for o in os.getenv("MIRAI_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# Serve static frontend files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return {"message": "MIRAI Site Carbon Navigator API"}
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": "MIRAI Site Carbon Navigator API"}
