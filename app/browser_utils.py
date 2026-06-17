"""
Utilitários compartilhados de browser para todos os scrapers.
"""
import os
import sys
import asyncio
import random
import httpx
from playwright.async_api import Page


BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "")
HEADLESS            = os.getenv("HEADLESS", "false").lower() == "true"
TWOCAPTCHA_KEY      = os.getenv("TWOCAPTCHA_KEY", "")

# No Windows não desabilitamos GPU — WebGL/Canvas reais ajudam a passar o hCaptcha.
# No Linux (Railway/Docker) sem GPU real precisamos dessas flags.
if sys.platform == "win32":
    LAUNCH_ARGS = ["--window-size=1920,1080"]
else:
    LAUNCH_ARGS = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
    ]


async def resolver_hcaptcha(page: Page, sitekey: str, pageurl: str) -> None:
    """
    Resolve o hCaptcha invisível via 2captcha e submete o formulário.
    Exige TWOCAPTCHA_KEY configurado no .env.
    Lança RuntimeError se falhar.
    """
    if not TWOCAPTCHA_KEY:
        raise RuntimeError(
            "hCaptcha invisível detectado. Configure TWOCAPTCHA_KEY no .env "
            "para resolver automaticamente."
        )

    # 1. Envia tarefa para o 2captcha
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post("https://2captcha.com/in.php", data={
            "key":     TWOCAPTCHA_KEY,
            "method":  "hcaptcha",
            "sitekey": sitekey,
            "pageurl": pageurl,
        })
        resp.raise_for_status()
        if not resp.text.startswith("OK|"):
            raise RuntimeError(f"2captcha recusou a tarefa: {resp.text}")
        task_id = resp.text.split("|")[1]

    # 2. Aguarda resolução — poll a cada 5s, timeout 120s
    token = None
    async with httpx.AsyncClient(timeout=15) as client:
        for _ in range(24):
            await asyncio.sleep(5)
            resp = await client.get("https://2captcha.com/res.php", params={
                "key":    TWOCAPTCHA_KEY,
                "action": "get",
                "id":     task_id,
            })
            if resp.text == "CAPCHA_NOT_READY":
                continue
            if resp.text.startswith("OK|"):
                token = resp.text.split("|")[1]
                break
            raise RuntimeError(f"2captcha erro: {resp.text}")

    if not token:
        raise RuntimeError("2captcha timeout: captcha não resolvido em 120s")

    # 3. Injeta o token e submete o formulário
    await page.evaluate(f"""
        (() => {{
            const ta = document.querySelector('textarea[name="h-captcha-response"]');
            if (ta) ta.value = {repr(token)};
            const form = document.querySelector('#identificacao');
            if (form) form.submit();
        }})();
    """)


async def simular_humano(page: Page) -> None:
    """Movimentos de mouse e scroll aleatórios para parecer humano."""
    for _ in range(random.randint(2, 4)):
        await page.mouse.move(
            random.randint(100, 1400),
            random.randint(100, 700),
        )
        await page.wait_for_timeout(random.randint(80, 250))
    await page.evaluate(f"window.scrollBy(0, {random.randint(40, 120)})")
    await page.wait_for_timeout(random.randint(300, 600))
    await page.evaluate("window.scrollBy(0, 0)")
    await page.wait_for_timeout(random.randint(200, 400))


async def digitar_cnpj(page: Page, selector: str, cnpj: str) -> None:
    """Clica e digita o CNPJ caractere a caractere com delay variável."""
    campo = page.locator(selector)
    box = await campo.bounding_box()
    if box:
        await page.mouse.move(
            box["x"] + box["width"] / 2 + random.randint(-10, 10),
            box["y"] + box["height"] / 2 + random.randint(-5, 5),
        )
        await page.wait_for_timeout(random.randint(150, 350))
    await campo.click()
    await page.wait_for_timeout(random.randint(300, 600))
    # Seleciona tudo para garantir que digita do início, independente do cursor
    await campo.press("Control+a")
    await page.wait_for_timeout(random.randint(200, 400))
    await campo.press_sequentially(cnpj, delay=random.randint(90, 170))
    await page.wait_for_timeout(random.randint(800, 1600))
