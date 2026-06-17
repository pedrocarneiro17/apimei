"""
Endpoints internos usados pelo worker local (PC com IP residencial).
Protegidos por X-Worker-Key.
"""
import base64
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import exige_worker_key
from ..database import get_db
from .. import crud
from ..schemas import MesStatus, Resumo, ProcessarResponse

router = APIRouter(prefix="/worker", tags=["Worker"])


def _agora() -> str:
    return (datetime.utcnow() - timedelta(hours=3)).isoformat()


class WorkerResultado(BaseModel):
    resultado: dict[str, Any]


@router.get("/proximo", summary="Próximos jobs pendentes para o worker")
def proximo_job(request: Request, count: int = 1, db: Session = Depends(get_db)):
    auth = exige_worker_key(request)
    if auth:
        return auth
    jobs = crud.buscar_proximos_pendentes(db, n=count)
    if not jobs:
        return Response(status_code=204)
    return [
        {
            "job_id":        job.id,
            "cnpj":          job.cnpj,
            "ano":           job.ano,
            "meses_com_pdf": job.payload_enviado.get("meses_com_pdf", []),
        }
        for job in jobs
    ]


@router.post("/concluir/{job_id}", summary="Worker posta resultado de um job")
def concluir_job(
    job_id: str,
    body: WorkerResultado,
    request: Request,
    db: Session = Depends(get_db),
):
    auth = exige_worker_key(request)
    if auth:
        return auth

    job = crud.buscar_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    resultado = body.resultado

    if not resultado.get("sucesso"):
        erro = resultado.get("erro") or {}
        crud.finalizar_job_erro(db, job, {
            "tipo":      erro.get("tipo", "ErroWorker"),
            "mensagem":  erro.get("mensagem", "Erro desconhecido no worker"),
            "etapa":     erro.get("etapa", "worker"),
            "timestamp": _agora(),
        })
        return {"ok": True}

    meses_response = []
    cnt = dict(liquidados=0, devedores=0, a_vencer=0,
               pdfs_gerados=0, novos=0, atualizados=0, duplicados=0)

    for m in resultado.get("meses", []):
        pdf_bytes = None
        if m.get("pdf"):
            try:
                pdf_bytes = base64.b64decode(m["pdf"])
            except Exception:
                pass

        dados_db = {
            "cnpj": job.cnpj, "ano": job.ano,
            "mes": m["mes"], "periodo": m["periodo"], "situacao": m["situacao"],
            "principal": m.get("principal"), "multa": m.get("multa"),
            "juros": m.get("juros"), "total": m.get("total"),
            "data_vencimento":  m.get("data_vencimento"),
            "data_acolhimento": m.get("data_acolhimento"),
            "pdf": pdf_bytes,
        }
        registro, novo, atualizado = crud.upsert_registro(db, dados_db)

        s = m["situacao"]
        if "Liquidado" in s:  cnt["liquidados"] += 1
        elif "Devedor"  in s: cnt["devedores"]  += 1
        else:                 cnt["a_vencer"]   += 1

        if pdf_bytes:    cnt["pdfs_gerados"] += 1
        if novo:         cnt["novos"]        += 1
        elif atualizado: cnt["atualizados"]  += 1
        else:            cnt["duplicados"]   += 1

        pdf_ok = registro.pdf is not None
        meses_response.append(MesStatus(
            periodo=m["periodo"], mes=m["mes"], situacao=m["situacao"],
            principal=m.get("principal"), multa=m.get("multa"),
            juros=m.get("juros"), total=m.get("total"),
            data_vencimento=m.get("data_vencimento"),
            data_acolhimento=m.get("data_acolhimento"),
            pdf_disponivel=pdf_ok,
            pdf_url=f"/das/{job.cnpj}/{job.ano}/{m['mes']}/pdf" if pdf_ok else None,
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

    resposta = ProcessarResponse(
        sucesso=True,
        job_id=job_id,
        cnpj=job.cnpj,
        ano=job.ano,
        nome=resultado.get("nome"),
        processado_em=_agora(),
        duracao_segundos=resultado.get("duracao_segundos"),
        resumo=resumo,
        meses=meses_response,
    ).model_dump()

    crud.finalizar_job_sucesso_com_resultado(
        db, job,
        nome=resultado.get("nome"),
        duracao=resultado.get("duracao_segundos") or 0,
        resumo=resumo.model_dump(),
        resultado=resposta,
    )

    return {"ok": True}
