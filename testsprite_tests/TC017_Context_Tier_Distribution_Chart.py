import asyncio
from playwright import async_api
from playwright.async_api import expect


async def run_test():
    pw = None
    browser = None
    context = None

    try:
        # Start a Playwright session in asynchronous mode
        pw = await async_api.async_playwright().start()

        # Launch a Chromium browser in headless mode with custom arguments
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--window-size=1280,720",  # Set the browser window size
                "--disable-dev-shm-usage",  # Avoid using /dev/shm which can cause issues in containers
                "--ipc=host",  # Use host-level IPC for better stability
                "--single-process",  # Run the browser in a single process mode
            ],
        )

        # Create a new browser context (like an incognito window)
        context = await browser.new_context()
        context.set_default_timeout(5000)

        # Open a new page in the browser context
        page = await context.new_page()

        # Navigate to your target URL and wait until the network request is committed
        await page.goto("http://localhost:3000", wait_until="commit", timeout=10000)

        # Wait for the main page to reach DOMContentLoaded state (optional for stability)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
        except async_api.Error:
            pass

        # Iterate through all iframes and wait for them to load as well
        for frame in page.frames:
            try:
                await frame.wait_for_load_state("domcontentloaded", timeout=3000)
            except async_api.Error:
                pass

        # Interact with the page elements to simulate user flow
        # -> Fill in the project name and description, then click 'Create Project & Start Discovery' button
        frame = context.pages[-1]
        # Input project name
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("context-tier-test")

        frame = context.pages[-1]
        # Input project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name and description, then click 'Create Project & Start Discovery' button
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name with lowercase letters, numbers, hyphens, or underscores only (min 3 chars) and a description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name with lowercase letters, numbers, hyphens, or underscores only (e.g., 'contexttierproject') and a description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name with lowercase letters, numbers, hyphens, or underscores only (e.g., 'contexttierproject') and a description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name with lowercase letters, numbers, hyphens, or underscores only (e.g., 'contexttierproject') and a description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name with lowercase letters, numbers, hyphens, or underscores only (e.g., 'contexttierproject') and a description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input a valid project name with lowercase letters, numbers, hyphens, or underscores only (e.g., 'contexttierproject') and a description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Testing context tier chart display with token counts and percentages.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Clear the project name input and enter a valid project name using only lowercase letters, numbers, hyphens, or underscores (e.g., 'contexttierproject'). Enter a valid description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description with more than 10 characters
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill(
            "This project tests the context tier chart display with token counts and percentages."
        )

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Clear the project name input and enter a valid project name using only lowercase letters, numbers, hyphens, or underscores (e.g., 'contexttierproject'). Enter a valid description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description with more than 10 characters
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill(
            "This project tests the context tier chart display with token counts and percentages."
        )

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Clear the project name input and enter a valid project name using only lowercase letters, numbers, hyphens, or underscores (e.g., 'contexttierproject'). Enter a valid description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description with more than 10 characters
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill(
            "This project tests the context tier chart display with token counts and percentages."
        )

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Clear the project name input and enter a valid project name using only lowercase letters, numbers, hyphens, or underscores (e.g., 'contexttierproject'). Enter a valid description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description with more than 10 characters
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill(
            "This project tests the context tier chart display with token counts and percentages."
        )

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Clear the project name input and enter a valid project name using only lowercase letters, numbers, hyphens, or underscores (e.g., 'contexttierproject'). Enter a valid description with at least 10 characters, then click 'Create Project & Start Discovery' button.
        frame = context.pages[-1]
        # Input valid project name with lowercase letters only
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("contexttierproject")

        frame = context.pages[-1]
        # Input valid project description with more than 10 characters
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill(
            "This project tests the context tier chart display with token counts and percentages."
        )

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # --> Assertions to verify final state
        frame = context.pages[-1]
        try:
            await expect(frame.locator("text=Tier Distribution Overview").first).to_be_visible(
                timeout=1000
            )
        except AssertionError:
            raise AssertionError(
                "Test case failed: The ContextTierChart did not display the expected tier distribution with token counts and percentages as per the test plan."
            )
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()


asyncio.run(run_test())
