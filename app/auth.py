"""
Autenticação simples via sessão assinada.
Credenciais definidas nas variáveis de ambiente LOGIN_USER e LOGIN_PASS.
"""
import os
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

LOGIN_USER = os.getenv("LOGIN_USER", "admin")
LOGIN_PASS = os.getenv("LOGIN_PASS", "admin")


def esta_logado(request: Request) -> bool:
    return request.session.get("autenticado") is True


def exige_login_pagina(request: Request):
    """Dependência para rotas HTML — redireciona para /login se não autenticado."""
    if not esta_logado(request):
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=302)
    return None


def exige_login_api(request: Request):
    """Dependência para rotas de API — retorna 401 JSON se não autenticado."""
    if not esta_logado(request):
        return JSONResponse(status_code=401, content={"detail": "Não autenticado"})
    return None
