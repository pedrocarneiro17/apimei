import sys
import uuid
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

def _agora() -> str:
    """Retorna ISO string no horário de Brasília (UTC-3)."""
    return (datetime.utcnow() - timedelta(hours=3)).isoformat()
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import exige_login_api
from ..schemas import (
    ProcessarRequest, ProcessarResponse,
    MesStatus, Resumo, MesListaResponse,
    JobStatusResponse, ErroDetalhe,
)
from .. import crud, scraper

_executor = ThreadPoolExecutor(max_workers=2)


def _rodar_scraper(cnpj: str, ano: str) -> dict:
    """
    Executa o scraper em uma thread separada com loop próprio.
    Resolve o NotImplementedError do Playwright no Windows com uvicorn.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(scraper.processar_das(cnpj=cnpj, ano=ano))
    finally:
        loop.close()

router = APIRouter(prefix="/das", tags=["DAS"])


# ── POST /das/processar ──────────────────────────────────────────────────────

@router.post("/processar", response_model=ProcessarResponse, summary="Processa DAS de um CNPJ")
async def processar_das(request: Request, req: ProcessarRequest, db: Session = Depends(get_db)):
    auth = exige_login_api(request)
    if auth:
        return auth
    """
    Executa o scraping do PGMEI para o CNPJ e ano informados.
    - Retorna a situação de todos os meses.
    - Gera PDF para meses **Devedor**, **mês atual** e **mês seguinte**.
    - Controle de duplicados: registros já existentes sem mudança são ignorados.
    - Erros detalhados com tipo, mensagem e etapa onde falhou.
    """
    job_id  = str(uuid.uuid4())
    payload = {"cnpj": req.cnpj, "ano": req.ano}
    job     = crud.criar_job(db, job_id=job_id, cnpj=req.cnpj, ano=req.ano, payload=payload)
    agora   = _agora()

    try:
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(_executor, _rodar_scraper, req.cnpj, req.ano)
    except Exception as exc:
        erro = {
            "tipo": type(exc).__name__,
            "mensagem": str(exc),
            "etapa": "scraper",
            "timestamp": _agora(),
        }
        crud.finalizar_job_erro(db, job, erro)
        return ProcessarResponse(
            sucesso=False, job_id=job_id, cnpj=req.cnpj, ano=req.ano,
            processado_em=agora, erro=ErroDetalhe(**erro),
        )

    if not resultado["sucesso"]:
        crud.finalizar_job_erro(db, job, resultado["erro"])
        return ProcessarResponse(
            sucesso=False,
            job_id=job_id,
            cnpj=req.cnpj,
            ano=req.ano,
            processado_em=agora,
            erro=ErroDetalhe(**resultado["erro"]),
        )

    meses_response: list[MesStatus] = []
    cnt = dict(liquidados=0, devedores=0, a_vencer=0,
               pdfs_gerados=0, novos=0, atualizados=0, duplicados=0)

    for m in resultado["meses"]:
        dados_db = {
            "cnpj": req.cnpj, "ano": req.ano,
            "mes": m["mes"], "periodo": m["periodo"], "situacao": m["situacao"],
            "principal": m["principal"], "multa": m["multa"],
            "juros": m["juros"], "total": m["total"],
            "data_vencimento": m["data_vencimento"],
            "data_acolhimento": m["data_acolhimento"],
            "pdf": m.get("pdf"),
        }
        registro, novo, atualizado = crud.upsert_registro(db, dados_db)

        s = m["situacao"]
        if "Liquidado" in s:  cnt["liquidados"] += 1
        elif "Devedor" in s:  cnt["devedores"]  += 1
        else:                 cnt["a_vencer"]   += 1

        if m.get("pdf"):   cnt["pdfs_gerados"] += 1
        if novo:           cnt["novos"]        += 1
        elif atualizado:   cnt["atualizados"]  += 1
        else:              cnt["duplicados"]   += 1

        pdf_ok = registro.pdf is not None
        meses_response.append(MesStatus(
            periodo=m["periodo"], mes=m["mes"], situacao=m["situacao"],
            principal=m["principal"], multa=m["multa"],
            juros=m["juros"], total=m["total"],
            data_vencimento=m["data_vencimento"],
            data_acolhimento=m["data_acolhimento"],
            pdf_disponivel=pdf_ok,
            pdf_url=f"/das/{req.cnpj}/{req.ano}/{m['mes']}/pdf" if pdf_ok else None,
            novo_registro=novo, atualizado=atualizado,
            pdf_erro=m.get("pdf_erro"),
        ))

    db.commit()

    resumo = Resumo(
        total_meses=len(meses_response),
        liquidados=cnt["liquidados"], devedores=cnt["devedores"],
        a_vencer=cnt["a_vencer"], pdfs_gerados=cnt["pdfs_gerados"],
        novos_registros=cnt["novos"], atualizados=cnt["atualizados"],
        duplicados=cnt["duplicados"],
    )

    crud.finalizar_job_sucesso(db, job, nome=resultado.get("nome"),
                               duracao=resultado.get("duracao_segundos", 0),
                               resumo=resumo.model_dump())

    return ProcessarResponse(
        sucesso=True, job_id=job_id, cnpj=req.cnpj, ano=req.ano,
        nome=resultado.get("nome"), processado_em=agora,
        duracao_segundos=resultado.get("duracao_segundos"),
        resumo=resumo, meses=meses_response,
    )


# ── Rotas de jobs — ANTES das rotas com {cnpj}/{ano} para evitar conflito ───

@router.get("/jobs/lista", summary="Lista todos os jobs")
def listar_jobs(db: Session = Depends(get_db)):
    """Retorna os últimos 50 jobs para o histórico da interface."""
    from ..models import DASJob
    jobs = (
        db.query(DASJob)
        .order_by(DASJob.iniciado_em.desc())
        .limit(50).all()
    )
    return [
        {
            "job_id":           j.id,
            "cnpj":             j.cnpj,
            "ano":              j.ano,
            "nome":             j.nome,
            "status":           j.status,
            "iniciado_em":      j.iniciado_em.isoformat() if j.iniciado_em else None,
            "finalizado_em":    j.finalizado_em.isoformat() if j.finalizado_em else None,
            "duracao_segundos": float(j.duracao_segundos) if j.duracao_segundos else None,
            "resumo":           j.resumo,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}", response_model=JobStatusResponse,
            summary="Status de um job de processamento")
def status_job(job_id: str, db: Session = Depends(get_db)):
    """Retorna o status completo de um job (sucesso, erro, duração, resumo)."""
    job = crud.buscar_job(db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    erro = None
    if job.erro_tipo:
        erro = ErroDetalhe(
            tipo=job.erro_tipo,
            mensagem=job.erro_mensagem or "",
            etapa=job.erro_etapa or "",
            timestamp=job.finalizado_em.isoformat() if job.finalizado_em else "",
        )

    return JobStatusResponse(
        job_id=job.id, cnpj=job.cnpj, ano=job.ano, nome=job.nome,
        status=job.status,
        iniciado_em=job.iniciado_em.isoformat(),
        finalizado_em=job.finalizado_em.isoformat() if job.finalizado_em else None,
        duracao_segundos=float(job.duracao_segundos) if job.duracao_segundos else None,
        resumo=job.resumo, payload_enviado=job.payload_enviado, erro=erro,
    )


# ── GET /das/{cnpj}/{ano} — APÓS as rotas fixas ──────────────────────────────

@router.get("/{cnpj}/{ano}", response_model=MesListaResponse,
            summary="Lista meses de um CNPJ/ano")
def listar_meses(cnpj: str, ano: str, db: Session = Depends(get_db)):
    registros = crud.buscar_registros(db, cnpj=cnpj, ano=ano)
    if not registros:
        raise HTTPException(status_code=404, detail="Nenhum registro encontrado para este CNPJ/ano")

    meses = [
        MesStatus(
            periodo=r.periodo, mes=r.mes, situacao=r.situacao,
            principal=float(r.principal) if r.principal is not None else None,
            multa=float(r.multa)  if r.multa  is not None else None,
            juros=float(r.juros)  if r.juros  is not None else None,
            total=float(r.total)  if r.total  is not None else None,
            data_vencimento=r.data_vencimento,
            data_acolhimento=r.data_acolhimento,
            pdf_disponivel=r.pdf is not None,
            pdf_url=f"/das/{cnpj}/{ano}/{r.mes}/pdf" if r.pdf else None,
        )
        for r in registros
    ]
    return MesListaResponse(cnpj=cnpj, ano=ano, meses=meses)


# ── GET /das/{cnpj}/{ano}/{mes}/pdf ──────────────────────────────────────────

@router.get("/{cnpj}/{ano}/{mes}/pdf", summary="Download do PDF do DAS")
def baixar_pdf(cnpj: str, ano: str, mes: int, db: Session = Depends(get_db)):
    registro = crud.buscar_registro_mes(db, cnpj=cnpj, ano=ano, mes=mes)
    if not registro or not registro.pdf:
        raise HTTPException(
            status_code=404,
            detail=f"PDF não disponível para {cnpj} — {ano}/mês {mes:02d}"
        )
    return Response(
        content=registro.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="DAS_{cnpj}_{ano}_{mes:02d}.pdf"'},
    )
