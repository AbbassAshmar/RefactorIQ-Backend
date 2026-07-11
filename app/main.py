from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.middleware import AuthContextMiddleware, RequestLoggingMiddleware
from app.core.middlewares.exceptions_handler import register_exception_handlers
from app.auth.routes import router as auth_router
from app.github.routes import router as github_router
from app.projects.routes import router as projects_router
from app.scans.scan_routes import router as scans_router
from app.scan_visualization.routes import router as scan_visualization_router
from app.overview.routes import router as overview_router
from app.files.routes import router as files_router
from app.users.routes import router as users_router
from app.utils.response import ApiResponse

from app.core.database import engine
from app.models import Base

from app.core.logger import configure_logging

from scripts.seed_data import create_admin, create_roles_permissions

configure_logging()
logger = logging.getLogger(__name__)


def initialize_database() -> None:
    if settings.RESET_DB_ON_STARTUP:
        logger.warning("RESET_DB_ON_STARTUP is enabled; recreating all database tables")
        Base.metadata.drop_all(bind=engine)
    else:
        logger.info("RESET_DB_ON_STARTUP is disabled; preserving existing database tables")

    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    initialize_database()

    logger.info("Database tables: %s", list(Base.metadata.tables.keys()))
    logger.info(Base.metadata.tables.keys())

    # seeders
    create_roles_permissions()
    create_admin()

    yield

    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# Middleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthContextMiddleware)
app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)

# Routers

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(github_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(scans_router, prefix="/api/v1")
app.include_router(scan_visualization_router, prefix="/api/v1")
app.include_router(overview_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")


# Health check 


@app.get("/health", tags=["Health"])
def health_check():
    return ApiResponse.success(
        data={"status": "healthy", "version": settings.APP_VERSION}
    )
