import sys
import asyncio

# Windows: define ProactorEventLoop ANTES do uvicorn criar o event loop
# Necessário para o Playwright conseguir criar subprocessos
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
