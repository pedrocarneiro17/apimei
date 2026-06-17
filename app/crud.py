"""
Operações de banco de dados — inserção com controle de duplicados,
busca de registros e gestão de jobs.
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from . import models


def _agora() -> datetime:
    """Retorna datetime atual no horário de Brasília (UTC-3)."""
    return datetime.utcnow() - timedelta(hours=3)


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

    nova_situacao   = dados.get("situacao", "")
    situacao_mudou  = existente.situacao != nova_situacao
    virou_liquidado = situacao_mudou and "Liquidado" in nova_situacao
    eh_devedor      = "Devedor" in nova_situacao

    # PDF novo: (a) não tinha antes, ou (b) é Devedor (juros muda todo dia)
    pdf_novo = dados.get("pdf") and (existente.pdf is None or eh_devedor)

    if situacao_mudou or pdf_novo:
        for campo in ("situacao", "principal", "multa", "juros", "total",
                      "data_vencimento", "data_acolhimento"):
            valor = dados.get(campo)
            if valor is not None:
                setattr(existente, campo, valor)

        if virou_liquidado:
            # mês foi pago — apaga o PDF do banco
            existente.pdf           = None
            existente.pdf_gerado_em = None
        elif dados.get("pdf"):
            existente.pdf           = dados["pdf"]
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
              payload: dict, status: str = "processando") -> models.DASJob:
    job = models.DASJob(
        id=job_id, cnpj=cnpj, ano=ano,
        status=status,
        payload_enviado=payload,
    )
    db.add(job)
    db.commit()
    return job


def buscar_proximos_pendentes(db: Session, n: int = 1) -> list[models.DASJob]:
    jobs = (
        db.query(models.DASJob)
        .filter_by(status="pendente")
        .order_by(models.DASJob.iniciado_em)
        .limit(n)
        .all()
    )
    for job in jobs:
        job.status = "processando"
    db.commit()
    return jobs


def finalizar_job_sucesso_com_resultado(
    db: Session, job: models.DASJob,
    nome: Optional[str], duracao: float,
    resumo: dict, resultado: dict,
) -> models.DASJob:
    job.status           = "concluido"
    job.nome             = nome
    job.finalizado_em    = _agora()
    job.duracao_segundos = duracao
    job.resumo           = resumo
    job.resultado        = resultado
    db.commit()
    db.refresh(job)
    return job


def finalizar_job_sucesso(db: Session, job: models.DASJob,
                           nome: Optional[str], duracao: float,
                           resumo: dict) -> models.DASJob:
    job.status            = "concluido"
    job.nome              = nome
    job.finalizado_em     = _agora()
    job.duracao_segundos  = duracao
    job.resumo            = resumo
    db.commit()
    db.refresh(job)
    return job


def finalizar_job_erro(db: Session, job: models.DASJob, erro: dict) -> models.DASJob:
    job.status        = "erro"
    job.finalizado_em = _agora()
    job.erro_tipo     = erro.get("tipo")
    job.erro_mensagem = erro.get("mensagem")
    job.erro_etapa    = erro.get("etapa")
    db.commit()
    db.refresh(job)
    return job


def buscar_job(db: Session, job_id: str) -> Optional[models.DASJob]:
    return db.query(models.DASJob).filter_by(id=job_id).first()


def deletar_job(db: Session, job_id: str) -> bool:
    job = db.query(models.DASJob).filter_by(id=job_id).first()
    if not job:
        return False
    db.delete(job)
    db.commit()
    return True
