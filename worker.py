"""
Worker local — executa scraping com IP residencial e posta resultado na API.

Configuração (.env ou variáveis de ambiente):
  WORKER_API_URL   URL da API no Railway/Render, ex: https://apimei.up.railway.app
  WORKER_KEY       Chave secreta (mesma configurada no servidor em WORKER_KEY)

Uso:
  python worker.py
"""
import os
import sys
import time
import base64
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import requests
from dotenv import load_dotenv

load_dotenv()

from app.scraper import processar_das

API_URL    = os.getenv("WORKER_API_URL", "").rstrip("/")
WORKER_KEY = os.getenv("WORKER_KEY", "")
INTERVALO  = int(os.getenv("WORKER_POLL_INTERVAL", "5"))

if not API_URL or not WORKER_KEY:
    print("[worker] ERRO: defina WORKER_API_URL e WORKER_KEY no .env")
    sys.exit(1)

HEADERS = {"X-Worker-Key": WORKER_KEY}


def buscar_proximo():
    resp = requests.get(f"{API_URL}/worker/proximo", headers=HEADERS, timeout=10)
    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.json()


def enviar_resultado(job_id: str, resultado: dict):
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


def main():
    print(f"[worker] Iniciando | API: {API_URL} | intervalo: {INTERVALO}s")
    while True:
        try:
            job = buscar_proximo()
            if not job:
                time.sleep(INTERVALO)
                continue

            job_id        = job["job_id"]
            cnpj          = job["cnpj"]
            ano           = job["ano"]
            meses_com_pdf = set(job.get("meses_com_pdf", []))

            print(f"[worker] Job {job_id} | CNPJ {cnpj} / {ano}")

            try:
                resultado = asyncio.run(processar_das(cnpj, ano, meses_com_pdf))
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

            enviar_resultado(job_id, resultado)
            print(f"[worker] Job {job_id} concluído | sucesso: {resultado.get('sucesso')}")

        except Exception as exc:
            print(f"[worker] Erro no loop: {exc}")
            time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
