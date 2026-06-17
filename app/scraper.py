"""
Scraper PGMEI — automatiza a Receita Federal para coletar situação dos DAS.
"""
import os
import random
import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

URL_BASE      = "https://www8.receita.fazenda.gov.br/SimplesNacional/Aplicacoes/ATSPO/pgmei.app"
HEADLESS      = os.getenv("HEADLESS", "false").lower() == "true"
PAUSA_MS      = int(os.getenv("PAUSA_MS", "1500"))
# Delay aleatório máximo antes de abrir o browser (evita burst de requisições simultâneas)
DELAY_MAX_S   = int(os.getenv("DELAY_MAX_S", "10"))


def _agora() -> datetime:
    """Retorna datetime atual no horário de Brasília (UTC-3)."""
    return datetime.utcnow() - timedelta(hours=3)

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


class ScraperError(Exception):
    def __init__(self, tipo: str, mensagem: str, etapa: str):
        self.tipo = tipo
        self.mensagem = mensagem
        self.etapa = etapa
        super().__init__(mensagem)


# ── Entrada principal ────────────────────────────────────────────────────────

async def processar_das(cnpj: str, ano: str, meses_com_pdf: set | None = None) -> dict:
    """
    Processa o PGMEI para CNPJ/ano e retorna dados de todos os meses.
    PDFs são gerados individualmente para: Devedor, mês atual e mês seguinte.
    """
    # Spread aleatório: evita que chamadas simultâneas batam no site ao mesmo tempo
    if DELAY_MAX_S > 0:
        await asyncio.sleep(random.uniform(0, DELAY_MAX_S))

    meses_com_pdf = meses_com_pdf or set()
    inicio = _agora()
    resultado = {
        "cnpj": cnpj, "ano": ano, "nome": None,
        "sucesso": False, "erro": None,
        "meses": [], "inicio": inicio.isoformat(),
    }

    ano_int = int(ano)
    etapa   = "inicializacao"

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1920,1080",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )
        page = await context.new_page()

        try:
            # ── 1. Login ─────────────────────────────────────────────
            etapa = "login"
            await page.goto(f"{URL_BASE}/Identificacao")
            await page.wait_for_timeout(PAUSA_MS)
            await page.locator('input[type="text"]').fill(cnpj)
            await page.wait_for_timeout(800)
            await page.locator('button[type="submit"]').click()

            try:
                await page.wait_for_url("**/Inicio", timeout=25000)
            except Exception:
                html = await page.content()
                if any(w in html.lower() for w in ["captcha", "robô", "robot"]):
                    raise ScraperError(
                        "CaptchaDetectado",
                        "Site bloqueou o acesso por detecção de comportamento de robô",
                        etapa,
                    )
                raise ScraperError(
                    "TimeoutLogin",
                    "Timeout aguardando página inicial após inserir o CNPJ",
                    etapa,
                )

            # Extrai nome do MEI — tenta vários seletores possíveis
            etapa = "extrair_nome"
            try:
                seletores = [
                    "p.cabecalho-informacoes",
                    ".cabecalho-informacoes",
                    ".row .col-md-12",
                    "p:has-text('Nome:')",
                    "div:has-text('Nome:')",
                ]
                for seletor in seletores:
                    try:
                        loc = page.locator(seletor).first
                        info = await loc.inner_text(timeout=500)
                        if "Nome:" in info:
                            resultado["nome"] = info.split("Nome:")[-1].split("\n")[0].strip()
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # ── 2. Navega para Emitir DAS ────────────────────────────
            etapa = "navegar_emissao"
            emitir_btn = page.get_by_text("Emitir Guia de Pagamento (DAS)")
            await emitir_btn.wait_for(state="visible", timeout=10000)
            await emitir_btn.click()
            await page.wait_for_url("**/emissao", timeout=15000)
            await page.wait_for_selector("table tbody tr, button.dropdown-toggle", timeout=15000)

            # ── 3. Seleciona o ano ───────────────────────────────────
            etapa = "selecionar_ano"
            await _selecionar_ano(page, ano)

            # ── 4. Lê a tabela ───────────────────────────────────────
            etapa = "ler_tabela"
            await page.wait_for_selector("table tbody tr", timeout=20000)
            await page.wait_for_timeout(PAUSA_MS)
            dados_meses = await _ler_tabela(page, ano_int, meses_com_pdf)

            # ── 5. Gera PDFs mês a mês ───────────────────────────────
            etapa = "gerar_pdfs"
            for mes_data in dados_meses:
                if not mes_data["precisa_pdf"]:
                    continue
                try:
                    pdf = await _gerar_pdf_mes(page, context, mes_data["periodo"], ano)
                    mes_data["pdf"] = pdf
                    mes_data["pdf_gerado_em"] = _agora().isoformat()
                    if not pdf:
                        mes_data["pdf_erro"] = "PDF não capturado (resposta vazia)"
                except Exception as exc:
                    mes_data["pdf_erro"] = f"{type(exc).__name__}: {exc}"

            fim = _agora()
            resultado.update({
                "sucesso": True,
                "meses": dados_meses,
                "fim": fim.isoformat(),
                "duracao_segundos": round((fim - inicio).total_seconds(), 2),
            })

        except ScraperError as exc:
            resultado["erro"] = {
                "tipo": exc.tipo, "mensagem": exc.mensagem,
                "etapa": exc.etapa, "timestamp": _agora().isoformat(),
            }
        except Exception as exc:
            resultado["erro"] = {
                "tipo": type(exc).__name__, "mensagem": str(exc),
                "etapa": etapa, "timestamp": _agora().isoformat(),
            }
        finally:
            await browser.close()

    return resultado


