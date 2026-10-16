import { describe, expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'

type Answer = { exitCode?: number; stdout?: string; stderr?: string } | { deny: string }

const CAPTURED = {
  requirement: {
    id: 'REQ-0005', title: 'Cart total ignores discounts',
    obligations: [{ gate: 'unit', status: 'pending' }],
    scope: { files: ['.'], routes: [], apis: [], components: [], tags: [] },
  },
  stubs: { unit: 'tests/proof/REQ-0005/draft_test_unit.py' },
  workspace_created: false,
  warnings: [],
}

function world(on: On, capture: Answer, opts: { ledger?: boolean; repo?: boolean } = {}) {
  const argvs: (readonly string[])[] = []
  const registered: { name: string; isDeferred?: boolean; required?: unknown }[] = []
  on('process.run', (_$, e) => {
    argvs.push(e.argv)
    const a: Answer = e.argv[2] === 'capture' ? capture : e.argv[1] === '--version' ? { stdout: 'codeframe 0.9.7' } : { stdout: '{"requirements": []}' }
    if ('deny' in a) return a
    return { value: { exitCode: a.exitCode ?? 0, stdout: a.stdout ?? '', stderr: a.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.repo', () => ({ value: opts.repo === false ? null : { root: '/repo', remote: null, internal: false, name: null } }))
  on('fs.stat', (_$, e) =>
    opts.ledger && e.path === '/repo/.codeframe'
      ? { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } }
      : { deny: `ENOENT: ${e.path}` },
  )
  on('tool.register', (_$, e) => {
    registered.push({ name: e.name, isDeferred: e.isDeferred, required: (e.inputSchema as { required?: unknown } | undefined)?.required })
    return { value: { tool: `mcp__proof9__${e.name}` } }
  })
  on('command.register', (_$, e) => ({ value: { command: e.name } }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('prompt.compose', () => ({ sections: [{ id: 'core:base', text: 'base', scope: 'session' }] }))
  return { argvs, registered }
}

const json = (doc: unknown, exitCode = 0): Answer => ({ exitCode, stdout: JSON.stringify(doc) })
const start = ($: Engine) => $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
const capture = ($: Engine, input: Record<string, unknown>) =>
  $.tool.call({ tool: 'mcp__proof9__capture', ...input } as Parameters<Engine['tool']['call']>[0])
const compose = ($: Engine) =>
  $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: ['terminal'], tools: [], outputStyle: null, traits: [] })

describe('the capture tool', () => {
  test('is registered for Claude from the start, title and description required', async ($, on) => {
    const w = world(on, json(CAPTURED))
    await start($)
    expect(w.registered).toEqual([{ name: 'capture', isDeferred: false, required: ['title', 'description'] }])
  })

  test('captures through cf with every field as its own argument', async ($, on) => {
    const w = world(on, json(CAPTURED))
    await start($)
    const out = await capture($, {
      title: 'Cart total ignores discounts',
      description: 'Expected 90 after a 10% discount, got 100',
      where: 'src/cart.py',
      severity: 'high',
    })
    expect(w.argvs.find(a => a[2] === 'capture')).toEqual([
      'cf', 'proof', 'capture', '--json',
      '--title', 'Cart total ignores discounts',
      '--description', 'Expected 90 after a 10% discount, got 100',
      '--where', 'src/cart.py',
      '--severity', 'high',
      '--source', 'qa',
    ])
    expect(out.deny).toBeUndefined()
    expect(JSON.stringify(out.result)).toContain('REQ-0005')
    expect(JSON.stringify(out.result)).toContain('tests/proof/REQ-0005/draft_test_unit.py')
  })

  test('defaults: the repo root as scope, medium severity', async ($, on) => {
    const w = world(on, json(CAPTURED))
    await start($)
    await capture($, { title: 't', description: 'd' })
    const argv = w.argvs.find(a => a[2] === 'capture') ?? []
    expect(argv[argv.indexOf('--where') + 1]).toBe('/repo')
    expect(argv[argv.indexOf('--severity') + 1]).toBe('medium')
  })

  test('hostile text stays one argument', async ($, on) => {
    const w = world(on, json(CAPTURED))
    await start($)
    const hostile = '"; rm -rf ~ #`whoami` $(id) --severity critical'
    await capture($, { title: hostile, description: hostile })
    const argv = w.argvs.find(a => a[2] === 'capture') ?? []
    expect(argv[argv.indexOf('--title') + 1]).toBe(hostile)
    expect(argv[argv.indexOf('--description') + 1]).toBe(hostile)
    expect(argv.filter(a => a === '--severity').length).toBe(1)
  })

  test('a missing title or description is refused without running cf', async ($, on) => {
    const w = world(on, json(CAPTURED))
    await start($)
    const out = await capture($, { title: '  ', description: 'd' })
    expect(out.deny).toMatch(/title/i)
    expect(w.argvs.some(a => a[2] === 'capture')).toBe(false)
  })

  test('an unknown severity is refused without running cf', async ($, on) => {
    const w = world(on, json(CAPTURED))
    await start($)
    const out = await capture($, { title: 't', description: 'd', severity: 'urgent' })
    expect(out.deny).toMatch(/severity/i)
    expect(w.argvs.some(a => a[2] === 'capture')).toBe(false)
  })

  test('a missing cf gives Claude the install command', async ($, on) => {
    world(on, { deny: 'failed to start: ENOENT: Executable not found in $PATH: "cf"' })
    await start($)
    const out = await capture($, { title: 't', description: 'd' })
    expect(out.deny).toContain('uv tool install codeframe-ai')
  })

  test('a refused capture tells Claude why', async ($, on) => {
    world(on, { exitCode: 1, stderr: 'Error: not inside a git repository' })
    await start($)
    const out = await capture($, { title: 't', description: 'd' })
    expect(out.deny).toContain('not inside a git repository')
  })
})

describe('the system-prompt section', () => {
  test('is added in a repository with a proof ledger', async ($, on) => {
    world(on, json(CAPTURED), { ledger: true })
    const out = await compose($)
    const ours = out.sections.find(s => s.id === 'proof9:ledger')
    expect(out.sections[0]?.id).toBe('core:base')
    expect(ours?.scope).toBe('session')
    expect(ours?.text).toContain('mcp__proof9__capture')
    expect(ours?.text).toMatch(/fix the code, not the test/i)
    expect((ours?.text ?? '').split('\n').length).toBeLessThanOrEqual(6)
  })

  test('is absent without a ledger', async ($, on) => {
    world(on, json(CAPTURED), { ledger: false })
    const out = await compose($)
    expect(out.sections.map(s => s.id)).toEqual(['core:base'])
  })

  test('is absent outside a git repository', async ($, on) => {
    world(on, json(CAPTURED), { repo: false })
    const out = await compose($)
    expect(out.sections.map(s => s.id)).toEqual(['core:base'])
  })
})
