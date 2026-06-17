import sys
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

# Windows: ProactorEventLoop antes do uvicorn criar o loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from .database import engine
from .models import Base
from .routers import das, health, pages

# ── Variáveis obrigatórias ───────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY não configurada. Defina a variável de ambiente SECRET_KEY.")

# ── CORS ─────────────────────────────────────────────────────────────────────
# allow_credentials=False → API Key não usa cookies, não precisa de credentials.
# allow_origins=["*"] é seguro nesse caso pois a autenticação é via X-API-Key.
# Para restringir por origem: ALLOWED_ORIGINS=https://app.exemplo.com
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")]

IS_PROD = os.getenv("RAILWAY_ENVIRONMENT") is not None   # Railway define essa var automaticamente


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PGMEI DAS API",
    description="API + Interface para geração e controle de guias DAS do MEI.",
    version="1.0.0",
    lifespan=lifespan,
    # Desativa /docs e /redoc em produção
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
)


# ── Middlewares ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,   # API Key não usa cookies — credentials desnecessário
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=IS_PROD,        # True em produção (Railway), False em dev local
    same_site="lax",
)


# ── Headers de segurança HTTP ────────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"]           = "DENY"
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"]          = "1; mode=block"
    response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
    if IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(pages.router)
app.include_router(das.router)
app.include_router(health.router)