# ── Helpers internos ─────────────────────────────────────────────────────────

async def _selecionar_ano(page: Page, ano: str) -> None:
    dropdown = page.locator("button.dropdown-toggle").first
    await dropdown.wait_for(state="visible", timeout=8000)
    await dropdown.click()
    opcao = page.locator(".dropdown-menu li").filter(has_text=ano).first
    await opcao.wait_for(state="visible", timeout=8000)
    await opcao.click()
    submit = page.locator("button[type='submit']")
    await submit.wait_for(state="visible", timeout=5000)
    await submit.click()


async def _ler_tabela(page: Page, ano_int: int, meses_com_pdf: set) -> list[dict]:
    rows = await page.locator("table tbody tr").all()
    dados = []

    for row in rows:
        tds = await row.locator("td").all_inner_texts()
        if len(tds) < 5:
            continue

        periodo  = tds[1].strip()
        situacao = tds[4].strip()
        nome_mes = periodo.split("/")[0].strip().lower()
        mes_num  = MESES_PT.get(nome_mes, 0)

        precisa_pdf = _determinar_pdf(situacao, mes_num, meses_com_pdf)

        dados.append({
            "periodo":          periodo,
            "mes":              mes_num,
            "situacao":         situacao,
            "principal":        _parse_brl(tds[5] if len(tds) > 5 else ""),
            "multa":            _parse_brl(tds[6] if len(tds) > 6 else ""),
            "juros":            _parse_brl(tds[7] if len(tds) > 7 else ""),
            "total":            _parse_brl(tds[8] if len(tds) > 8 else ""),
            "data_vencimento":  _parse_date(tds[9]  if len(tds) > 9  else ""),
            "data_acolhimento": _parse_date(tds[10] if len(tds) > 10 else ""),
            "precisa_pdf":      precisa_pdf,
            "pdf":              None,
            "pdf_erro":         None,
            "pdf_gerado_em":    None,
        })

    return dados


def _determinar_pdf(situacao: str, mes_num: int, meses_com_pdf: set) -> bool:
    """
    Regras de geração de PDF:
      Devedor   → sempre gera PDF novo (juros acumulam todo dia)
      A Vencer  → gera só se ainda não tem PDF no banco
      Liquidado → não gera
    """
    if "Devedor" in situacao:
        return True
    if "A Vencer" in situacao:
        return mes_num not in meses_com_pdf
    return False


async def _gerar_pdf_mes(page: Page, context: BrowserContext,
                          periodo: str, ano: str) -> bytes | None:
    """Volta à tabela, seleciona só o mês desejado e captura o PDF via interceptor."""

    # Volta à página de emissão
    await page.goto(f"{URL_BASE}/emissao")
    await page.wait_for_selector("button.dropdown-toggle", timeout=15000)
    await _selecionar_ano(page, ano)
    await page.wait_for_selector("table tbody tr", timeout=20000)

    # Marca só o checkbox do período desejado
    rows = await page.locator("table tbody tr").all()
    for row in rows:
        tds = await row.locator("td").all_inner_texts()
        if len(tds) >= 2 and tds[1].strip() == periodo:
            await row.locator("td:first-child input[type='checkbox']").check()
            await page.wait_for_timeout(300)
            break

    # Intercepta a resposta PDF
    pdf_capturado: dict[str, bytes] = {}

    async def interceptar(route, request):
        response = await route.fetch()
        corpo    = await response.body()
        if corpo[:4] == b"%PDF":
            pdf_capturado["bytes"] = corpo
        await route.fulfill(response=response)

    await context.route("**/emissao/imprimir**", interceptar)

    apurar_btn = page.get_by_text("Apurar/Gerar DAS")
    await apurar_btn.wait_for(state="visible", timeout=10000)
    await apurar_btn.click()
    await page.wait_for_url("**/gerarDas", timeout=25000)

    try:
        async with context.expect_page(timeout=10000) as popup_info:
            await page.get_by_text("Imprimir/Visualizar PDF").click()
        pdf_page = await popup_info.value
        await pdf_page.wait_for_load_state("load", timeout=20000)
    except Exception:
        await page.get_by_text("Imprimir/Visualizar PDF").click()
        await page.wait_for_timeout(3000)

    await context.unroute("**/emissao/imprimir**")
    return pdf_capturado.get("bytes")


# ── Utilitários ──────────────────────────────────────────────────────────────

def _parse_brl(valor: str) -> float | None:
    v = (valor or "").replace("R$", "").replace(".", "").replace(",", ".").strip()
    if not v or v == "-":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_date(data: str) -> str | None:
    d = (data or "").strip()
    if not d or d == "-":
        return None
    try:
        dia, mes, ano = d.split("/")
        return f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"
    except Exception:
        return None
