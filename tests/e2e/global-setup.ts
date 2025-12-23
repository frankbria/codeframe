/**
 * Global setup for Playwright E2E tests.
 * Creates a test project and seeds comprehensive test data before running tests.
 */
import { chromium, FullConfig } from '@playwright/test';
import { spawnSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { TEST_DB_PATH, BACKEND_URL } from './e2e-config';

/**
 * Clean up test environment to ensure fresh state.
 * Only removes workspaces directory to avoid "workspace already exists" errors.
 * Note: Database is NOT deleted because the backend server starts before globalSetup
 * and deleting would cause "readonly database" errors.
 */
function cleanupTestEnvironment(): void {
  console.log('\n🧹 Cleaning up test environment...');

  // Remove workspaces directory to avoid conflicts
  // This prevents "workspace already exists" errors when creating projects
  const projectRoot = path.resolve(__dirname, '../..');
  const workspacesDir = path.join(projectRoot, '.codeframe', 'workspaces');
  if (fs.existsSync(workspacesDir)) {
    console.log(`   Removing workspaces directory: ${workspacesDir}`);
    fs.rmSync(workspacesDir, { recursive: true, force: true });
  }

  console.log('✅ Test environment cleaned');
}

/**
 * Get the test database path.
 * Uses a fixed path that matches the Playwright config's DATABASE_PATH.
 */
function getTestDatabasePath(): string {
  return TEST_DB_PATH;
}

/**
 * Ensure the test database directory exists and initialize the schema.
 */
function initializeTestDatabase(): void {
  console.log('\n🗄️ Initializing test database...\n');

  // Create database directory if it doesn't exist
  const dbDir = path.dirname(TEST_DB_PATH);
  if (!fs.existsSync(dbDir)) {
    console.log(`📁 Creating database directory: ${dbDir}`);
    fs.mkdirSync(dbDir, { recursive: true });
  }

  // Initialize database schema using Python backend
  // Use spawnSync with argument array to prevent command injection
  try {
    console.log('🔧 Creating database schema...');
    const projectRoot = path.resolve(__dirname, '../..');
    const pythonCode = `from codeframe.persistence.database import Database; import sys; db = Database(sys.argv[1]); db.initialize()`;
    const result = spawnSync('uv', ['run', 'python', '-c', pythonCode, TEST_DB_PATH], {
      cwd: projectRoot,
      stdio: 'inherit',
      encoding: 'utf-8',
    });
    if (result.status !== 0) {
      throw new Error(`Database initialization failed with exit code ${result.status}`);
    }
    console.log('✅ Database schema initialized');
  } catch (error) {
    console.error('❌ Failed to initialize database schema:', error);
    throw error;
  }
}

/**
 * Seed test data directly into SQLite database using Python script.
 * This is more reliable than API-based seeding since create endpoints don't exist.
 */
function seedDatabaseDirectly(projectId: number): void {
  console.log('\n📊 Seeding test data directly into database...\n');

  // Use spawnSync with argument array to prevent command injection
  // Use 'uv run python' to ensure we use the project's managed virtual environment
  try {
    const dbPath = getTestDatabasePath();
    console.log(`📁 Using test database: ${dbPath}`);

    const scriptPath = path.join(__dirname, 'seed-test-data.py');
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Seeding script not found: ${scriptPath}`);
    }

    const projectRoot = path.resolve(__dirname, '../..');
    console.log(`🐍 Executing: uv run python ${scriptPath} ${dbPath} ${projectId}\n`);

    const result = spawnSync('uv', ['run', 'python', scriptPath, dbPath, projectId.toString()], {
      cwd: projectRoot,
      stdio: 'inherit',
      encoding: 'utf-8',
    });

    if (result.status !== 0) {
      throw new Error(`Seeding script failed with exit code ${result.status}`);
    }

    console.log('\n✅ Database seeding complete!');
  } catch (error) {
    console.error('❌ Failed to seed database:', error);
    // Fail fast by default to make debugging easier
    // Set E2E_ALLOW_SEED_FAILURE=true to allow tests to run with missing data
    if (process.env.E2E_ALLOW_SEED_FAILURE === 'true') {
      console.warn('⚠️  E2E_ALLOW_SEED_FAILURE=true: Continuing despite seed failure');
      console.warn('⚠️  Tests may fail due to missing test data');
    } else {
      throw error;
    }
  }
}

/**
 * Create a test user with known credentials for E2E tests.
 * Returns the session token to use in authenticated requests.
 */
async function createTestUser(page: any): Promise<string> {
  console.log('\n👤 Creating test user...');

  const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
  const TEST_USER = {
    email: 'test@example.com',
    password: 'testpassword123',
    name: 'E2E Test User'
  };

  try {
    // Try to sign up the test user
    const signupResponse = await page.request.post(`${FRONTEND_URL}/api/auth/signup`, {
      data: TEST_USER,
      failOnStatusCode: false
    });

    if (signupResponse.ok()) {
      console.log('✅ Test user created successfully');
    } else if (signupResponse.status() === 400) {
      // User might already exist, try to sign in
      console.log('   Test user already exists, signing in...');
    } else {
      console.warn(`⚠️  Signup failed with status ${signupResponse.status()}: ${await signupResponse.text()}`);
    }

    // Sign in to get session token
    const signinResponse = await page.request.post(`${FRONTEND_URL}/api/auth/signin`, {
      data: {
        email: TEST_USER.email,
        password: TEST_USER.password
      }
    });

    if (!signinResponse.ok()) {
      throw new Error(`Failed to sign in test user: ${signinResponse.status()} - ${await signinResponse.text()}`);
    }

    // Extract session token from response cookies
    const cookies = await page.context().cookies();
    const sessionCookie = cookies.find(c => c.name === 'better-auth.session_token' || c.name === 'session_token' || c.name === 'auth_token');

    if (!sessionCookie) {
      console.warn('⚠️  No session cookie found, available cookies:', cookies.map(c => c.name));
      // Return empty token - tests will need to handle authentication differently
      return '';
    }

    console.log('✅ Test user authenticated successfully');
    console.log(`   Email: ${TEST_USER.email}`);
    console.log(`   Session token: ${sessionCookie.value.substring(0, 20)}...`);

    // Store credentials for tests to use
    process.env.E2E_TEST_USER_EMAIL = TEST_USER.email;
    process.env.E2E_TEST_USER_PASSWORD = TEST_USER.password;
    process.env.E2E_TEST_SESSION_TOKEN = sessionCookie.value;

    return sessionCookie.value;
  } catch (error) {
    console.error('❌ Failed to create test user:', error);
    // Don't throw - tests can still run without auth if AUTH_REQUIRED=false
    console.warn('⚠️  Tests will run without authentication');
    return '';
  }
}

async function globalSetup(config: FullConfig) {
  console.log('🔧 Setting up E2E test environment...');

  // Clean up any stale test artifacts first
  cleanupTestEnvironment();

  // Initialize test database schema.
  // NOTE ON ORDERING: Playwright starts webServer BEFORE globalSetup runs.
  // This means the backend is already running when we reach this point.
  // This is safe because:
  // 1. Backend respects DATABASE_PATH env var and uses the test database
  // 2. Database.initialize() uses CREATE TABLE IF NOT EXISTS (idempotent)
  // 3. We do NOT delete the database file (would cause "readonly database" errors)
  initializeTestDatabase();

  // Launch browser for API calls
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // Wait for frontend to be ready before creating user
  console.log('\n⏳ Waiting for frontend to be ready...');
  const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
  let frontendReady = false;
  for (let i = 0; i < 60; i++) {
    try {
      const response = await page.request.get(FRONTEND_URL, { timeout: 2000 });
      if (response.ok() || response.status() === 404) {
        frontendReady = true;
        console.log('✅ Frontend is ready');
        break;
      }
    } catch (e) {
      // Frontend not ready yet
    }
    await page.waitForTimeout(1000);
  }

  if (!frontendReady) {
    console.warn('⚠️  Frontend did not become ready in time, continuing anyway...');
  }

  // Create test user and get session token
  await createTestUser(page);

  try {
    // ========================================
    // 1. Create or reuse test project
    // ========================================
    const projectsResponse = await page.request.get(`${BACKEND_URL}/api/projects`);
    let projectId: number;

    if (projectsResponse.ok()) {
      const data = await projectsResponse.json();
      const projects = data.projects || [];

      // Look for existing e2e-test-project or any project we can reuse
      const existingProject = projects.find((p: { name: string }) => p.name === 'e2e-test-project') || projects[0];

      if (existingProject) {
        // Use existing project
        projectId = existingProject.id;
        console.log(`✅ Using existing project ID: ${projectId} (${existingProject.name})`);
        process.env.E2E_TEST_PROJECT_ID = projectId.toString();
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
          // If creation fails (e.g., workspace exists), try to fetch projects again
          // The workspace might exist from a previous run with a different database
          console.warn(`⚠️  Project creation failed: ${createResponse.statusText()}`);
          const retryResponse = await page.request.get(`${BACKEND_URL}/api/projects`);
          if (retryResponse.ok()) {
            const retryData = await retryResponse.json();
            const retryProjects = retryData.projects || [];
            if (retryProjects.length > 0) {
              projectId = retryProjects[0].id;
              console.log(`✅ Using existing project ID after retry: ${projectId}`);
              process.env.E2E_TEST_PROJECT_ID = projectId.toString();
            } else {
              throw new Error(`Failed to create project and no existing projects found: ${createResponse.statusText()}`);
            }
          } else {
            throw new Error(`Failed to create project: ${createResponse.statusText()}`);
          }
        } else {
          const project = await createResponse.json();
          projectId = project.id;
          console.log(`✅ Test project created with ID: ${projectId}`);
          process.env.E2E_TEST_PROJECT_ID = projectId.toString();
        }
      }
    } else {
      throw new Error(`Failed to fetch projects: ${projectsResponse.statusText()}`);
    }

    // ========================================
    // 2. Seed test data directly into database
    // ========================================
    // Use Python script to seed directly into SQLite instead of API calls
    // (many create endpoints don't exist)
    // Note: This now includes checkpoint seeding
    seedDatabaseDirectly(projectId);

    console.log('\n✅ E2E test environment ready!');
    console.log(`   Project ID: ${projectId}`);
    console.log(`   Backend URL: ${BACKEND_URL}`);
    console.log('');

  } catch (error) {
    console.error('❌ Failed to set up test environment:', error);
    throw error;
  } finally {
    await context.close();
    await browser.close();
  }
}

export default globalSetup;
