# PGMEI DAS API — Documentação

Base URL de produção: `https://<seu-app>.railway.app`  
Base URL local: `http://localhost:8000`

Documentação interativa (Swagger): `<base-url>/docs`

---

## Autenticação

A API suporta dois métodos de autenticação:

### 1. API Key — recomendado para integração servidor-para-servidor

Adicione o header `X-API-Key` em todas as requisições:

```
X-API-Key: sua-chave-aqui
```

Configure a chave na variável de ambiente `API_KEY` no Railway.

### 2. Sessão de browser — para uso pela interface web

Faça login via `POST /login` (form-urlencoded) e envie o cookie `session` nas chamadas seguintes. Usado automaticamente pelo painel web.

---

## Endpoints

### 1. Processar DAS de um CNPJ

Acessa o PGMEI da Receita Federal, lê a situação de todos os meses do ano informado e gera PDFs para meses em atraso e mês atual/seguinte.

```
POST /das/processar
Content-Type: application/json
X-API-Key: sua-chave-aqui
```

**Body:**
```json
{
  "cnpj": "35286331000114",
  "ano": "2026"
}
```

> CNPJ deve ter exatamente 14 dígitos numéricos (sem pontos, traço ou barra).

**Resposta de sucesso (`200`):**
```json
{
  "sucesso": true,
  "job_id": "a1b2c3d4-...",
  "cnpj": "35286331000114",
  "ano": "2026",
  "nome": "PEDRO CARNEIRO MEI",
  "processado_em": "2026-05-27T10:30:00",
  "duracao_segundos": 45.2,
  "resumo": {
    "total_meses": 5,
    "liquidados": 3,
    "devedores": 1,
    "a_vencer": 1,
    "pdfs_gerados": 2,
    "novos_registros": 5,
    "atualizados": 0,
    "duplicados": 0
  },
  "meses": [
    {
      "periodo": "Janeiro/2026",
      "mes": 1,
      "situacao": "Liquidado",
      "principal": 75.90,
      "multa": null,
      "juros": null,
      "total": 75.90,
      "data_vencimento": "2026-01-20",
      "data_acolhimento": "2026-01-15",
      "pdf_disponivel": false,
      "pdf_url": null,
      "novo_registro": true,
      "atualizado": false,
      "pdf_erro": null
    },
    {
      "periodo": "Fevereiro/2026",
      "mes": 2,
      "situacao": "Devedor",
      "principal": 75.90,
      "multa": 7.59,
      "juros": 2.10,
      "total": 85.59,
      "data_vencimento": "2026-02-20",
      "data_acolhimento": null,
      "pdf_disponivel": true,
      "pdf_url": "/das/35286331000114/2026/2/pdf",
      "novo_registro": true,
      "atualizado": false,
      "pdf_erro": null
    }
  ]
}
```

**Resposta de erro (`200` com `sucesso: false`):**
```json
{
  "sucesso": false,
  "job_id": "a1b2c3d4-...",
  "cnpj": "35286331000114",
  "ano": "2026",
  "processado_em": "2026-05-27T10:30:00",
  "erro": {
    "tipo": "CaptchaDetectado",
    "mensagem": "Site bloqueou o acesso por detecção de comportamento de robô",
    "etapa": "login",
    "timestamp": "2026-05-27T10:30:01"
  }
}
```

---

### 2. Listar meses de um CNPJ/ano (do banco)

Retorna os dados já gravados — sem acessar o PGMEI.

```
GET /das/{cnpj}/{ano}
X-API-Key: sua-chave-aqui
```

**Exemplo:** `GET /das/35286331000114/2026`

**Resposta (`200`):**
```json
{
  "cnpj": "35286331000114",
  "ano": "2026",
  "meses": [
    {
      "periodo": "Janeiro/2026",
      "mes": 1,
      "situacao": "Liquidado",
      "principal": 75.90,
      "total": 75.90,
      "data_vencimento": "2026-01-20",
      "data_acolhimento": "2026-01-15",
      "pdf_disponivel": false,
      "pdf_url": null
    }
  ]
}
```

**`404`** — CNPJ/ano ainda não processado.

---

### 3. Download do PDF de um mês

```
GET /das/{cnpj}/{ano}/{mes}/pdf
X-API-Key: sua-chave-aqui
```

**Exemplo:** `GET /das/35286331000114/2026/2/pdf`

Retorna o arquivo PDF com header:
```
Content-Disposition: attachment; filename="DAS_35286331000114_2026_02.pdf"
```

**`404`** — PDF não disponível (mês liquidado ou a vencer fora da janela de geração).

---

### 4. Histórico de jobs

```
GET /das/jobs/lista
X-API-Key: sua-chave-aqui
```

Retorna os últimos 50 processamentos.

**Resposta (`200`):**
```json
[
  {
    "job_id": "a1b2c3d4-...",
    "cnpj": "35286331000114",
    "ano": "2026",
    "nome": "PEDRO CARNEIRO MEI",
    "status": "concluido",
    "iniciado_em": "2026-05-27T10:30:00",
    "finalizado_em": "2026-05-27T10:30:45",
    "duracao_segundos": 45.2,
    "resumo": { "total_meses": 5, "liquidados": 3, "devedores": 1, "..." : "..." }
  }
]
```

---

### 5. Status de um job

```
GET /das/jobs/{job_id}
X-API-Key: sua-chave-aqui
```

