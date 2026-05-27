from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import esta_logado, exige_login_pagina, LOGIN_USER, LOGIN_PASS
from .. import crud

router    = APIRouter(tags=["Interface"])
templates = Jinja2Templates(directory="templates")


# ── Login / Logout ───────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if esta_logado(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "erro": None, "next": next})


@router.post("/login")
async def login_submit(
    request: Request,
    usuario: str = Form(...),
    senha:   str = Form(...),
    next:    str = Form(default="/"),
):
    if usuario == LOGIN_USER and senha == LOGIN_PASS:
        request.session["autenticado"] = True
        return RedirectResponse(url=next or "/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "erro": "Usuário ou senha incorretos.",
        "next": next,
    }, status_code=401)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# ── Páginas protegidas ───────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    redir = exige_login_pagina(request)
    if redir:
        return redir

    from ..models import DASJob
    jobs = (
        db.query(DASJob)
        .order_by(DASJob.iniciado_em.desc())
        .limit(20).all()
    )
    return templates.TemplateResponse("index.html", {"request": request, "jobs": jobs})


@router.get("/detalhes/{cnpj}/{ano}", response_class=HTMLResponse)
def detalhes(cnpj: str, ano: str, request: Request, db: Session = Depends(get_db)):
    redir = exige_login_pagina(request)
    if redir:
        return redir

    registros = crud.buscar_registros(db, cnpj=cnpj, ano=ano)
    return templates.TemplateResponse("detalhes.html", {
        "request": request,
        "cnpj": cnpj,
        "ano": ano,
        "registros": registros,
    })
