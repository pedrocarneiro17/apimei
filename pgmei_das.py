import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ── configurações ──────────────────────────────────────────────
CNPJ = "35286331000114"
ANO  = "2026"
URL  = "https://www8.receita.fazenda.gov.br/SimplesNacional/Aplicacoes/ATSPO/pgmei.app/Identificacao"
PAUSA = 1500  # ms entre cada passo (aumente se o site estiver lento)
# ───────────────────────────────────────────────────────────────


async def espera(page, ms=None):
    await page.wait_for_timeout(ms or PAUSA)


async def main():
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized"],
        )
        context = await browser.new_context(
            no_viewport=True,
            accept_downloads=True,
        )
        page = await context.new_page()

        # ── 1. preenche CNPJ ──────────────────────────────────
        print(f"\nAbrindo PGMEI — CNPJ {CNPJ} ...")
        await page.goto(URL)
        await espera(page)
        await page.locator('input[type="text"]').fill(CNPJ)
        await espera(page, 800)
        await page.locator('button[type="submit"]').click()

        # ── 2. clica em Emitir Guia de Pagamento (DAS) ────────
        print("Aguardando página inicial...")
        await page.wait_for_url("**/Inicio", timeout=25000)
        await espera(page)
        print("Clicando em Emitir Guia de Pagamento (DAS)...")
        await page.get_by_text("Emitir Guia de Pagamento (DAS)").click()

        # ── 3. seleciona o ano e clica Ok ─────────────────────
        print("Aguardando tela de seleção de ano...")
        await page.wait_for_url("**/emissao", timeout=15000)
        await espera(page)

        print(f"Selecionando ano {ANO}...")
        await page.locator("button.dropdown-toggle").first.click()
        await espera(page, 1500)

        # aguarda algum li do dropdown ficar visível e clica no ano correto
        opcao = page.locator(".dropdown-menu li").filter(has_text=ANO).first
        await opcao.wait_for(state="visible", timeout=8000)
        await opcao.click()
        await espera(page, 800)
        await page.locator("button[type='submit']").click()

        # ── 4. lê a tabela e identifica situações ─────────────
        print("Aguardando tabela de períodos...")
        await page.wait_for_selector("table tbody tr", timeout=20000)
        await espera(page)
        rows = await page.locator("table tbody tr").all()

        print(f"\n{'─'*50}")
        print(f"  {'Período':<20} {'Situação':<15} Total")
        print(f"{'─'*50}")

        tem_devedor = False

        for row in rows:
            tds = await row.locator("td").all_inner_texts()
            if len(tds) < 5:
                continue

            periodo  = tds[1].strip()
            situacao = tds[4].strip()
            total    = tds[8].strip() if len(tds) > 8 else "-"

            if "Liquidado" in situacao:
                print(f"  ✅ {periodo:<20} {'Liquidado':<15} (pago)")

            elif "Devedor" in situacao:
                print(f"  ❌ {periodo:<20} {'Devedor':<15} {total}")
                checkbox = row.locator("td:first-child input[type='checkbox']")
                await checkbox.check()
                await espera(page, 300)
                tem_devedor = True

            else:
                print(f"  ⏳ {periodo:<20} {situacao}")

        print(f"{'─'*50}")

        if not tem_devedor:
            print("\nNenhum período devedor encontrado. Encerrando.")
            await browser.close()
            return

        # ── 5. gera DAS ───────────────────────────────────────
        print("\nGerando DAS para períodos devedores...")
        await espera(page)
        await page.get_by_text("Apurar/Gerar DAS").click()
        await page.wait_for_url("**/gerarDas", timeout=25000)
        await espera(page)

        # ── 6. baixa o PDF ────────────────────────────────────
        print("Baixando PDF...")

        pdf_capturado = {}

        async def interceptar_pdf(route, request):
            """Intercepta a resposta do PDF e salva os bytes."""
            response = await route.fetch()
            corpo = await response.body()
            content_type = response.headers.get("content-type", "")
            if "pdf" in content_type or corpo[:4] == b"%PDF":
                pdf_capturado["bytes"] = corpo
            await route.fulfill(response=response)

        # registra interceptor para a rota de impressão
        await context.route("**/emissao/imprimir**", interceptar_pdf)

        try:
            async with context.expect_page(timeout=10000) as popup_info:
                await page.get_by_text("Imprimir/Visualizar PDF").click()
            pdf_page = await popup_info.value
            await pdf_page.wait_for_load_state("load", timeout=20000)
        except Exception:
            await page.get_by_text("Imprimir/Visualizar PDF").click()
            await espera(page, 3000)

        # salva o PDF capturado
        if pdf_capturado.get("bytes"):
            destino = Path.home() / "Downloads" / f"DAS_{CNPJ}_{ANO}.pdf"
            destino.write_bytes(pdf_capturado["bytes"])
            print(f"✅ PDF salvo em: {destino}")
        else:
            print("⚠️  PDF não capturado — verifique se a nova aba abriu corretamente.")

        print("\n✅ Fluxo concluído!")
        print("Pressione ENTER para fechar o navegador...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        await browser.close()


asyncio.run(main())
