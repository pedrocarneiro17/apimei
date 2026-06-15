"""
Utilitários compartilhados de browser para todos os scrapers.
"""
import os
import random
from playwright.async_api import Page


# Diretório de perfil persistente — acumula cookies/histórico entre execuções.
# Ajuda o hCaptcha a reconhecer o browser como usuário recorrente.
# Configure BROWSER_PROFILE_DIR no .env para uso local.
# Em produção (Railway + Xvfb), deixe em branco — temp dir é suficiente.
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "")

HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1920,1080",
]


async def simular_humano(page: Page) -> None:
    """
    Movimentos de mouse e scroll aleatórios antes de interagir com o formulário.
    Reduz a probabilidade de detecção por hCaptcha.
    """
    # Movimentos de mouse em arco natural
    for _ in range(random.randint(2, 4)):
        await page.mouse.move(
            random.randint(100, 1400),
            random.randint(100, 700),
        )
        await page.wait_for_timeout(random.randint(80, 250))

    # Scroll suave (simula leitura da página)
    await page.evaluate(f"window.scrollBy(0, {random.randint(40, 120)})")
    await page.wait_for_timeout(random.randint(300, 600))
    await page.evaluate("window.scrollBy(0, 0)")
    await page.wait_for_timeout(random.randint(200, 400))


async def digitar_cnpj(page: Page, selector: str, cnpj: str) -> None:
    """
    Clica no campo e digita o CNPJ caractere a caractere com delay variável.
    """
    campo = page.locator(selector)
    # Move o mouse até o campo antes de clicar
    box = await campo.bounding_box()
    if box:
        await page.mouse.move(
            box["x"] + box["width"] / 2 + random.randint(-10, 10),
            box["y"] + box["height"] / 2 + random.randint(-5, 5),
        )
        await page.wait_for_timeout(random.randint(150, 350))
    await campo.click()
    await page.wait_for_timeout(random.randint(400, 800))
    await campo.press_sequentially(cnpj, delay=random.randint(90, 170))
    await page.wait_for_timeout(random.randint(800, 1600))
