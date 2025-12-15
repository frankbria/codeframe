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
        # -> Fill in the project description to meet minimum requirements and create the project to navigate to the dashboard.
        frame = context.pages[-1]
        # Fill in the project description to meet minimum 10 characters requirement.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("This project is for testing task tree with issues and nested tasks.")

        frame = context.pages[-1]
        # Click the 'Create Project & Start Discovery' button to create the project and navigate to dashboard.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Correct the project name to a valid format and create the project to navigate to the dashboard.
        frame = context.pages[-1]
        # Correct the project name to a valid format without hyphens or underscores.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("myawesomeproject")

        frame = context.pages[-1]
        # Click the 'Create Project & Start Discovery' button to create the project and navigate to dashboard.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Correct the project name to only lowercase letters, numbers, underscores (no hyphens), and fill the description with at least 10 characters, then create the project.
        frame = context.pages[-1]
        # Correct the project name to valid format without hyphens.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("myawesomeproject")

        frame = context.pages[-1]
        # Fill the description with at least 10 characters.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("This project is for testing task tree with issues and nested tasks.")

        frame = context.pages[-1]
        # Click the 'Create Project & Start Discovery' button to create the project and navigate to dashboard.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Correct the project name to a valid format without hyphens and submit the form to create the project and navigate to the dashboard.
        frame = context.pages[-1]
        # Correct the project name to a valid format without hyphens.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("myawesomeproject")

        frame = context.pages[-1]
        # Click the 'Create Project & Start Discovery' button to create the project and navigate to the dashboard.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # --> Assertions to verify final state
        frame = context.pages[-1]
        try:
            await expect(
                frame.locator("text=All Tasks Completed Successfully").first
            ).to_be_visible(timeout=1000)
        except AssertionError:
            raise AssertionError(
                "Test plan execution failed: Issues and nested tasks are not displayed correctly in the task tree with collapsible views and status badges."
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
