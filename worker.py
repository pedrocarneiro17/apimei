"""
Worker local — executa scraping com IP residencial e posta resultado na API.

Configuração (.env ou variáveis de ambiente):
  WORKER_API_URL        URL da API no Railway/Render
  WORKER_KEY            Chave secreta (mesma configurada no servidor)
  WORKER_POLL_INTERVAL  Segundos entre polls quando fila vazia (padrão: 5)
"""
import os
import sys
import time
import base64
import asyncio
import logging

_log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.log")
logging.basicConfig(
    filename=_log_file,
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger()
log.addHandler(logging.StreamHandler(sys.stdout))

log.info("=== Worker iniciando ===")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import requests
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path)
log.info(f"Carregado .env de: {_env_path}")

from app.scraper import processar_das

API_URL    = os.getenv("WORKER_API_URL", "").rstrip("/")
WORKER_KEY = os.getenv("WORKER_KEY", "")
CONCURRENT = 5
INTERVALO  = int(os.getenv("WORKER_POLL_INTERVAL", "5"))

if not API_URL or not WORKER_KEY:
    log.error("ERRO: defina WORKER_API_URL e WORKER_KEY no .env")
    sys.exit(1)

log.info(f"API: {API_URL} | concorrência: {CONCURRENT} | intervalo: {INTERVALO}s")
HEADERS = {"X-Worker-Key": WORKER_KEY}


def buscar_proximos() -> list[dict]:
    resp = requests.get(
        f"{API_URL}/worker/proximo",
        headers=HEADERS,
        params={"count": CONCURRENT},
        timeout=10,
    )
    if resp.status_code == 204:
        return []
    resp.raise_for_status()
    return resp.json()


def enviar_resultado(job_id: str, resultado: dict) -> None:
    resp = requests.post(
        f"{API_URL}/worker/concluir/{job_id}",
        json={"resultado": resultado},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()


def serializar_pdfs(resultado: dict) -> dict:
    for mes in resultado.get("meses", []):
        if mes.get("pdf") and isinstance(mes["pdf"], bytes):
            mes["pdf"] = base64.b64encode(mes["pdf"]).decode()
    return resultado


async def processar_job(job: dict) -> None:
    job_id        = job["job_id"]
    cnpj          = job["cnpj"]
    ano           = job["ano"]
    meses_com_pdf = set(job.get("meses_com_pdf", []))

    log.info(f"[{job_id[:8]}] Iniciando | CNPJ {cnpj} / {ano}")

    try:
        resultado = await processar_das(cnpj, ano, meses_com_pdf)
        resultado = serializar_pdfs(resultado)
    except Exception as exc:
        resultado = {
            "cnpj": cnpj, "ano": ano, "sucesso": False, "meses": [],
            "erro": {
                "tipo":     type(exc).__name__,
                "mensagem": str(exc),
                "etapa":    "scraper",
            },
        }

    await asyncio.to_thread(enviar_resultado, job_id, resultado)
    log.info(f"[{job_id[:8]}] Concluído | sucesso: {resultado.get('sucesso')}")


async def _loop():
    log.info("Loop iniciado")
    while True:
        try:
            jobs = await asyncio.to_thread(buscar_proximos)
            if not jobs:
                await asyncio.sleep(INTERVALO)
                continue

            log.info(f"Processando {len(jobs)} job(s) em paralelo")
            await asyncio.gather(*[processar_job(job) for job in jobs])

        except Exception as exc:
            log.error(f"Erro no loop: {exc}")
            await asyncio.sleep(INTERVALO)


def main():
    asyncio.run(_loop())


if __name__ == "__main__":
    main()