**Resposta (`200`):**
```json
{
  "job_id": "a1b2c3d4-...",
  "cnpj": "35286331000114",
  "ano": "2026",
  "nome": "PEDRO CARNEIRO MEI",
  "status": "concluido",
  "iniciado_em": "2026-05-27T10:30:00",
  "finalizado_em": "2026-05-27T10:30:45",
  "duracao_segundos": 45.2,
  "resumo": { "..." : "..." },
  "payload_enviado": { "cnpj": "35286331000114", "ano": "2026" },
  "erro": null
}
```

`status` possíveis: `processando` | `concluido` | `erro`

---

### 6. Health check

```
GET /health
```

Não requer autenticação.

```json
{ "status": "ok", "timestamp": "2026-05-27T13:30:00" }
```

---

## Regras de negócio

| Situação do mês | PDF gerado? |
|---|---|
| **Devedor** | Sempre, independente do mês |
| **A Vencer** — mês atual ou seguinte | Sim |
| **A Vencer** — demais meses futuros | Não |
| **Liquidado** | Não — PDF anterior (se existia) é apagado do banco |

**Controle de duplicados:**
- Mesmo CNPJ/ano/mês sem nenhuma alteração → ignorado (`duplicados` no resumo)
- Situação mudou ou PDF novo disponível → atualizado (`atualizados` no resumo)

---

## Chamadas simultâneas

A API suporta até **15 processamentos simultâneos**. Chamadas de leitura (`GET`) são ilimitadas.

Para evitar que chamadas simultâneas batam no site da Receita Federal ao mesmo tempo, cada scraper aguarda um tempo aleatório de até `DELAY_MAX_S` segundos antes de abrir o browser (padrão: 10s). Isso espalha as 15 chamadas ao longo de 10 segundos automaticamente.

Se precisar ajustar, configure a variável de ambiente:
```
DELAY_MAX_S=10   # recomendado para 15 chamadas simultâneas
DELAY_MAX_S=0    # sem delay (não recomendado em produção)
```

---

## Exemplos de integração

### Python (requests)

```python
import requests

BASE    = "https://<seu-app>.railway.app"
HEADERS = {"X-API-Key": "sua-chave-aqui"}

# Processar CNPJ
resp = requests.post(
    f"{BASE}/das/processar",
    json={"cnpj": "35286331000114", "ano": "2026"},
    headers=HEADERS,
    timeout=180,   # scraper pode levar até 2-3 min
)
dados = resp.json()

if dados["sucesso"]:
    for mes in dados["meses"]:
        print(f"{mes['periodo']:20} {mes['situacao']:10} R$ {mes['total'] or 0:.2f}")
        if mes["pdf_disponivel"]:
            pdf = requests.get(f"{BASE}{mes['pdf_url']}", headers=HEADERS)
            with open(f"DAS_{mes['mes']:02d}.pdf", "wb") as f:
                f.write(pdf.content)
else:
    print("Erro:", dados["erro"]["mensagem"])
```

### Python — múltiplas chamadas simultâneas

```python
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE    = "https://<seu-app>.railway.app"
HEADERS = {"X-API-Key": "sua-chave-aqui"}

cnpjs = [
    ("11222333000181", "2026"),
    ("44555666000172", "2026"),
    ("77888999000163", "2026"),
    # ... até 15
]

def processar(cnpj, ano):
    resp = requests.post(
        f"{BASE}/das/processar",
        json={"cnpj": cnpj, "ano": ano},
        headers=HEADERS,
        timeout=300,
    )
    return cnpj, resp.json()

with ThreadPoolExecutor(max_workers=15) as pool:
    futures = {pool.submit(processar, cnpj, ano): cnpj for cnpj, ano in cnpjs}
    for future in as_completed(futures):
        cnpj, resultado = future.result()
        status = "✓" if resultado["sucesso"] else "✗"
        print(f"{status} {cnpj} — {resultado.get('nome', 'erro')}")
```

### JavaScript / Node.js

```javascript
const BASE    = "https://<seu-app>.railway.app";
const HEADERS = { "Content-Type": "application/json", "X-API-Key": "sua-chave-aqui" };

const resp = await fetch(`${BASE}/das/processar`, {
  method: "POST",
  headers: HEADERS,
  body: JSON.stringify({ cnpj: "35286331000114", ano: "2026" }),
});

const dados = await resp.json();
console.log(dados.resumo);
```

### cURL

```bash
# Processar
curl -X POST https://<seu-app>.railway.app/das/processar \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sua-chave-aqui" \
  -d '{"cnpj":"35286331000114","ano":"2026"}'

# Listar meses do banco
curl https://<seu-app>.railway.app/das/35286331000114/2026 \
  -H "X-API-Key: sua-chave-aqui"

# Baixar PDF do mês 2
curl https://<seu-app>.railway.app/das/35286331000114/2026/2/pdf \
  -H "X-API-Key: sua-chave-aqui" \
  -o DAS_fevereiro.pdf
```

---

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `DATABASE_URL` | URL do PostgreSQL (Railway preenche automaticamente) | SQLite local |
| `HEADLESS` | `true` = sem janela (produção) / `false` = com janela | `false` |
| `PAUSA_MS` | Pausa entre ações do browser (ms) | `1500` |
| `DELAY_MAX_S` | Delay aleatório máximo antes de abrir o browser (s) | `10` |
| `LOGIN_USER` | Usuário do painel web | `admin` |
| `LOGIN_PASS` | Senha do painel web | `admin` |
| `SECRET_KEY` | Chave para assinar cookies de sessão | — |
| `API_KEY` | Chave para autenticação servidor-para-servidor | — |
