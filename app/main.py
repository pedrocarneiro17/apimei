import sys
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

# Windows: ProactorEventLoop antes do uvicorn criar o loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from .database import engine
from .models import Base
from .routers import das, health, pages

SECRET_KEY = os.getenv("SECRET_KEY", "troque-por-uma-chave-secreta-longa")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="PGMEI DAS API",
    description="API + Interface para geração e controle de guias DAS do MEI.",
    version="1.0.0",
    lifespan=lifespan,
)

# Sessão assinada (necessária para login)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=False)

app.include_router(pages.router)
app.include_router(das.router)
app.include_router(health.router)
