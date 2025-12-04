/**
 * Global setup for Playwright E2E tests.
 * Creates a test project and seeds comprehensive test data before running tests.
 */
import { chromium, FullConfig, Page } from '@playwright/test';
import { execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';

/**
 * Find the CodeFRAME database path.
 * Tries common locations: ./state.db, ./.codeframe/state.db, etc.
 */
function findDatabasePath(): string {
  const possiblePaths = [
    path.join(process.cwd(), 'state.db'),
    path.join(process.cwd(), '.codeframe', 'state.db'),
    path.join(process.cwd(), '..', '..', 'state.db'),
    path.join(process.cwd(), '..', '..', '.codeframe', 'state.db'),
  ];

  for (const dbPath of possiblePaths) {
    if (fs.existsSync(dbPath)) {
      return dbPath;
    }
  }

  throw new Error('Could not find CodeFRAME database (state.db). Tried paths: ' + possiblePaths.join(', '));
}

/**
 * Seed test data directly into SQLite database using Python script.
 * This is more reliable than API-based seeding since create endpoints don't exist.
 */
function seedDatabaseDirectly(projectId: number): void {
  console.log('\n📊 Seeding test data directly into database...\n');

  try {
    const dbPath = findDatabasePath();
    console.log(`📁 Database found: ${dbPath}`);

    const scriptPath = path.join(__dirname, 'seed-test-data.py');
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Seeding script not found: ${scriptPath}`);
    }

    const command = `python3 "${scriptPath}" "${dbPath}" ${projectId}`;
    console.log(`🐍 Executing: ${command}\n`);

    execSync(command, { stdio: 'inherit' });

    console.log('\n✅ Database seeding complete!');
  } catch (error) {
    console.error('❌ Failed to seed database:', error);
    console.warn('⚠️  Tests may fail due to missing test data');
    // Don't throw - allow tests to run even if seeding fails
  }
}

/**
 * Seed 5 agents with mixed statuses (working, idle, blocked).
 */
async function seedAgents(page: Page, projectId: number): Promise<void> {
  console.log('👥 Seeding agents...');

  const agents = [
    {
      id: 'lead-001',
      type: 'lead',
      status: 'working',
      provider: 'anthropic',
      maturity: 'delegating',
      current_task: { id: 1, title: 'Orchestrate project' },
      context_tokens: 25000,
      tasks_completed: 12,
      timestamp: Date.now()
    },
    {
      id: 'backend-worker-001',
      type: 'backend-worker',
      status: 'working',
      provider: 'anthropic',
      maturity: 'delegating',
      current_task: { id: 2, title: 'Implement API endpoints' },
      context_tokens: 45000,
      tasks_completed: 8,
      timestamp: Date.now()
    },
    {
      id: 'frontend-specialist-001',
      type: 'frontend-specialist',
      status: 'idle',
      provider: 'anthropic',
      maturity: 'supporting',
      context_tokens: 12000,
      tasks_completed: 5,
      timestamp: Date.now()
    },
    {
      id: 'test-engineer-001',
      type: 'test-engineer',
      status: 'working',
      provider: 'anthropic',
      maturity: 'delegating',
      current_task: { id: 3, title: 'Write E2E tests' },
      context_tokens: 30000,
      tasks_completed: 15,
      timestamp: Date.now()
    },
    {
      id: 'review-agent-001',
      type: 'review',
      status: 'blocked',
      provider: 'anthropic',
      maturity: 'delegating',
      blocker: 'Waiting for code review completion',
      context_tokens: 18000,
      tasks_completed: 20,
      timestamp: Date.now()
    }
  ];

  let createdCount = 0;
  for (const agent of agents) {
    try {
      // Note: The backend may not have a direct POST /api/agents endpoint.
      // Agents are typically created internally by the system.
      // We'll try the endpoint, but expect it may not exist.
      const response = await page.request.post(`${BACKEND_URL}/api/agents`, {
        data: agent,
        timeout: 10000
      });

      if (response.ok()) {
        createdCount++;
      } else {
        console.warn(`⚠️  Failed to create agent ${agent.id}: ${response.statusText()}`);
      }
    } catch (error) {
      console.warn(`⚠️  Failed to create agent ${agent.id}:`, error);
    }
  }

  if (createdCount > 0) {
    console.log(`✅ Seeded ${createdCount}/${agents.length} agents`);
  } else {
    console.log('⚠️  No agents created (endpoint may not exist or agents created internally)');
  }
}

/**
 * Seed 10 tasks with mixed statuses (completed, in_progress, blocked, pending).
 */
async function seedTasks(page: Page, projectId: number): Promise<void> {
  console.log('📋 Seeding tasks...');

  const tasks = [
    // Completed tasks
    {
      id: 1,
      project_id: projectId,
      title: 'Setup project structure',
      description: 'Initialize project repository and workspace',
      status: 'completed',
      assigned_to: 'lead-001',
      priority: 1,
      workflow_step: 1,
      timestamp: Date.now() - 86400000 * 2 // 2 days ago
    },
    {
      id: 2,
      project_id: projectId,
      title: 'Implement authentication API',
      description: 'Build JWT-based authentication endpoints',
      status: 'completed',
      assigned_to: 'backend-worker-001',
      priority: 1,
      workflow_step: 2,
      timestamp: Date.now() - 86400000 * 1 // 1 day ago
    },
    {
      id: 3,
      project_id: projectId,
      title: 'Write unit tests for auth',
      description: 'Comprehensive test coverage for authentication',
      status: 'completed',
      assigned_to: 'test-engineer-001',
      priority: 1,
      workflow_step: 3,
      timestamp: Date.now() - 43200000 // 12 hours ago
    },

    // In-progress tasks
    {
      id: 4,
      project_id: projectId,
      title: 'Build dashboard UI',
      description: 'Create React dashboard with real-time updates',
      status: 'in_progress',
      assigned_to: 'frontend-specialist-001',
      priority: 2,
      workflow_step: 4,
      timestamp: Date.now() - 7200000 // 2 hours ago
    },
    {
      id: 5,
      project_id: projectId,
      title: 'Add token usage tracking',
      description: 'Implement token counting and cost analytics',
      status: 'in_progress',
      assigned_to: 'backend-worker-001',
      priority: 2,
      workflow_step: 4,
      timestamp: Date.now() - 3600000 // 1 hour ago
    },

    // Blocked tasks
    {
      id: 6,
      project_id: projectId,
      title: 'Deploy to production',
      description: 'Set up production deployment pipeline',
      status: 'blocked',
      depends_on: '7,8',
      priority: 3,
      workflow_step: 6,
      timestamp: Date.now() - 1800000 // 30 minutes ago
    },
    {
      id: 7,
      project_id: projectId,
      title: 'Security audit',
      description: 'Comprehensive security review and penetration testing',
      status: 'blocked',
      depends_on: '4',
      priority: 2,
      workflow_step: 5,
      timestamp: Date.now() - 1800000 // 30 minutes ago
    },

    // Pending tasks
    {
      id: 8,
      project_id: projectId,
      title: 'Write API documentation',
      description: 'OpenAPI/Swagger documentation for all endpoints',
      status: 'pending',
      priority: 3,
      workflow_step: 5,
      timestamp: Date.now()
    },
    {
      id: 9,
      project_id: projectId,
      title: 'Optimize database queries',
      description: 'Add indexes and optimize slow queries',
      status: 'pending',
      priority: 2,
      workflow_step: 5,
      timestamp: Date.now()
    },
    {
      id: 10,
      project_id: projectId,
      title: 'Add logging middleware',
      description: 'Structured logging with request/response tracking',
      status: 'pending',
      priority: 2,
      workflow_step: 5,
      timestamp: Date.now()
    }
  ];

  let createdCount = 0;
  for (const task of tasks) {
    try {
      const response = await page.request.post(`${BACKEND_URL}/api/tasks`, {
        data: task,
        timeout: 10000
      });

      if (response.ok()) {
        createdCount++;
      } else {
        console.warn(`⚠️  Failed to create task ${task.id}: ${response.statusText()}`);
      }
    } catch (error) {
      console.warn(`⚠️  Failed to create task ${task.id}:`, error);
    }
  }

  if (createdCount > 0) {
    console.log(`✅ Seeded ${createdCount}/${tasks.length} tasks`);
  } else {
    console.log('⚠️  No tasks created (endpoint may not exist)');
  }
}

/**
 * Seed 15 token usage records across 3 models (Sonnet, Opus, Haiku) and 3 days.
 * Total cost: ~$4.46 USD
 */
async function seedTokenUsage(page: Page, projectId: number): Promise<void> {
  console.log('💰 Seeding token usage records...');

  const now = Date.now();
  const dayMs = 86400000; // 24 hours in milliseconds

  const tokenRecords = [
    // Backend agent usage (Sonnet)
    {
      task_id: 2,
      agent_id: 'backend-worker-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 12500,
      output_tokens: 4800,
      estimated_cost_usd: 0.11,
      call_type: 'task_execution',
      timestamp: new Date(now - dayMs * 2).toISOString()
    },
    {
      task_id: 2,
      agent_id: 'backend-worker-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 8900,
      output_tokens: 3200,
      estimated_cost_usd: 0.075,
      call_type: 'task_execution',
      timestamp: new Date(now - dayMs * 2 + 5400000).toISOString() // +1.5h
    },

    // Frontend agent usage (Haiku for smaller tasks)
    {
      task_id: 4,
      agent_id: 'frontend-specialist-001',
      project_id: projectId,
      model_name: 'claude-haiku-4',
      input_tokens: 5000,
      output_tokens: 2000,
      estimated_cost_usd: 0.012,
      call_type: 'task_execution',
      timestamp: new Date(now - dayMs * 2 + 14400000).toISOString() // +4h
    },
    {
      task_id: 4,
      agent_id: 'frontend-specialist-001',
      project_id: projectId,
      model_name: 'claude-haiku-4',
      input_tokens: 6200,
      output_tokens: 2500,
      estimated_cost_usd: 0.015,
      call_type: 'task_execution',
      timestamp: new Date(now - dayMs * 1 + 3600000).toISOString() // Day 2 +1h
    },

    // Test engineer usage (Sonnet)
    {
      task_id: 3,
      agent_id: 'test-engineer-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 15000,
      output_tokens: 6000,
      estimated_cost_usd: 0.135,
      call_type: 'task_execution',
      timestamp: new Date(now - dayMs * 2 + 21600000).toISOString() // +6h
    },

    // Review agent usage (Opus for code review)
    {
      agent_id: 'review-agent-001',
      project_id: projectId,
      model_name: 'claude-opus-4',
      input_tokens: 25000,
      output_tokens: 8000,
      estimated_cost_usd: 0.975,
      call_type: 'code_review',
      timestamp: new Date(now - dayMs * 1 + 10800000).toISOString() // Day 2 +3h
    },
    {
      agent_id: 'review-agent-001',
      project_id: projectId,
      model_name: 'claude-opus-4',
      input_tokens: 18000,
      output_tokens: 5500,
      estimated_cost_usd: 0.6825,
      call_type: 'code_review',
      timestamp: new Date(now - dayMs * 1 + 18000000).toISOString() // Day 2 +5h
    },

    // Lead agent coordination (Sonnet)
    {
      agent_id: 'lead-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 8000,
      output_tokens: 3000,
      estimated_cost_usd: 0.069,
      call_type: 'coordination',
      timestamp: new Date(now - 3600000).toISOString() // Today -1h
    },

    // Additional records for time-series (Day 3 - today)
    {
      task_id: 5,
      agent_id: 'backend-worker-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 10000,
      output_tokens: 4000,
      estimated_cost_usd: 0.09,
      call_type: 'task_execution',
      timestamp: new Date(now - 1800000).toISOString() // Today -30min
    },
    {
      task_id: 4,
      agent_id: 'frontend-specialist-001',
      project_id: projectId,
      model_name: 'claude-haiku-4',
      input_tokens: 7000,
      output_tokens: 2800,
      estimated_cost_usd: 0.017,
      call_type: 'task_execution',
      timestamp: new Date(now - 900000).toISOString() // Today -15min
    },

    // More Opus usage for higher costs
    {
      agent_id: 'review-agent-001',
      project_id: projectId,
      model_name: 'claude-opus-4',
      input_tokens: 30000,
      output_tokens: 10000,
      estimated_cost_usd: 1.2,
      call_type: 'code_review',
      timestamp: new Date(now - 7200000).toISOString() // Today -2h
    },

    // Haiku for quick coordination
    {
      agent_id: 'lead-001',
      project_id: projectId,
      model_name: 'claude-haiku-4',
      input_tokens: 3000,
      output_tokens: 1200,
      estimated_cost_usd: 0.0072,
      call_type: 'coordination',
      timestamp: new Date(now - 5400000).toISOString() // Today -1.5h
    },

    // Additional Sonnet usage
    {
      task_id: 5,
      agent_id: 'backend-worker-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 14000,
      output_tokens: 5500,
      estimated_cost_usd: 0.1245,
      call_type: 'task_execution',
      timestamp: new Date(now - 10800000).toISOString() // Today -3h
    },
    {
      task_id: 3,
      agent_id: 'test-engineer-001',
      project_id: projectId,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 11000,
      output_tokens: 4200,
      estimated_cost_usd: 0.096,
      call_type: 'task_execution',
      timestamp: new Date(now - 14400000).toISOString() // Today -4h
    },
    {
      agent_id: 'review-agent-001',
      project_id: projectId,
      model_name: 'claude-opus-4',
      input_tokens: 22000,
      output_tokens: 7000,
      estimated_cost_usd: 0.855,
      call_type: 'code_review',
      timestamp: new Date(now - 18000000).toISOString() // Today -5h
    }
  ];

  let createdCount = 0;
  for (const record of tokenRecords) {
    try {
      // Try the most likely endpoints
      const endpoints = [
        `/api/projects/${projectId}/metrics/tokens`,
        `/api/token-usage`
      ];

      let success = false;
      for (const endpoint of endpoints) {
        try {
          const response = await page.request.post(`${BACKEND_URL}${endpoint}`, {
            data: record,
            timeout: 10000
          });

          if (response.ok()) {
            createdCount++;
            success = true;
            break;
          }
        } catch (error) {
          // Try next endpoint
          continue;
        }
      }

      if (!success) {
        console.warn(`⚠️  Failed to create token usage record for agent ${record.agent_id}`);
      }
    } catch (error) {
      console.warn(`⚠️  Failed to create token usage record:`, error);
    }
  }

  if (createdCount > 0) {
    console.log(`✅ Seeded ${createdCount}/${tokenRecords.length} token usage records (~$4.46 total)`);
  } else {
    console.log('⚠️  No token usage records created (endpoint may not exist)');
  }
}

/**
 * Seed 3 checkpoints with Git commit SHAs and metadata.
 */
async function seedCheckpoints(page: Page, projectId: number): Promise<void> {
  console.log('💾 Seeding checkpoints...');

  const now = Date.now();
  const dayMs = 86400000;

  const checkpoints = [
    {
      project_id: projectId,
      name: 'Initial setup complete',
      description: 'Project structure and authentication working',
      trigger: 'phase_transition',
      git_commit: 'a1b2c3d4e5f6',
      database_backup_path: '.codeframe/checkpoints/checkpoint-001-db.sqlite',
      context_snapshot_path: '.codeframe/checkpoints/checkpoint-001-context.json',
      metadata: {
        project_id: projectId,
        phase: 'setup',
        tasks_completed: 3,
        tasks_total: 10,
        agents_active: ['lead-001', 'backend-worker-001', 'test-engineer-001'],
        last_task_completed: 'Write unit tests for auth',
        context_items_count: 45,
        total_cost_usd: 1.2
      },
      created_at: new Date(now - dayMs * 2 + 64800000).toISOString() // 2 days ago + 18h
    },
    {
      project_id: projectId,
      name: 'UI development milestone',
      description: 'Dashboard UI 50% complete',
      trigger: 'manual',
      git_commit: 'f6e5d4c3b2a1',
      database_backup_path: '.codeframe/checkpoints/checkpoint-002-db.sqlite',
      context_snapshot_path: '.codeframe/checkpoints/checkpoint-002-context.json',
      metadata: {
        project_id: projectId,
        phase: 'ui-development',
        tasks_completed: 4,
        tasks_total: 10,
        agents_active: ['lead-001', 'frontend-specialist-001'],
        last_task_completed: 'Build dashboard UI',
        context_items_count: 78,
        total_cost_usd: 2.8
      },
      created_at: new Date(now - dayMs * 1 + 72000000).toISOString() // 1 day ago + 20h
    },
    {
      project_id: projectId,
      name: 'Pre-review snapshot',
      description: 'Before code review process',
      trigger: 'auto',
      git_commit: '9876543210ab',
      database_backup_path: '.codeframe/checkpoints/checkpoint-003-db.sqlite',
      context_snapshot_path: '.codeframe/checkpoints/checkpoint-003-context.json',
      metadata: {
        project_id: projectId,
        phase: 'review',
        tasks_completed: 5,
        tasks_total: 10,
        agents_active: ['lead-001', 'review-agent-001'],
        last_task_completed: 'Add token usage tracking',
        context_items_count: 120,
        total_cost_usd: 4.46
      },
      created_at: new Date(now - 3600000).toISOString() // Today -1h
    }
  ];

  let createdCount = 0;
  for (const checkpoint of checkpoints) {
    try {
      const response = await page.request.post(
        `${BACKEND_URL}/api/projects/${projectId}/checkpoints`,
        {
          data: checkpoint,
          timeout: 10000
        }
      );

      if (response.ok()) {
        createdCount++;
      } else {
        console.warn(`⚠️  Failed to create checkpoint "${checkpoint.name}": ${response.statusText()}`);
      }
    } catch (error) {
      console.warn(`⚠️  Failed to create checkpoint "${checkpoint.name}":`, error);
    }
  }

  if (createdCount > 0) {
    console.log(`✅ Seeded ${createdCount}/${checkpoints.length} checkpoints`);
  } else {
    console.log('⚠️  No checkpoints created (endpoint may not exist)');
  }
}

/**
 * Seed 2 review reports: 1 approved, 1 changes_requested.
 */
async function seedReviews(page: Page, projectId: number): Promise<void> {
  console.log('🔍 Seeding review reports...');

  const now = Date.now();

  const reviews = [
    {
      task_id: 2,
      reviewer_agent_id: 'review-agent-001',
      overall_score: 85,
      complexity_score: 80,
      security_score: 90,
      style_score: 85,
      status: 'approved',
      findings: [
        {
          file_path: 'codeframe/api/auth.py',
          line_number: 45,
          category: 'security',
          severity: 'medium',
          message: 'Consider adding rate limiting to login endpoint to prevent brute force attacks',
          suggestion: "Use FastAPI's limiter middleware with 5 requests per minute limit"
        },
        {
          file_path: 'codeframe/api/auth.py',
          line_number: 78,
          category: 'style',
          severity: 'low',
          message: "Function 'validate_token' exceeds 50 lines, consider extracting helper functions",
          suggestion: 'Extract JWT decoding logic into separate function'
        },
        {
          file_path: 'codeframe/api/auth.py',
          line_number: 120,
          category: 'coverage',
          severity: 'medium',
          message: 'Error handling path not covered by tests (line 120-125)',
          suggestion: 'Add test case for expired token scenario'
        }
      ],
      summary: 'Good implementation overall. Authentication logic is solid with proper JWT handling. Main concerns are rate limiting and test coverage for error paths. Approved with suggested improvements.',
      created_at: new Date(now - 86400000 * 1 + 43200000).toISOString() // 1 day ago + 12h
    },
    {
      task_id: 4,
      reviewer_agent_id: 'review-agent-001',
      overall_score: 65,
      complexity_score: 60,
      security_score: 75,
      style_score: 70,
      status: 'changes_requested',
      findings: [
        {
          file_path: 'web-ui/src/components/Dashboard.tsx',
          line_number: 125,
          category: 'security',
          severity: 'critical',
          message: 'User input not sanitized before rendering, potential XSS vulnerability',
          suggestion: 'Use DOMPurify to sanitize user-generated content before rendering'
        },
        {
          file_path: 'web-ui/src/components/Dashboard.tsx',
          line_number: 200,
          category: 'complexity',
          severity: 'high',
          message: 'Component exceeds 300 lines, violating single responsibility principle',
          suggestion: 'Extract AgentStatusPanel, TaskList, and MetricsChart into separate components'
        },
        {
          file_path: 'web-ui/src/components/Dashboard.tsx',
          line_number: 45,
          category: 'style',
          severity: 'medium',
          message: 'useState hooks not grouped at top of component',
          suggestion: 'Move all useState declarations to top of component for better readability'
        },
        {
          file_path: 'web-ui/src/components/Dashboard.tsx',
          line_number: 180,
          category: 'owasp',
          severity: 'critical',
          message: 'Sensitive data (API tokens) logged to console in production build',
          suggestion: 'Remove console.log statements or gate with NODE_ENV check'
        }
      ],
      summary: 'Component needs refactoring before approval. Critical security issues found: XSS vulnerability and token exposure in logs. Component is too complex (300+ lines) and violates separation of concerns. Please address critical findings before re-review.',
      created_at: new Date(now - 7200000).toISOString() // Today -2h
    }
  ];

  let createdCount = 0;
  for (const review of reviews) {
    try {
      // Try multiple possible endpoints
      const endpoints = [
        `/api/reviews`,
        `/api/projects/${projectId}/reviews`,
        `/api/agents/${review.reviewer_agent_id}/review`
      ];

      let success = false;
      for (const endpoint of endpoints) {
        try {
          const response = await page.request.post(`${BACKEND_URL}${endpoint}`, {
            data: review,
            timeout: 10000
          });

          if (response.ok()) {
            createdCount++;
            success = true;
            break;
          }
        } catch (error) {
          // Try next endpoint
          continue;
        }
      }

      if (!success) {
        console.warn(`⚠️  Failed to create review for task ${review.task_id}`);
      }
    } catch (error) {
      console.warn(`⚠️  Failed to create review for task ${review.task_id}:`, error);
    }
  }

  if (createdCount > 0) {
    console.log(`✅ Seeded ${createdCount}/${reviews.length} review reports`);
  } else {
    console.log('⚠️  No review reports created (endpoint may not exist)');
  }
}

async function globalSetup(config: FullConfig) {
  console.log('🔧 Setting up E2E test environment...');

  // Launch browser for API calls
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // ========================================
    // 1. Create or reuse test project
    // ========================================
    const projectsResponse = await page.request.get(`${BACKEND_URL}/api/projects`);
    let projectId: number;

    if (projectsResponse.ok()) {
      const data = await projectsResponse.json();
      const projects = data.projects || [];

      if (projects.length > 0) {
        // Use first existing project
        projectId = projects[0].id;
        console.log(`✅ Using existing project ID: ${projectId}`);
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
          throw new Error(`Failed to create project: ${createResponse.statusText()}`);
        }

        const project = await createResponse.json();
        projectId = project.id;
        console.log(`✅ Test project created with ID: ${projectId}`);
        process.env.E2E_TEST_PROJECT_ID = projectId.toString();
      }
    } else {
      throw new Error(`Failed to fetch projects: ${projectsResponse.statusText()}`);
    }

    // ========================================
    // 2. Seed test data directly into database
    // ========================================
    // Use Python script to seed directly into SQLite instead of API calls
    // (many create endpoints don't exist)
    seedDatabaseDirectly(projectId);

    // ========================================
    // 3. Seed checkpoints via API (works!)
    // ========================================
    console.log('\n📊 Seeding checkpoints via API...\n');
    await seedCheckpoints(page, projectId);

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
