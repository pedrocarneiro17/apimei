"""
Operações de banco de dados — inserção com controle de duplicados,
busca de registros e gestão de jobs.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
from sqlalchemy.orm import Session
from . import models

BR_TZ = ZoneInfo("America/Sao_Paulo")


def _agora() -> datetime:
    return datetime.now(BR_TZ)


# ── DASRegistro ──────────────────────────────────────────────────────────────

def upsert_registro(db: Session, dados: dict) -> tuple[models.DASRegistro, bool, bool]:
    """
    Insere ou atualiza um registro DAS.
    Retorna (registro, novo, atualizado).

    Regras de atualização:
      - Se a situação mudou → atualiza tudo
      - Se o PDF ficou disponível e antes era None → atualiza PDF
      - Caso contrário → mantém o existente (duplicado ignorado)
    """
    existente: Optional[models.DASRegistro] = (
        db.query(models.DASRegistro)
        .filter_by(cnpj=dados["cnpj"], ano=dados["ano"], mes=dados["mes"])
        .first()
    )

    if existente is None:
        campos = {k: v for k, v in dados.items() if k not in ("pdf",)}
        registro = models.DASRegistro(**campos)
        if dados.get("pdf"):
            registro.pdf           = dados["pdf"]
            registro.pdf_gerado_em = _agora()
        db.add(registro)
        db.flush()
        return registro, True, False

    nova_situacao  = dados.get("situacao", "")
    situacao_mudou = existente.situacao != nova_situacao
    pdf_novo       = dados.get("pdf") and existente.pdf is None
    virou_liquidado = situacao_mudou and "Liquidado" in nova_situacao

    if situacao_mudou or pdf_novo:
        for campo in ("situacao", "principal", "multa", "juros", "total",
                      "data_vencimento", "data_acolhimento"):
            valor = dados.get(campo)
            if valor is not None:
                setattr(existente, campo, valor)

        if virou_liquidado:
            # mês foi pago — apaga o PDF do banco
            existente.pdf          = None
            existente.pdf_gerado_em = None
        elif dados.get("pdf"):
            existente.pdf          = dados["pdf"]
            existente.pdf_gerado_em = _agora()

        existente.atualizado_em = _agora()
        db.flush()
        return existente, False, True

    return existente, False, False


def buscar_registros(db: Session, cnpj: str, ano: str) -> list[models.DASRegistro]:
    return (
        db.query(models.DASRegistro)
        .filter_by(cnpj=cnpj, ano=ano)
        .order_by(models.DASRegistro.mes)
        .all()
    )


def buscar_registro_mes(db: Session, cnpj: str, ano: str,
                         mes: int) -> Optional[models.DASRegistro]:
    return db.query(models.DASRegistro).filter_by(
        cnpj=cnpj, ano=ano, mes=mes
    ).first()


# ── DASJob ───────────────────────────────────────────────────────────────────

def criar_job(db: Session, job_id: str, cnpj: str, ano: str,
              payload: dict) -> models.DASJob:
    job = models.DASJob(
        id=job_id, cnpj=cnpj, ano=ano,
        status="processando",
        payload_enviado=payload,
    )
    db.add(job)
    db.commit()
    return job


def finalizar_job_sucesso(db: Session, job: models.DASJob,
                           nome: Optional[str], duracao: float,
                           resumo: dict) -> models.DASJob:
    job.status            = "concluido"
    job.nome              = nome
    job.finalizado_em     = datetime.utcnow()
    job.duracao_segundos  = duracao
    job.resumo            = resumo
    db.commit()
    db.refresh(job)
    return job


def finalizar_job_erro(db: Session, job: models.DASJob, erro: dict) -> models.DASJob:
    job.status        = "erro"
    job.finalizado_em = datetime.utcnow()
    job.erro_tipo     = erro.get("tipo")
    job.erro_mensagem = erro.get("mensagem")
    job.erro_etapa    = erro.get("etapa")
    db.commit()
    db.refresh(job)
    return job


def buscar_job(db: Session, job_id: str) -> Optional[models.DASJob]:
    return db.query(models.DASJob).filter_by(id=job_id).first()
