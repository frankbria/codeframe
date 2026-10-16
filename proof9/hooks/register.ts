import type { EngineInterface, Register } from 'claude-code'

// The CLI is the product; this plugin is a front door. Every call is `cf … --json`
// by argv (no shell), and nothing here repeats what the CLI decides.

const MIN_VERSION = [0, 9, 7] as const // first release with `cf proof … --json` (#1488)
const INSTALL = 'uv tool install codeframe-ai'
const UPGRADE = 'uv tool upgrade codeframe-ai'
const ENV = { CODEFRAME_CLIENT: 'proof9' }
const TITLE_MAX = 80

const USAGE = [
  'Usage:',
  '  /proof <what went wrong>   capture a bug as a permanent proof obligation',
  '  /proof                     capture the text you selected in the transcript',
  '  /proof ratchet [--dry-run] lock in every test that passes today',
].join('\n')

type Ran = { exitCode: number; stdout: string; stderr: string }

/** Runs `cf <args>`; `{ failed }` when cf cannot start (not installed) or times out. */
async function cf($: EngineInterface, args: string[], timeoutMs?: number): Promise<Ran | { failed: string }> {
  try {
    return await $.process.run(['cf', ...args], { env: ENV, timeoutMs })
  } catch (err) {
    return { failed: err instanceof Error ? err.message : String(err) }
  }
}

function cannotRun(failed: string): string {
  return `proof9 could not run the codeframe CLI (${failed}).\nInstall it with: ${INSTALL}`
}

function parse<T>(ran: Ran): T | null {
  try {
    return JSON.parse(ran.stdout) as T
  } catch {
    return null
  }
}

function errorText(ran: Ran): string {
  return (ran.stderr || ran.stdout).trim() || `cf exited ${ran.exitCode}`
}

type Captured = {
  requirement: { id: string; title: string; obligations: { gate: string }[] }
  stubs: Record<string, string>
  workspace_created: boolean
  warnings: string[]
}

async function capture($: EngineInterface, text: string): Promise<string> {
  const title = (text.split('\n').find(line => line.trim()) ?? text).trim().slice(0, TITLE_MAX)
  // The repo root scopes the requirement to the whole repository (fail closed).
  const where = (await $.session.repo())?.root ?? '.'
  const ran = await cf($, [
    'proof', 'capture', '--json',
    '--title', title,
    '--description', text,
    '--where', where,
    '--severity', 'medium',
    '--source', 'qa',
  ])
  if ('failed' in ran) return cannotRun(ran.failed)
  const doc = ran.exitCode === 0 ? parse<Captured>(ran) : null
  if (!doc) return `cf proof capture failed:\n${errorText(ran)}`

  const req = doc.requirement
  const lines = [
    `✓ ${req.id} captured: ${req.title}`,
    `  Obligations: ${req.obligations.map(o => o.gate).join(', ')}`,
  ]
  const stubs = Object.values(doc.stubs)
  if (stubs.length) lines.push(`  Test stubs: ${stubs.join(', ')}`)
  for (const warning of doc.warnings) lines.push(`  ⚠ ${warning}`)
  if (doc.workspace_created) lines.push('Created .codeframe/ in this repository.')
  lines.push('Implement the stub tests, then run `cf proof run` to enforce it.')
  return lines.join('\n')
}

type Ratcheted = {
  dry_run: boolean
  locked: Record<string, string[]>
  already_locked: string[]
  failed: string[]
  skipped: string[]
  unenforceable: string[]
  per_test_scope: boolean
}

async function ratchet($: EngineInterface, dryRun: boolean): Promise<string> {
  $.ui.toast('proof9: running your test suite to find the tests that pass today…')
  const ran = await cf($, ['proof', 'ratchet', '--json', ...(dryRun ? ['--dry-run'] : [])], 600_000)
  if ('failed' in ran) return cannotRun(ran.failed)
  // Exit 2 with a document is "nothing to lock"; anything else non-zero is an error.
  const doc = ran.exitCode === 0 || ran.exitCode === 2 ? parse<Ratcheted>(ran) : null
  if (!doc) return `cf proof ratchet failed:\n${errorText(ran)}`

  const n = Object.keys(doc.locked).length
  const tests = n === 1 ? 'test' : 'tests'
  const lines: string[] = []
  if (ran.exitCode === 2) lines.push('Nothing to lock: no passing tests found.')
  else if (doc.dry_run) lines.push(`Would lock in ${n} passing ${tests} (dry run: nothing written).`)
  else if (n) lines.push(`✓ Locked in ${n} passing ${tests} as proof obligations.`)
  else lines.push('Every passing test is already locked in.')

  if (n && doc.already_locked.length) lines.push(`${doc.already_locked.length} already locked.`)
  const notLocked = [
    doc.failed.length ? `${doc.failed.length} failed` : '',
    doc.skipped.length ? `${doc.skipped.length} skipped` : '',
  ].filter(Boolean)
  if (notLocked.length) lines.push(`Not locked: ${notLocked.join(', ')}.`)
  if (doc.unenforceable.length) {
    lines.push(`Not locked (a rule can only name tests starting with test_): ${doc.unenforceable.join(', ')}`)
  }
  if (n && !doc.per_test_scope) {
    lines.push('⚠ Each is scoped to the whole repository: install pytest-cov to scope each to the files its test covers.')
  }
  if (n && !doc.dry_run) lines.push('Run `cf proof run --full` to record their evidence.')
  return lines.join('\n')
}

function parseVersion(text: string): number[] | null {
  const match = /(\d+)\.(\d+)\.(\d+)/.exec(text)
  return match ? match.slice(1, 4).map(Number) : null
}

function isOlder(found: number[], min: readonly number[]): boolean {
  for (let i = 0; i < min.length; i++) {
    const a = found[i] ?? 0
    const b = min[i] ?? 0
    if (a !== b) return a < b
  }
  return false
}

async function checkVersion($: EngineInterface): Promise<void> {
  const ran = await cf($, ['--version'])
  if ('failed' in ran) {
    $.ui.toast(`proof9 needs the codeframe CLI. Install it with: ${INSTALL}`)
    return
  }
  const found = parseVersion(ran.stdout)
  if (found && isOlder(found, MIN_VERSION)) {
    $.ui.toast(`proof9 needs codeframe ${MIN_VERSION.join('.')} or later; found ${found.join('.')}. Run: ${UPGRADE}`)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'proof',
      description: 'Capture a bug as a permanent proof obligation (or: /proof ratchet)',
      argumentHint: '<what went wrong> | ratchet [--dry-run]',
    })
    await checkVersion($)
    return next(e)
  })

  on('command.run', { command: 'proof' }, async ($, e) => {
    const args = e.args.trim()
    const ratchetArgs = /^ratchet(?:\s+(--dry-run))?$/.exec(args)
    if (ratchetArgs) return { text: await ratchet($, Boolean(ratchetArgs[1])) }
    const text = args || (await $.ui.selection())?.text.trim()
    if (!text) return { text: USAGE }
    return { text: await capture($, text) }
  })
}
