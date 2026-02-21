from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.middleware import AuthContextMiddleware, RequestLoggingMiddleware
from app.core.middlewares.exceptions_handler import register_exception_handlers
from app.users.routes import router as users_router
from app.auth.routes import router as auth_router
from app.utils.response import ApiResponse

from app.core.database import engine 
from app.models import Base

from app.core.logger import configure_logging
import logging

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Initialization tasks
    Base.metadata.create_all(bind=engine)  
    
    yield

    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# ── Middleware ────────────────────────────────────────────────

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

# ── Routers ───────────────────────────────────────────────────

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


# ── Health check ──────────────────────────────────────────────


@app.get("/health", tags=["Health"])
def health_check():
    return ApiResponse.success(
        data={"status": "healthy", "version": settings.APP_VERSION}
    )
