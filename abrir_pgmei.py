import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

URL = "https://www8.receita.fazenda.gov.br/SimplesNacional/Aplicacoes/ATSPO/pgmei.app/Identificacao"

async def main():
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized"],
        )
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        await page.goto(URL)

        print("Página aberta. Preencha manualmente.")
        print("Pressione ENTER aqui no terminal para fechar o navegador.")
        await asyncio.get_event_loop().run_in_executor(None, input)

        await browser.close()

asyncio.run(main())
