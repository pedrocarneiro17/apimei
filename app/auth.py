"""
Autenticação via sessão (browser) ou API Key (servidor-para-servidor).

Variáveis de ambiente:
  LOGIN_USER / LOGIN_PASS  — credenciais da interface web
  API_KEY                  — chave para chamadas de outros sistemas
                             (header: X-API-Key: <chave>)
"""
import os
import secrets
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

LOGIN_USER = os.getenv("LOGIN_USER", "")
LOGIN_PASS = os.getenv("LOGIN_PASS", "")
API_KEY    = os.getenv("API_KEY", "")
WORKER_KEY = os.getenv("WORKER_KEY", "")

# ── Rate limiting em memória (login) ────────────────────────────────────────
_tentativas: dict[str, list[datetime]] = defaultdict(list)
_lock = threading.Lock()
_MAX_TENTATIVAS = 10   # por IP
_JANELA_S       = 60   # segundos


def _rate_limit_excedido(ip: str) -> bool:
    """Retorna True se o IP excedeu o limite de tentativas de login."""
    agora  = datetime.utcnow()
    inicio = agora - timedelta(seconds=_JANELA_S)
    with _lock:
        _tentativas[ip] = [t for t in _tentativas[ip] if t > inicio]
        if len(_tentativas[ip]) >= _MAX_TENTATIVAS:
            return True
        _tentativas[ip].append(agora)
        return False


def registrar_falha_login(ip: str) -> bool:
    """
    Registra uma tentativa falha e retorna True se o IP deve ser bloqueado.
    Chamado apenas em falhas — não conta tentativas bem-sucedidas.
    """
    return _rate_limit_excedido(ip)


# ── Helpers de autenticação ──────────────────────────────────────────────────

def esta_logado(request: Request) -> bool:
    return request.session.get("autenticado") is True


def _api_key_valida(request: Request) -> bool:
    """
    Comparação em tempo constante para evitar timing attacks.
    Retorna False se API_KEY não estiver configurada.
    """
    if not API_KEY:
        return False
    chave_recebida = request.headers.get("X-API-Key", "")
    return secrets.compare_digest(chave_recebida.encode(), API_KEY.encode())


def exige_worker_key(request: Request):
    """Rotas do worker — valida X-Worker-Key."""
    if not WORKER_KEY:
        return JSONResponse(status_code=503, content={"detail": "WORKER_KEY não configurada no servidor."})
    chave = request.headers.get("X-Worker-Key", "")
    if not secrets.compare_digest(chave.encode(), WORKER_KEY.encode()):
        return JSONResponse(status_code=401, content={"detail": "Worker key inválida."})
    return None


def exige_login_pagina(request: Request):
    """Rotas HTML — redireciona para /login se não autenticado."""
    if not esta_logado(request):
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=302)
    return None


def exige_login_api(request: Request):
    """Rotas de API — aceita sessão de browser OU header X-API-Key."""
    if esta_logado(request) or _api_key_valida(request):
        return None
    return JSONResponse(
        status_code=401,
        content={"detail": "Não autenticado. Use sessão (browser) ou X-API-Key header."},
    )
