from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime,
    LargeBinary, Text, JSON, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base
from datetime import datetime, timedelta

def _agora():
    """Retorna datetime atual no horário de Brasília (UTC-3)."""
    return datetime.utcnow() - timedelta(hours=3)

Base = declarative_base()


class DASRegistro(Base):
    """Um mês de DAS para um CNPJ/ano. Unique por (cnpj, ano, mes)."""
    __tablename__ = "das_registros"

    id               = Column(Integer, primary_key=True, index=True)
    cnpj             = Column(String(14), nullable=False, index=True)
    ano              = Column(String(4),  nullable=False)
    mes              = Column(Integer,    nullable=False)          # 1–12
    periodo          = Column(String(20), nullable=False)          # "Janeiro/2026"
    situacao         = Column(String(20), nullable=False)          # Liquidado | Devedor | A Vencer
    principal        = Column(Numeric(10, 2), nullable=True)
    multa            = Column(Numeric(10, 2), nullable=True)
    juros            = Column(Numeric(10, 2), nullable=True)
    total            = Column(Numeric(10, 2), nullable=True)
    data_vencimento  = Column(String(10), nullable=True)           # "2026-05-20"
    data_acolhimento = Column(String(10), nullable=True)
    pdf              = Column(LargeBinary, nullable=True)
    pdf_gerado_em    = Column(DateTime, nullable=True)
    criado_em        = Column(DateTime, default=_agora)
    atualizado_em    = Column(DateTime, default=_agora, onupdate=_agora)

    __table_args__ = (
        UniqueConstraint("cnpj", "ano", "mes", name="uq_das_cnpj_ano_mes"),
    )


class DASJob(Base):
    """Rastreia cada execução de scraping (sucesso, erro, duração, resumo)."""
    __tablename__ = "das_jobs"

    id               = Column(String(36), primary_key=True)   # UUID
    cnpj             = Column(String(14), nullable=False, index=True)
    ano              = Column(String(4),  nullable=False)
    nome             = Column(String(200), nullable=True)
    status           = Column(String(20), nullable=False, default="processando")
    # pendente | processando | concluido | erro
    iniciado_em      = Column(DateTime, default=_agora)
    finalizado_em    = Column(DateTime, nullable=True)
    duracao_segundos = Column(Numeric(8, 2), nullable=True)
    resumo           = Column(JSON, nullable=True)
    erro_tipo        = Column(String(100), nullable=True)
    erro_mensagem    = Column(Text, nullable=True)
    erro_etapa       = Column(String(50), nullable=True)
    payload_enviado  = Column(JSON, nullable=True)             # o que foi enviado
    resultado        = Column(JSON, nullable=True)             # ProcessarResponse serializado
