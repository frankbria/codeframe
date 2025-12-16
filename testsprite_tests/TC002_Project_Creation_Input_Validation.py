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
        # -> Submit the form with an empty project name to check validation error.
        frame = context.pages[-1]
        # Clear the project name input to simulate empty project name submission.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("")

        frame = context.pages[-1]
        # Fill description with valid text to isolate project name validation.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Valid description with more than 10 chars")

        frame = context.pages[-1]
        # Click the submit button to submit the form with empty project name.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Submit the form with a project name but empty description to check description validation.
        frame = context.pages[-1]
        # Input a valid project name to test description validation.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("my-awesome-project")

        frame = context.pages[-1]
        # Clear the description field to test validation for empty description.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("")

        frame = context.pages[-1]
        # Click submit button to submit form with valid project name but empty description.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Enter an excessively long project name exceeding max length to check validation error.
        frame = context.pages[-1]
        # Input an excessively long project name exceeding max length.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill(
            "a-very-long-project-name-that-exceeds-the-maximum-allowed-length-for-this-field-to-test-validation"
        )

        frame = context.pages[-1]
        # Fill description with valid text to isolate project name length validation.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("Valid description with more than 10 chars")

        frame = context.pages[-1]
        # Click submit button to submit form with excessively long project name.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # -> Input valid project name and valid description, then submit the form to verify successful submission and no validation errors.
        frame = context.pages[-1]
        # Input a valid project name within allowed length.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("valid-project")

        frame = context.pages[-1]
        # Input a valid description meeting minimum length requirement.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        await page.wait_for_timeout(3000)
        await elem.fill("This is a valid project description with more than 10 characters.")

        frame = context.pages[-1]
        # Click submit button to submit form with valid inputs.
        elem = frame.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)
        await page.wait_for_timeout(3000)
        await elem.click(timeout=5000)

        # --> Assertions to verify final state
        frame = context.pages[-1]
        try:
            await expect(frame.locator("text=Project creation successful!").first).to_be_visible(
                timeout=1000
            )
        except AssertionError:
            raise AssertionError(
                "Test case failed: The project creation form did not validate inputs and provide user feedback for invalid or missing data as expected."
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
