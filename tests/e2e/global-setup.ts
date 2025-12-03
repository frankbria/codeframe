/**
 * Global setup for Playwright E2E tests.
 * Creates a test project before running tests.
 */
import { chromium, FullConfig } from '@playwright/test';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';

async function globalSetup(config: FullConfig) {
  console.log('🔧 Setting up E2E test environment...');

  // Launch browser for API calls
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Try to get existing projects first
    const projectsResponse = await page.request.get(`${BACKEND_URL}/api/projects`);
    if (projectsResponse.ok()) {
      const data = await projectsResponse.json();
      const projects = data.projects || [];

      if (projects.length > 0) {
        // Use first existing project
        console.log(`✅ Using existing project ID: ${projects[0].id}`);
        process.env.E2E_TEST_PROJECT_ID = projects[0].id.toString();
      } else {
        // No projects exist, create one
        console.log('📦 Creating test project...');
        const createResponse = await page.request.post(`${BACKEND_URL}/api/projects`, {
          data: {
            name: 'e2e-test-project',
            description: 'Test project for Playwright E2E tests'
          }
        });

        if (!createResponse.ok()) {
          throw new Error(`Failed to create project: ${createResponse.statusText()}`);
        }

        const project = await createResponse.json();
        console.log(`✅ Test project created with ID: ${project.id}`);
        process.env.E2E_TEST_PROJECT_ID = project.id.toString();
      }
    } else {
      throw new Error(`Failed to fetch projects: ${projectsResponse.statusText()}`);
    }
  } catch (error) {
    console.error('❌ Failed to set up test environment:', error);
    throw error;
  } finally {
    await context.close();
    await browser.close();
  }

  console.log('✅ E2E test environment ready!');
}

export default globalSetup;
