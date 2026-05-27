"""
Autenticação via sessão (browser) ou API Key (servidor-para-servidor).

Variáveis de ambiente:
  LOGIN_USER / LOGIN_PASS  — credenciais da interface web
  API_KEY                  — chave para chamadas de outros sistemas
                             (header: X-API-Key: <chave>)
"""
import os
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

LOGIN_USER = os.getenv("LOGIN_USER", "admin")
LOGIN_PASS = os.getenv("LOGIN_PASS", "admin")
API_KEY    = os.getenv("API_KEY", "")          # vazio = API Key desativada


def esta_logado(request: Request) -> bool:
    return request.session.get("autenticado") is True


def _api_key_valida(request: Request) -> bool:
    """Verifica o header X-API-Key. Retorna False se API_KEY não estiver configurada."""
    if not API_KEY:
        return False
    return request.headers.get("X-API-Key") == API_KEY


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
