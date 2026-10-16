import { describe, expect, mock, test } from 'claude-code/testing'
import type { On, RenderElement } from 'claude-code'
import type { Engine } from 'claude-code/testing'

type Answer = { exitCode?: number; stdout?: string; stderr?: string }

const req = (id: string, title: string, status: string, obligation: string, waiver: unknown = null) => ({
  id, title, status, source: 'qa', severity: 'high',
  obligations: [{ gate: 'unit', status: obligation }],
  evidence_rules: [{ test_id: `test_unit_${id.slice(-1)}`, gate: 'unit', must_pass: true }],
  waiver,
})
const LEDGER = {
  requirements: [
    req('REQ-0001', 'Totals round correctly', 'satisfied', 'satisfied'),
    req('REQ-0002', 'Login 500s on an empty form', 'open', 'failed'),
    req('REQ-0003', 'Export keeps the header', 'open', 'pending'),
    req('REQ-0004', 'Legacy importer', 'waived', 'failed', { reason: 'sunset', expired: false }),
    req('REQ-0005', 'Old flaky test', 'waived', 'failed', { reason: 'later', expired: true }),
  ],
}
const STATUS = (runs: unknown[]) => ({ counts: {}, expired_waivers: [], runs })
const RUNS = [
  { run_id: 'r3', started_at: '2026-10-16T10:00:00+00:00', passed: true, vacuous: true, duration_ms: 5 },
  { run_id: 'r2', started_at: '2026-10-16T09:00:00+00:00', passed: false, vacuous: false, duration_ms: 900 },
  { run_id: 'r1', started_at: '2026-10-16T08:00:00+00:00', passed: true, vacuous: false, duration_ms: 800 },
]
const SHOW = {
  requirement: {
    ...req('REQ-0002', 'Login *500s* on [an](http://x) empty form\n---\n# Pwned\n1. list', 'open', 'failed'),
    scope: { files: ['src/auth.py'], routes: [], apis: [], components: [], tags: [] },
  },
  evidence: [{ gate: 'unit', status: 'failed', artifact_path: '/x/a.txt', artifact_checksum: 'abc123', run_id: 'r2', timestamp: '2026-10-16T09:00:00+00:00' }],
}

const PROPS = {
  title: 'proof9', isFocused: true, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 30 }, view: {},
}

