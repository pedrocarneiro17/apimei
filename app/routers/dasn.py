import sys
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import exige_login_api
from ..schemas import ConsultarDASNRequest, DASNAno, DASNResponse, ErroDetalhe
from .. import crud, scraper_dasn
from ..models import DASNJob

_executor = ThreadPoolExecutor(max_workers=15)


def _rodar_scraper(cnpj: str) -> dict:
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(scraper_dasn.consultar_dasn(cnpj=cnpj))
    finally:
        loop.close()


router = APIRouter(prefix="/dasn", tags=["DASN SIMEI"])


@router.post("/consultar", response_model=DASNResponse,
             summary="Consulta situação das declarações DASN SIMEI")
async def consultar_dasn(request: Request, req: ConsultarDASNRequest,
                          db: Session = Depends(get_db)):
    """
    Acessa o DASN SIMEI da Receita Federal e retorna, para cada ano
    disponível, o status da declaração (Apresentada / Não Apresentada)
    e a data de apresentação quando houver.
    """
    auth = exige_login_api(request)
    if auth:
        return auth

    job_id = str(uuid.uuid4())
    job = crud.criar_dasn_job(db, job_id=job_id, cnpj=req.cnpj)

    loop = asyncio.get_event_loop()
    resultado = await loop.run_in_executor(
        _executor,
        partial(_rodar_scraper, req.cnpj),
    )

    if not resultado["sucesso"]:
        erro_raw = resultado.get("erro") or {}
        crud.finalizar_dasn_job_erro(db, job, erro_raw)
        return DASNResponse(
            sucesso=False,
            cnpj=req.cnpj,
            consultado_em=resultado.get("consultado_em"),
            erro=ErroDetalhe(
                tipo=erro_raw.get("tipo", "ErroDesconhecido"),
                mensagem=erro_raw.get("mensagem", ""),
                etapa=erro_raw.get("etapa", ""),
                timestamp=erro_raw.get("timestamp", ""),
            ),
        )

    anos_raw = resultado.get("anos", [])
    crud.finalizar_dasn_job_sucesso(
        db, job,
        duracao=resultado.get("duracao_segundos", 0),
        anos=anos_raw,
    )

    anos = [
        DASNAno(
            ano=a["ano"],
            status=a["status"],
            data_apresentacao=a.get("data_apresentacao"),
        )
        for a in anos_raw
    ]

    return DASNResponse(
        sucesso=True,
        cnpj=req.cnpj,
        anos=anos,
        consultado_em=resultado.get("consultado_em"),
        duracao_segundos=resultado.get("duracao_segundos"),
    )


@router.get("/jobs/lista", summary="Lista as últimas consultas DASN SIMEI")
def listar_dasn_jobs(request: Request, db: Session = Depends(get_db)):
    auth = exige_login_api(request)
    if auth:
        return auth

    jobs = (
        db.query(DASNJob)
        .order_by(DASNJob.iniciado_em.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "job_id":           j.id,
            "cnpj":             j.cnpj,
            "status":           j.status,
            "iniciado_em":      j.iniciado_em.isoformat() if j.iniciado_em else None,
            "finalizado_em":    j.finalizado_em.isoformat() if j.finalizado_em else None,
            "duracao_segundos": float(j.duracao_segundos) if j.duracao_segundos else None,
            "anos":             j.anos,
            "erro_tipo":        j.erro_tipo,
            "erro_mensagem":    j.erro_mensagem,
            "erro_etapa":       j.erro_etapa,
        }
        for j in jobs
    ]


@router.delete("/jobs/{job_id}", summary="Remove uma consulta DASN do histórico")
def deletar_dasn_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    auth = exige_login_api(request)
    if auth:
        return auth
    ok = crud.deletar_dasn_job(db, job_id=job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return {"ok": True}
