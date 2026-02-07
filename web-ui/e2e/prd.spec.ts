/**
 * E2E tests for PRD management page.
 *
 * Covers: PRD display, empty state, upload, editing, Socratic discovery,
 * PRD generation from discovery, task generation, and version info.
 */
import { test, expect } from './fixtures/test-setup';
import { mockPrd, mockDiscoverySession } from './fixtures/mock-data';

// ---------------------------------------------------------------------------
// 1. PRD Display
// ---------------------------------------------------------------------------
test.describe('PRD Display', () => {
  test('renders existing PRD with title, version, and markdown content', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // Title from mockPrd
    await expect(page.getByRole('heading', { name: mockPrd.title })).toBeVisible();

    // Version indicator in header
    await expect(page.getByText(`Version ${mockPrd.version}`)).toBeVisible();

    // Markdown content is rendered in the editor textarea (Edit tab is default)
    const textarea = page.getByPlaceholder('Write your PRD in markdown...');
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(mockPrd.content);
  });

  test('renders markdown preview when Preview tab is clicked', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // Click Preview tab
    await page.getByRole('tab', { name: 'Preview' }).click();

    // Markdown headings rendered as HTML
    await expect(page.getByRole('heading', { name: 'Project Overview' })).toBeVisible();
    await expect(page.getByText('Goal 1')).toBeVisible();
  });

  test('shows task counts summary when tasks exist', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // AssociatedTasksSummary shows total count
    await expect(page.getByText(/Tasks \(\d+\)/)).toBeVisible();
  });

  test('header action buttons are visible', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // When PRD exists, Upload button says "Upload New"
    await expect(page.getByRole('button', { name: /Upload New/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Discovery/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Generate Tasks/ })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 2. No PRD State
// ---------------------------------------------------------------------------
test.describe('No PRD State', () => {
  test('shows empty state when no PRD exists', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Empty state heading and description
    await expect(page.getByRole('heading', { name: 'No PRD yet' })).toBeVisible();
    await expect(page.getByText(/Upload a PRD document or start an AI-powered discovery/)).toBeVisible();

    // Empty state action buttons (header also has "Upload PRD", so scope to within the card)
    await expect(page.getByRole('button', { name: 'Upload PRD' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start Discovery' })).toBeVisible();
  });

  test('header shows "Product Requirements" when no PRD exists', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await expect(page.getByRole('heading', { name: 'Product Requirements' })).toBeVisible();
  });

  test('Generate Tasks button is disabled when no PRD exists', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await expect(page.getByRole('button', { name: /Generate Tasks/ })).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// 3. Upload PRD
// ---------------------------------------------------------------------------
test.describe('Upload PRD', () => {
  test('opens upload modal from header button', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Upload New/ }).click();

    // Dialog opens
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Upload PRD' })).toBeVisible();
    await expect(page.getByText('Upload a markdown file or paste PRD content directly.')).toBeVisible();
  });

  test('opens upload modal from empty state button', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Use the empty state Upload PRD button (second one — header button is first)
    await page.getByRole('button', { name: 'Upload PRD' }).nth(1).click();

    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Upload PRD' })).toBeVisible();
  });

  test('can paste markdown content and submit', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    const prdContent = '# My New PRD\n\nSome requirements here.';
    let capturedPostBody: Record<string, unknown> | null = null;

    await mockApi({
      'prd/create': async (route) => {
        capturedPostBody = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...mockPrd, content: prdContent, title: 'My New PRD' }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Open upload modal
    await page.getByRole('button', { name: /Upload New/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    // Fill in title
    await page.getByLabel(/Title/).fill('My New PRD');

    // Paste tab is default, fill the textarea
    await page.getByPlaceholder('Paste your PRD markdown here...').fill(prdContent);

    // Click Create PRD
    await page.getByRole('button', { name: 'Create PRD' }).click();

    // Dialog should close on success
    await expect(page.getByRole('dialog')).toBeHidden();

    // Verify POST was made with correct content
    expect(capturedPostBody).not.toBeNull();
    expect((capturedPostBody as Record<string, unknown>).content).toBe(prdContent);
    expect((capturedPostBody as Record<string, unknown>).title).toBe('My New PRD');
  });

  test('Create PRD button is disabled when content is empty', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Upload New/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    // Create PRD button should be disabled (no content)
    await expect(page.getByRole('button', { name: 'Create PRD' })).toBeDisabled();
  });

  test('cancel button closes the upload modal', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Upload New/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  test('shows file upload tab', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Upload New/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    // Switch to Upload File tab
    await page.getByRole('tab', { name: 'Upload File' }).click();

    // File upload area is visible
    await expect(page.getByText('Select a .md file')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Choose File' })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 4. Edit PRD
// ---------------------------------------------------------------------------
test.describe('Edit PRD', () => {
  test('editing content shows Save button and change summary input', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    const textarea = page.getByPlaceholder('Write your PRD in markdown...');
    await expect(textarea).toBeVisible();

    // Modify content to trigger hasChanges
    await textarea.fill(mockPrd.content + '\n\n## New Section');

    // Save button and change summary input should appear
    await expect(page.getByRole('button', { name: 'Save' })).toBeVisible();
    await expect(page.getByPlaceholder('Change summary (optional)')).toBeVisible();
  });

  test('saving edited PRD sends version request', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let versionRequestMade = false;

    await mockApi();

    // Intercept the version creation endpoint (POST /api/v2/prd/{id}/versions)
    await page.route('**/api/v2/prd/*/versions*', async (route) => {
      if (route.request().method() === 'POST') {
        versionRequestMade = true;
        const body = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...mockPrd,
            version: 2,
            content: body.content,
            change_summary: body.change_summary,
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([mockPrd]),
        });
      }
    });

    await withWorkspace();
    await page.goto('/prd');

    const textarea = page.getByPlaceholder('Write your PRD in markdown...');
    await textarea.fill(mockPrd.content + '\n\n## Updated section');

    // Add a change summary
    await page.getByPlaceholder('Change summary (optional)').fill('Added new section');

    // Save
    await page.getByRole('button', { name: 'Save' }).click();

    // Verify version POST was made
    expect(versionRequestMade).toBe(true);
  });

  test('Save button is hidden when content has not changed', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // Without edits, Save should not be visible
    await expect(page.getByRole('button', { name: 'Save' })).toBeHidden();
  });

  test('Edit and Preview tabs toggle correctly', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // Edit tab is active by default — textarea visible
    await expect(page.getByPlaceholder('Write your PRD in markdown...')).toBeVisible();

    // Switch to Preview
    await page.getByRole('tab', { name: 'Preview' }).click();
    await expect(page.getByPlaceholder('Write your PRD in markdown...')).toBeHidden();
    // Markdown content rendered as HTML
    await expect(page.getByText('This is a test PRD for E2E testing.')).toBeVisible();

    // Switch back to Edit
    await page.getByRole('tab', { name: 'Edit' }).click();
    await expect(page.getByPlaceholder('Write your PRD in markdown...')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 5. Socratic Discovery
// ---------------------------------------------------------------------------
test.describe('Socratic Discovery', () => {
  test('clicking Discovery opens the discovery panel', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    // Override discovery/status to return no active session so it starts fresh
    await mockApi({
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ state: 'idle', session_id: null, progress: {}, current_question: null, error: null }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Discovery/ }).click();

    // Discovery panel header
    await expect(page.getByText('Discovery Session')).toBeVisible();

    // Close button is visible
    await expect(page.getByRole('button', { name: 'Close discovery panel' })).toBeVisible();
  });

  test('shows first question from discovery API', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ state: 'idle', session_id: null, progress: {}, current_question: null, error: null }),
        });
      },
      'discovery/start': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            session_id: 'disc-001',
            state: 'discovering',
            question: { text: 'What is the main purpose of your application?' },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Discovery/ }).click();

    // First question appears in transcript
    await expect(page.getByText('What is the main purpose of your application?')).toBeVisible();
  });

  test('user can type and submit an answer', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let answerSubmitted = false;

    await mockApi({
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ state: 'idle', session_id: null, progress: {}, current_question: null, error: null }),
        });
      },
      'discovery/start': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            session_id: 'disc-001',
            state: 'discovering',
            question: { text: 'What is the main purpose of your application?' },
          }),
        });
      },
      'discovery/answer': async (route) => {
        answerSubmitted = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            accepted: true,
            feedback: 'Great, that helps clarify the purpose.',
            follow_up: null,
            is_complete: false,
            next_question: { text: 'Who are the target users?' },
            coverage: null,
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Discovery/ }).click();

    // Wait for first question
    await expect(page.getByText('What is the main purpose of your application?')).toBeVisible();

    // Type answer
    const answerInput = page.getByPlaceholder('Type your answer...');
    await answerInput.fill('It is a project management tool for developers.');

    // Submit via Ctrl+Enter (the send button is icon-only with no accessible name)
    await answerInput.press('Control+Enter');

    // User message appears in transcript
    await expect(page.getByText('It is a project management tool for developers.')).toBeVisible();

    // AI response with next question
    await expect(page.getByText('Great, that helps clarify the purpose.')).toBeVisible();
    await expect(page.getByText('Who are the target users?')).toBeVisible();

    expect(answerSubmitted).toBe(true);
  });

  test('closing discovery panel hides it', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ state: 'idle', session_id: null, progress: {}, current_question: null, error: null }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Discovery/ }).click();
    await expect(page.getByText('Discovery Session')).toBeVisible();

    await page.getByRole('button', { name: 'Close discovery panel' }).click();

    // Panel should be gone
    await expect(page.getByText('Discovery Session')).toBeHidden();
  });

  test('shows resume prompt when active session exists', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            state: 'discovering',
            session_id: 'disc-existing',
            progress: { answered_count: 3 },
            current_question: { text: 'What integrations do you need?' },
            error: null,
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await page.getByRole('button', { name: /Discovery/ }).click();

    // Resume prompt should appear
    await expect(page.getByText(/You have an active discovery session/)).toBeVisible();
    await expect(page.getByText(/3 questions answered/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start Fresh' })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 6. Generate PRD from Discovery
// ---------------------------------------------------------------------------
test.describe('Generate PRD from Discovery', () => {
  test('shows Generate PRD button when discovery is complete', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            state: 'completed',
            session_id: 'disc-completed',
            progress: { answered_count: 5 },
            current_question: null,
            error: null,
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Open discovery (no PRD, use empty state button)
    await page.getByRole('button', { name: 'Start Discovery' }).click();

    // Generate PRD button appears for completed sessions
    await expect(page.getByRole('button', { name: 'Generate PRD' })).toBeVisible();
  });

  test('clicking Generate PRD calls generate-prd API then fetches latest PRD', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let generatePrdCalled = false;
    let latestPrdCalled = false;

    const generatedPrd = {
      ...mockPrd,
      id: 'prd-generated',
      title: 'Generated PRD',
      content: '# Generated PRD\n\nContent from discovery.',
    };

    await mockApi({
      'prd/latest': async (route) => {
        // First call returns 404, subsequent calls return generated PRD
        if (!latestPrdCalled) {
          latestPrdCalled = true;
          await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
        } else {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(generatedPrd),
          });
        }
      },
      'discovery/status': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            state: 'completed',
            session_id: 'disc-completed',
            progress: { answered_count: 5 },
            current_question: null,
            error: null,
          }),
        });
      },
      'discovery/generate-prd': async (route) => {
        generatePrdCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ prd_id: 'prd-generated', content: generatedPrd.content }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Open discovery from empty state
    await page.getByRole('button', { name: 'Start Discovery' }).click();

    // Click Generate PRD
    await page.getByRole('button', { name: 'Generate PRD' }).click();

    // Wait for the PRD title to appear (discovery panel closes, PRD loads)
    await expect(page.getByRole('heading', { name: 'Generated PRD' })).toBeVisible();

    expect(generatePrdCalled).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 7. Generate Tasks from PRD