function world(on: On, ledger: unknown = LEDGER, runs: unknown[] = RUNS) {
  const argvs: string[] = []
  const submitted: string[] = []
  const opened: string[] = []
  on('process.run', (_$, e) => {
    argvs.push(e.argv.join(' '))
    const a: Answer = e.argv[1] === '--version' ? { stdout: 'codeframe 0.9.7' }
      : e.argv[2] === 'list' ? { stdout: JSON.stringify(ledger) }
        : e.argv[2] === 'status' ? { stdout: JSON.stringify(STATUS(runs)) }
          : e.argv[2] === 'show' ? { stdout: JSON.stringify(SHOW) }
            : e.argv[2] === 'run' ? { exitCode: 1, stdout: JSON.stringify({ failed: true, vacuous: false, empty_reason: null, description: null, requirements: [] }) }
              : { stdout: '' }
    return { value: { exitCode: a.exitCode ?? 0, stdout: a.stdout ?? '', stderr: a.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.open', (_$, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.selection', () => ({ value: undefined }))
  on('session.repo', () => ({ value: { root: '/repo', remote: null, internal: false, name: null } }))
  on('prompt.submit', (_$, e) => {
    submitted.push(e.text)
    return { text: e.text }
  })
  on('ui.render', { component: 'AbovePrompt' }, ($$, e) => h($$.ui.resolve(e).Box, {}) as RenderElement)
  mock.store(on, {})
  return { argvs, submitted, opened }
}

const proof = ($: Engine, args: string) =>
  $.command.run({ command: 'proof', args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 140 } })
const pane = ($: Engine) => $.ui.mount({ plugin: 'proof9', surface: 'terminal', component: 'Pane', requestId: 'proof9', props: PROPS })

describe('opening', () => {
  test('/proof with no text and no selection opens the pane', async ($, on) => {
    const w = world(on)
    await proof($, '')
    expect(w.opened).toEqual(['proof9'])
  })
})

describe('the ledger', () => {
  test('every status is visibly distinct, failing first', async ($, on) => {
    world(on)
    await proof($, '')
    const ui = await pane($)
    const rows = await Promise.all(['REQ-0001', 'REQ-0002', 'REQ-0003', 'REQ-0004', 'REQ-0005'].map(async id =>
      (await ui.find({ key: `req-${id}` }))?.text ?? ''))
    const [satisfied, failing, open, waived, expired] = rows
    expect(failing).toMatch(/FAILING/)
    expect(open).toMatch(/open/)
    expect(satisfied).toMatch(/satisfied/)
    expect(waived).toMatch(/waived/)
    expect(expired).toMatch(/waiver expired/)
    expect(new Set(rows.map(r => r.split(' ')[0])).size).toBe(5)
  })

  test('the header counts obligations and failures (an expired waiver no longer hides one)', async ($, on) => {
    world(on)
    await proof($, '')
    const ui = await pane($)
    expect((await ui.find({ type: 'Text', text: /obligations ·/ }))?.text).toContain('5 obligations · 2 failing')
  })
})

describe('runs', () => {
  test('the last run says when and what, and a vacuous run says it verified nothing', async ($, on) => {
    world(on)
    await proof($, '')
    const ui = await pane($)
    const last = (await ui.find({ type: 'Text', text: /^Last run/ }))?.text ?? ''
    expect(last).toContain('2026-10-16')
    expect(last).toMatch(/nothing verified/i)
  })

  test('the history is one Raster cell per run', async ($, on) => {
    world(on)
    await proof($, '')
    const ui = await pane($)
    const history = await ui.find({ key: 'history' })
    expect(history).toBeDefined()
  })

  test('no runs yet says so', async ($, on) => {
    world(on, LEDGER, [])
    await proof($, '')
    const ui = await pane($)
    expect(await ui.find({ type: 'Text', text: /No runs yet/ })).toBeDefined()
  })
})

describe('detail and buttons', () => {
  test('selecting a requirement shows its evidence with checksum, user text escaped', async ($, on) => {
    world(on)
    await proof($, '')
    const ui = await pane($)
    await ui.press({ key: 'req-REQ-0002' })
    const detail = (await ui.find({ key: 'detail' }))?.text ?? ''
    expect(detail).toContain('abc123')
    expect(detail).toContain('src/auth.py')
    expect(detail).toContain('\\*500s\\*')
    expect(detail).toContain('\\[an\\]')
    // A newline in ledger text cannot start a Markdown block (rule, heading, list).
    const titleLine = detail.split('\n')[0] ?? ''
    expect(titleLine).toContain('Pwned')
    expect(detail).not.toMatch(/^(---|#|1\.)/m)
  })

  test('Ask Claude to fix appears for a failing requirement and queues the prompt', async ($, on) => {
    const w = world(on)
    await proof($, '')
    const ui = await pane($)
    await ui.press({ key: 'req-REQ-0002' })
    await ui.press({ key: 'fix' })
    expect(w.submitted[0]).toContain('REQ-0002')
  })

  test('Run proof and Run full run the CLI and refresh the pane', async ($, on) => {
    const w = world(on)
    await proof($, '')
    const ui = await pane($)
    const before = w.argvs.filter(a => a === 'cf proof list --json').length
    await ui.press({ key: 'run' })
    await ui.press({ key: 'run-full' })
    expect(w.argvs).toContain('cf proof run --json')
    expect(w.argvs).toContain('cf proof run --full --json')
    expect(w.argvs.filter(a => a === 'cf proof list --json').length).toBeGreaterThanOrEqual(before + 2)
  })
})

test('an empty ledger shows the two ways forward', async ($, on) => {
  world(on, { requirements: [] }, [])
  await proof($, '')
  const ui = await pane($)
  const empty = (await ui.find({ type: 'Text', text: /No proof obligations yet/ }))?.text ?? ''
  expect(empty).toContain('/proof <what went wrong>')
  expect(empty).toContain('/proof ratchet')
})

test('the footer carries the /proof usage', async ($, on) => {
  world(on)
  await proof($, '')
  const ui = await pane($)
  expect(await ui.find({ type: 'Text', text: /proof ratchet \[--dry-run\]/ })).toBeDefined()
})

test('on a surface without Raster the history is text', async ($, on) => {
  world(on)
  await proof($, '')
  const ui = await $.ui.mount({ plugin: 'proof9', surface: 'mobile', component: 'Pane', requestId: 'proof9', props: PROPS })
  expect(await ui.find({ type: 'Text', text: /^✓✗○$/ })).toBeDefined()
})
