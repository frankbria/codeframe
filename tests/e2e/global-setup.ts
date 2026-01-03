/**
 * Global setup for Playwright E2E tests.
 * Creates a test project and seeds comprehensive test data before running tests.
 */
import { chromium, FullConfig, APIRequestContext } from '@playwright/test';
import { spawnSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { TEST_DB_PATH, BACKEND_URL } from './e2e-config';
import Database from 'better-sqlite3';

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
 * Store test user credentials for E2E tests to use with loginUser() helper.
 * These credentials match the test user seeded by seed-test-data.py.
 */
function storeTestUserCredentials(): void {
  console.log('\n👤 Storing test user credentials for E2E tests...');

  // Store credentials for tests to use with loginUser() helper
  process.env.E2E_TEST_USER_EMAIL = 'test@example.com';
  process.env.E2E_TEST_USER_PASSWORD = 'Testpassword123';

  console.log('✅ Test user credentials stored');
  console.log(`   Email: test@example.com`);
  console.log(`   Password: Testpassword123`);
  console.log('   Note: Tests will use real login flow via FastAPI Users JWT');
}

/**
 * Seed test user directly into SQLite database.
 * Must be called BEFORE any API calls since authentication is now always required.
 */
function seedTestUser(): void {
  console.log('\n👤 Seeding test user for authentication...');

  try {
    const db = new Database(TEST_DB_PATH);

    // Check if user already exists
    const existingUser = db.prepare('SELECT id FROM users WHERE email = ?').get('test@example.com');
    if (existingUser) {
      console.log('✅ Test user already exists (email: test@example.com)');
      db.close();
      return;
    }

    // Use fixed reference timestamp for reproducible test data
    const now = new Date('2025-01-15T10:00:00Z').toISOString();

    // FastAPI Users compatible password hash (argon2id hash of 'Testpassword123')
    // Generated with: uv run python -c "from fastapi_users.password import PasswordHelper; print(PasswordHelper().hash('Testpassword123'))"
    const testUserPasswordHash = '$argon2id$v=19$m=65536,t=3,p=4$AxoKRsvvZWnspMuG1EU8dg$8wybn5xP5s7mVC67TjepMx0ulIKAspzicdScIZtJ/MY';

    // Insert test user
    db.prepare(`
      INSERT OR REPLACE INTO users (
        id, email, name, hashed_password,
        is_active, is_superuser, is_verified, email_verified,
        created_at, updated_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      1,
      'test@example.com',
      'E2E Test User',
      testUserPasswordHash,
      1,  // is_active
      0,  // is_superuser
      1,  // is_verified
      1,  // email_verified
      now,
      now
    );

    console.log('✅ Test user created (email: test@example.com, password: Testpassword123)');
    db.close();
  } catch (error) {
    console.error('❌ Failed to seed test user:', error);
    throw error;
  }
}

/**
 * Login to the backend and get a JWT token for authenticated API calls.
 * Returns the access token for use in Authorization header.
 */
async function loginAndGetToken(request: APIRequestContext): Promise<string> {
  console.log('\n🔐 Logging in to get JWT token...');

  // FastAPI Users JWT login endpoint uses form data (OAuth2 password flow)
  const response = await request.post(`${BACKEND_URL}/auth/jwt/login`, {
    form: {
      username: 'test@example.com',
      password: 'Testpassword123'
    }
  });

  if (!response.ok()) {
    const errorText = await response.text();
    throw new Error(`Failed to login: ${response.status()} ${response.statusText()} - ${errorText}`);
  }

  const data = await response.json();
  const token = data.access_token;

  if (!token) {
    throw new Error('Login response did not contain access_token');
  }

  console.log('✅ Login successful, JWT token obtained');
  return token;
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

  // Seed test user BEFORE any API calls (authentication is always required)
  seedTestUser();

  // Launch browser for API calls
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // ========================================
    // 1. Login to get JWT token for authenticated API calls
    // ========================================
    const authToken = await loginAndGetToken(page.request);

    // Create headers with authentication
    const authHeaders = {
      'Authorization': `Bearer ${authToken}`
    };

    // ========================================
    // 2. Create or reuse test project (with authentication)
    // ========================================
    const projectsResponse = await page.request.get(`${BACKEND_URL}/api/projects`, {
      headers: authHeaders
    });
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
          headers: authHeaders,
          data: {
            name: 'e2e-test-project',
            description: 'Test project for Playwright E2E tests'
          }
        });

        if (!createResponse.ok()) {
          // If creation fails (e.g., workspace exists), try to fetch projects again
          // The workspace might exist from a previous run with a different database
          console.warn(`⚠️  Project creation failed: ${createResponse.statusText()}`);
          const retryResponse = await page.request.get(`${BACKEND_URL}/api/projects`, {
            headers: authHeaders
          });
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
    // 3. Seed test data directly into database
    // ========================================
    // Use Python script to seed directly into SQLite instead of API calls
    // (many create endpoints don't exist)
    // Note: Test user was already seeded before login, this seeds project data
    seedDatabaseDirectly(projectId);

    // ========================================
    // 4. Store test user credentials
    // ========================================
    // Store credentials for E2E tests to use with loginUser() helper
    // Tests will perform real login via FastAPI Users JWT
    storeTestUserCredentials();

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