// ---------------------------------------------------------------------------
test.describe('Generate Tasks from PRD', () => {
  test('clicking Generate Tasks calls the API', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let generateTasksCalled = false;

    await mockApi({
      'discovery/generate-tasks': async (route) => {
        generateTasksCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ tasks_generated: 3, task_ids: ['task-001', 'task-002', 'task-003'] }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Wait for PRD to load so button is enabled
    await expect(page.getByRole('heading', { name: mockPrd.title })).toBeVisible();

    await page.getByRole('button', { name: /Generate Tasks/ }).click();

    // Button should show loading state
    await expect(page.getByText('Generating...')).toBeVisible();

    // Wait for completion
    await expect(page.getByRole('button', { name: /Generate Tasks/ })).toBeVisible();

    expect(generateTasksCalled).toBe(true);
  });

  test('Generate Tasks button is disabled when no PRD exists', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    // Header Generate Tasks button should be disabled
    await expect(page.getByRole('button', { name: /Generate Tasks/ })).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// 8. PRD Version Info
// ---------------------------------------------------------------------------
test.describe('PRD Version Info', () => {
  test('displays version number and date', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/prd');

    // Version text in the PRDHeader subheading
    await expect(page.getByText(`Version ${mockPrd.version}`)).toBeVisible();

    // Date is formatted via toLocaleDateString()
    const dateStr = new Date(mockPrd.created_at).toLocaleDateString();
    await expect(page.getByText(dateStr)).toBeVisible();
  });

  test('version info is not shown when no PRD exists', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No PRD found' }) });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await expect(page.getByText(/Version \d/)).toBeHidden();
  });
});

// ---------------------------------------------------------------------------
// 9. No Workspace Selected
// ---------------------------------------------------------------------------
test.describe('No Workspace', () => {
  test('shows workspace warning when no workspace is set', async ({
    page,
    mockApi,
  }) => {
    await mockApi();
    // Do NOT call withWorkspace — localStorage will be empty
    await page.goto('/prd');

    await expect(page.getByText(/No workspace selected/)).toBeVisible();
    await expect(page.getByRole('link', { name: 'Workspace' })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 10. Error State
// ---------------------------------------------------------------------------
test.describe('Error State', () => {
  test('shows error banner for non-404 API errors', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'prd/latest': async (route) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error', status_code: 500 }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/prd');

    await expect(page.getByRole('heading', { name: 'Error' })).toBeVisible();
    await expect(page.getByText(/Failed to load PRD|Internal server error/)).toBeVisible();
  });
});
