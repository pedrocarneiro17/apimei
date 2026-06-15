from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


# ── Request ──────────────────────────────────────────────────────────────────

class ProcessarRequest(BaseModel):
    cnpj: str = Field(..., description="CNPJ sem formatação — 14 dígitos")
    ano:  str = Field(..., description="Ano-calendário, ex: 2026")

    @field_validator("cnpj")
    @classmethod
    def cnpj_apenas_numeros(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 14:
            raise ValueError("CNPJ deve conter 14 dígitos numéricos")
        return digits

    @field_validator("ano")
    @classmethod
    def ano_valido(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 4:
            raise ValueError("Ano deve ter 4 dígitos")
        return v


# ── Blocos de resposta ───────────────────────────────────────────────────────

class ErroDetalhe(BaseModel):
    tipo:      str
    mensagem:  str
    etapa:     str
    timestamp: str


class MesStatus(BaseModel):
    periodo:          str
    mes:              int
    situacao:         str           # Liquidado | Devedor | A Vencer
    principal:        Optional[float] = None
    multa:            Optional[float] = None
    juros:            Optional[float] = None
    total:            Optional[float] = None
    data_vencimento:  Optional[str]   = None
    data_acolhimento: Optional[str]   = None
    pdf_disponivel:   bool = False
    pdf_url:          Optional[str]   = None
    # controle de duplicados
    novo_registro:    bool = False
    atualizado:       bool = False
    # erro de geração de PDF (se houver)
    pdf_erro:         Optional[str]   = None


class Resumo(BaseModel):
    total_meses:      int
    liquidados:       int
    devedores:        int
    a_vencer:         int
    pdfs_gerados:     int
    novos_registros:  int
    atualizados:      int
    duplicados:       int           # registros já existentes sem mudança


# ── Resposta principal ───────────────────────────────────────────────────────

class ProcessarResponse(BaseModel):
    sucesso:           bool
    job_id:            str
    cnpj:              str
    ano:               str
    nome:              Optional[str]         = None
    processado_em:     str
    duracao_segundos:  Optional[float]       = None
    resumo:            Optional[Resumo]      = None
    meses:             List[MesStatus]       = []
    erro:              Optional[ErroDetalhe] = None


# ── Job status ───────────────────────────────────────────────────────────────

class JobStatusResponse(BaseModel):
    job_id:            str
    cnpj:              str
    ano:               str
    nome:              Optional[str]         = None
    status:            str                   # processando | concluido | erro
    iniciado_em:       str
    finalizado_em:     Optional[str]         = None
    duracao_segundos:  Optional[float]       = None
    resumo:            Optional[dict]        = None
    payload_enviado:   Optional[dict]        = None
    erro:              Optional[ErroDetalhe] = None


# ── Lista de meses (GET) ─────────────────────────────────────────────────────

class MesListaResponse(BaseModel):
    cnpj:  str
    ano:   str
    meses: List[MesStatus]


# ── DASN SIMEI ───────────────────────────────────────────────────────────────

class ConsultarDASNRequest(BaseModel):
    cnpj: str = Field(..., description="CNPJ sem formatação — 14 dígitos")

    @field_validator("cnpj")
    @classmethod
    def cnpj_apenas_numeros(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 14:
            raise ValueError("CNPJ deve conter 14 dígitos numéricos")
        return digits


class DASNAno(BaseModel):
    ano:               str
    status:            str            # Apresentada | Não Apresentada
    data_apresentacao: Optional[str] = None


class DASNResponse(BaseModel):
    sucesso:           bool
    cnpj:              str
    anos:              List[DASNAno]       = []
    consultado_em:     Optional[str]       = None
    duracao_segundos:  Optional[float]     = None
    erro:              Optional[ErroDetalhe] = None
