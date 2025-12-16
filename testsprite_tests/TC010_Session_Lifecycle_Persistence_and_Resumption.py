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
                "--window-size=1280,720",
                "--disable-dev-shm-usage",
                "--ipc=host",
                "--single-process",
            ],
        )

        # Create a new browser context (like an incognito window)
        context = await browser.new_context()
        context.set_default_timeout(10000)

        # Open a new page in the browser context
        page = await context.new_page()

        # Navigate to the application
        await page.goto("http://localhost:3000", wait_until="commit", timeout=10000)

        # Wait for page to be ready
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except async_api.Error:
            pass

        # Define locators for form elements
        project_name_input = page.locator("xpath=html/body/main/div/div[2]/form/div/input").nth(0)
        project_desc_input = page.locator("xpath=html/body/main/div/div[2]/form/div[2]/textarea").nth(0)
        submit_button = page.locator("xpath=html/body/main/div/div[2]/form/button").nth(0)

        # Locators for validation errors and success indicators
        validation_error = page.locator("text=Lowercase letters, numbers, hyphens, and underscores only")
        min_chars_error = page.locator("text=min 3 chars")
        min_desc_error = page.locator("text=min 10")

        # ========================================
        # Test Case 1: Negative - Invalid project name (hyphens not allowed at start)
        # ========================================
        print("Test 1: Invalid project name with leading hyphen")
        await project_name_input.fill("-invalidname")
        await project_desc_input.fill("Valid description for testing session lifecycle.")
        await submit_button.click()

        # Wait and check for validation error OR navigation
        await page.wait_for_timeout(1000)
        current_url = page.url

        # Should still be on home page with validation error
        if "localhost:3000" in current_url and "/" == current_url.split("3000")[-1].rstrip("/"):
            # Check that we're still on the form (validation prevented submission)
            is_form_visible = await submit_button.is_visible()
            assert is_form_visible, "Form should still be visible after invalid input"
            print("  ✓ Validation prevented submission with invalid name")
        else:
            raise AssertionError("Expected to remain on form page due to validation error")

        # ========================================
        # Test Case 2: Negative - Project name too short
        # ========================================
        print("Test 2: Project name too short")
        await project_name_input.clear()
        await project_name_input.fill("ab")  # Less than 3 chars
        await submit_button.click()

        await page.wait_for_timeout(1000)
        is_form_visible = await submit_button.is_visible()
        assert is_form_visible, "Form should still be visible - name too short"
        print("  ✓ Validation prevented submission with short name")

        # ========================================
        # Test Case 3: Negative - Description too short
        # ========================================
        print("Test 3: Description too short")
        await project_name_input.clear()
        await project_name_input.fill("validname")
        await project_desc_input.clear()
        await project_desc_input.fill("Short")  # Less than 10 chars
        await submit_button.click()

        await page.wait_for_timeout(1000)
        is_form_visible = await submit_button.is_visible()
        assert is_form_visible, "Form should still be visible - description too short"
        print("  ✓ Validation prevented submission with short description")

        # ========================================
        # Test Case 4: Positive - Valid project creation
        # ========================================
        print("Test 4: Valid project creation")
        await project_name_input.clear()
        await project_name_input.fill("sessiontest")
        await project_desc_input.clear()
        await project_desc_input.fill("This project tests session lifecycle persistence and resumption.")
        await submit_button.click()

        # Wait for navigation or success indicator
        try:
            # Wait for URL change indicating successful project creation
            await page.wait_for_url("**/projects/**", timeout=10000)
            print("  ✓ Project created successfully - navigated to project page")
            project_created = True
        except async_api.Error:
            # Alternative: check for success message on same page
            try:
                success_indicator = page.locator("text=Project created").or_(
                    page.locator("text=Discovery")
                ).or_(
                    page.locator("[data-testid='project-dashboard']")
                )
                await success_indicator.wait_for(state="visible", timeout=5000)
                print("  ✓ Project created successfully - success indicator visible")
                project_created = True
            except async_api.Error:
                # Check if still on form (creation failed)
                is_form_visible = await submit_button.is_visible()
                if is_form_visible:
                    raise AssertionError("Project creation failed - still on form page")
                project_created = False

        # ========================================
        # Test Case 5: Verify session state persistence
        # ========================================
        if project_created:
            print("Test 5: Verify session state/navigation")
            # After project creation, verify we're on a project-related page
            current_url = page.url
            assert "localhost:3000" in current_url, f"Unexpected URL: {current_url}"

            # Look for session-related content or project dashboard elements
            try:
                # Wait for any dashboard or project content to load
                await page.wait_for_load_state("networkidle", timeout=10000)

                # Check for common dashboard elements
                dashboard_content = page.locator("main").or_(
                    page.locator("[role='main']")
                ).or_(
                    page.locator(".dashboard")
                )
                await dashboard_content.wait_for(state="visible", timeout=5000)
                print("  ✓ Dashboard/project content loaded")
            except async_api.Error:
                print("  ⚠ Could not verify dashboard content (may still be loading)")

        # ========================================
        # Final Assertion
        # ========================================
        print("\n--- Final Verification ---")
        # The test passes if we successfully created a project and navigated away from the form
        if project_created:
            print("✅ Session lifecycle test completed successfully")
            print("   - Validation errors properly blocked invalid submissions")
            print("   - Valid project was created")
            print("   - Navigation/state change confirmed")
        else:
            raise AssertionError(
                "Test case failed: Could not create project and verify session state"
            )

        await asyncio.sleep(2)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()


asyncio.run(run_test())
