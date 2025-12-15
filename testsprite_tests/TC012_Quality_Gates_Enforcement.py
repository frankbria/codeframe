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
        # -> Fill in the project description to meet minimum requirements and create the project.
        frame = context.pages[-1]
        # Input project description to meet minimum 10 characters requirement.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("This project will test quality gates for task completion.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button to create the project and proceed.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Fix project name to a valid format and create the project.
        frame = context.pages[-1]
        # Fix project name to valid format with underscores instead of hyphens.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("my_awesome_project")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button to create the project with valid project name.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Fix project name to valid format and input a description with at least 10 characters, then create the project.
        frame = context.pages[-1]
        # Fix project name to valid format with underscores instead of hyphens.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("my_awesome_project")

        frame = context.pages[-1]
        # Input valid project description with more than 10 characters.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("This project will test quality gates for task completion.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button to create the project with valid inputs.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Try a simpler project name without hyphens or underscores, e.g., 'myawesomeproject', and input a valid description to enable project creation.
        frame = context.pages[-1]
        # Input simpler project name without hyphens or underscores to pass validation.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("myawesomeproject")

        frame = context.pages[-1]
        # Input valid project description with at least 10 characters.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("This project will test quality gates for task completion.")

        frame = context.pages[-1]
        # Click 'Create Project & Start Discovery' button to create the project with valid inputs.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # --> Assertions to verify final state
        frame = context.pages[-1]
        try:
            await expect(
                frame.locator("text=All Quality Gates Passed Successfully").first
            ).to_be_visible(timeout=1000)
        except AssertionError:
            raise AssertionError(
                "Test failed: Task was marked complete despite failing quality gates. Quality gates must pass before task completion."
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
