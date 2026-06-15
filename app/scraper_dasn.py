"""
Scraper DASN SIMEI — consulta a situação das declarações anuais do MEI.
"""
import os
import re
import random
import asyncio
from datetime import datetime, timedelta

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

URL_DASN   = "https://www8.receita.fazenda.gov.br/SimplesNacional/Aplicacoes/ATSPO/dasnsimei.app/Identificacao"
HEADLESS   = os.getenv("HEADLESS", "false").lower() == "true"
PAUSA_MS   = int(os.getenv("PAUSA_MS", "1500"))
DELAY_MAX_S = int(os.getenv("DELAY_MAX_S", "10"))


def _agora() -> datetime:
    return datetime.utcnow() - timedelta(hours=3)


class ScraperDASNError(Exception):
    def __init__(self, tipo: str, mensagem: str, etapa: str):
        self.tipo = tipo
        self.mensagem = mensagem
        self.etapa = etapa
        super().__init__(mensagem)


async def consultar_dasn(cnpj: str) -> dict:
    """
    Acessa o DASN SIMEI, entra com o CNPJ e retorna a lista de anos
    com o status de cada declaração.
    """
    if DELAY_MAX_S > 0:
        await asyncio.sleep(random.uniform(0, DELAY_MAX_S))

    inicio = _agora()
    resultado: dict = {
        "cnpj": cnpj,
        "sucesso": False,
        "erro": None,
        "anos": [],
        "consultado_em": inicio.isoformat(),
    }
    etapa = "inicializacao"

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
            accept_downloads=False,
        )
        page = await context.new_page()

        try:
            # ── 1. Navegação e CNPJ ──────────────────────────────────
            etapa = "login"
            await page.goto(URL_DASN)
            await page.wait_for_timeout(PAUSA_MS)

            # IDs confirmados via inspeção: #identificacao-cnpj / #identificacao-continuar
            await page.locator("#identificacao-cnpj").fill(cnpj)
            await page.wait_for_timeout(800)
            await page.locator("#identificacao-continuar").click()

            # Aguarda saída da página de identificação (o POST redireciona para /Inicio ou similar)
            try:
                await page.wait_for_function(
                    "() => !window.location.href.includes('Identificacao')",
                    timeout=25000,
                )
                await page.wait_for_timeout(PAUSA_MS)
            except ScraperDASNError:
                raise
            except Exception as exc:
                html = await page.content()
                if any(w in html.lower() for w in ["captcha", "robô", "robot"]):
                    raise ScraperDASNError(
                        "CaptchaDetectado",
                        "Site bloqueou o acesso por detecção de comportamento de robô",
                        etapa,
                    )
                raise ScraperDASNError(
                    "TimeoutLogin",
                    f"Timeout aguardando página após inserir CNPJ: {exc}",
                    etapa,
                )

            # ── 2. Abre o seletor de ano calendário (componente BRDS) ──
            # Trigger confirmado via inspeção: button[data-trigger="data-trigger"]
            # Lista: .br-list  |  Itens: .br-item com input[name="opcao"] (radio)
            etapa = "ler_anos"
            try:
                await page.wait_for_selector(
                    'button[data-trigger="data-trigger"]', timeout=15000
                )
                await page.locator('button[data-trigger="data-trigger"]').first.click()
                await page.wait_for_timeout(1000)
                await page.wait_for_selector(".br-list .br-item", timeout=5000)
            except ScraperDASNError:
                raise
            except Exception as exc:
                raise ScraperDASNError(
                    "DropdownNaoEncontrado",
                    f"Seletor de ano calendário não encontrado: {exc}",
                    etapa,
                )

            # ── 3. Lê os radio buttons do .br-list ───────────────────
            # Estrutura: input[value=ano, data-tipo-declaracao] + span "apresentada em DD/MM/YYYY"
            radios = await page.locator('input[name="opcao"]').all()
            anos: list[dict] = []

            for radio in radios:
                try:
                    ano = await radio.get_attribute("value")
                    tipo_declaracao = await radio.get_attribute("data-tipo-declaracao") or ""
                    if not ano or not re.match(r"^20\d{2}$", ano):
                        continue

                    # Sobe para o div.br-radio e lê o span com a data
                    br_radio = radio.locator("xpath=ancestor::div[contains(@class,'br-radio')]")
                    spans = await br_radio.locator("span:not(.br-tag)").all()
                    data_apresentacao = None
                    for span in spans:
                        t = (await span.inner_text()).strip()
                        match_data = re.search(
                            r"apresentada\s+em\s+(\d{2}/\d{2}/\d{4})", t, re.IGNORECASE
                        )
                        if match_data:
                            data_apresentacao = match_data.group(1)
                            break

                    # "Retificadora" = já apresentada e pode retificar
                    # "Original" = ainda não apresentada (primeira entrega)
                    if data_apresentacao:
                        status = "Apresentada"
                    elif tipo_declaracao.lower() == "original":
                        status = "Não Apresentada"
                    else:
                        status = "Apresentada" if tipo_declaracao else "Não Apresentada"

                    anos.append({
                        "ano": ano,
                        "status": status,
                        "data_apresentacao": data_apresentacao,
                    })
                except Exception:
                    continue

            if not anos:
                raise ScraperDASNError(
                    "SemAnos",
                    "Nenhum ano calendário encontrado no dropdown",
                    etapa,
                )

            fim = _agora()
            resultado.update({
                "sucesso": True,
                "anos": anos,
                "consultado_em": fim.isoformat(),
                "duracao_segundos": round((fim - inicio).total_seconds(), 2),
            })

        except ScraperDASNError as exc:
            resultado["erro"] = {
                "tipo": exc.tipo,
                "mensagem": exc.mensagem,
                "etapa": exc.etapa,
                "timestamp": _agora().isoformat(),
            }
        except Exception as exc:
            resultado["erro"] = {
                "tipo": type(exc).__name__,
                "mensagem": str(exc),
                "etapa": etapa,
                "timestamp": _agora().isoformat(),
            }
        finally:
            await browser.close()

    return resultado
