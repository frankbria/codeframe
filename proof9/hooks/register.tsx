import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Failing, LedgerRequirement, RunSummary } from '../types'
import { isGitCommit, runsCfProof } from './commit.ts'

const failingAtom = atom({ plugin: 'proof9', key: 'failing' } as const, [])
const dismissedAtom = atom({ plugin: 'proof9', key: 'dismissed' } as const, [])
const emptyAtom = atom({ plugin: 'proof9', key: 'emptyLedger' } as const, false)
const waivingAtom = atom({ plugin: 'proof9', key: 'waiving' } as const, null)
const ledgerAtom = atom({ plugin: 'proof9', key: 'ledger' } as const, [])
const runsAtom = atom({ plugin: 'proof9', key: 'runs' } as const, [])
const selectedAtom = atom({ plugin: 'proof9', key: 'selected' } as const, null)
const detailAtom = atom({ plugin: 'proof9', key: 'detail' } as const, null)
const PANE = 'proof9'

// The CLI is the product; this plugin is a front door. Every call is `cf … --json`
// by argv (no shell), and nothing here repeats what the CLI decides.

const MIN_VERSION = [0, 9, 7] as const // first release with `cf proof … --json` (#1488)
const INSTALL = 'uv tool install codeframe-ai'
const UPGRADE = 'uv tool upgrade codeframe-ai'
const ENV = { CODEFRAME_CLIENT: 'proof9' }
const TITLE_MAX = 80

const USAGE = [
  'Usage:',
  '  /proof <what went wrong>                  capture a bug as a permanent proof obligation',
  '  /proof                                    capture the text you selected in the transcript',
  '  /proof ratchet [--dry-run] [--path GLOB]  lock in every test that passes today',
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
  // Only a cf that never started is a missing install; a timeout is not.
  if (/ENOENT|not found/i.test(failed)) {
    return `proof9 could not run the codeframe CLI (${failed}).\nInstall it with: ${INSTALL}`
  }
  return `cf did not finish: ${failed}`
}

/** `ratchet [--dry-run] [--path GLOB]` as cf flags; undefined when not a ratchet; null when malformed. */
function ratchetFlags(args: string): string[] | null | undefined {
  const [first, ...rest] = args.split(/\s+/)
  // "ratchet" followed by words is a description that happens to start with it.
  if (first !== 'ratchet' || (rest.length && !rest[0]?.startsWith('-'))) return undefined
  const flags: string[] = []
  for (let i = 0; i < rest.length; i++) {
    const token = rest[i]
    if (token === '--dry-run') flags.push(token)
    // A flag in the glob's place would make cf take it as the glob: `--path --dry-run` ran for real.
    else if (token === '--path' && rest[i + 1] && !rest[i + 1]?.startsWith('-')) flags.push(token, rest[++i] ?? '')
    else return null
  }
  return flags
}

/** A hook call that may be unavailable on a surface; undefined instead of a throw. */
async function attempt<T>(call: () => Promise<T>): Promise<T | undefined> {
  try {
    return await call()
  } catch {
    return undefined
  }
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

const SEVERITIES = ['critical', 'high', 'medium', 'low']

type CaptureFields = { title: string; description: string; where?: string; severity?: string }

/** `cf proof capture --json`; the summary on success, or what went wrong. */
async function captureWith($: EngineInterface, f: CaptureFields): Promise<{ ok: boolean; text: string }> {
  // The repo root scopes the requirement to the whole repository (fail closed).
  const where = f.where?.trim() || (await attempt(() => $.session.repo()))?.root || '.'
  const ran = await cf($, [
    'proof', 'capture', '--json',
    '--title', f.title,
    '--description', f.description,
    '--where', where,
    '--severity', f.severity ?? 'medium',
    '--source', 'qa',
  ])
  if ('failed' in ran) return { ok: false, text: cannotRun(ran.failed) }
  const doc = ran.exitCode === 0 ? parse<Captured>(ran) : null
  if (!doc) return { ok: false, text: `cf proof capture failed:\n${errorText(ran)}` }

  // Words for someone who has read nothing (#1473): no "obligations" or "stubs".
  const req = doc.requirement
  const gates = req.obligations.map(o => o.gate)
  const kinds = gates.length > 1 ? `${gates.slice(0, -1).join(', ')} and ${gates.at(-1)}` : gates[0] ?? 'its'
  const lines = [`✓ ${req.id} captured: ${req.title}`, `It will be checked by ${kinds} tests.`]
  const stubs = Object.values(doc.stubs)
  if (stubs.length) lines.push('Draft tests were written for you; fill them in so they fail on the bug and pass on the fix:', ...stubs.map(s => `  ${s}`))
  for (const warning of doc.warnings) lines.push(`⚠ ${warning}`)
  lines.push('Then run `cf proof run` to record the proof. From then on, proof9 checks it before every commit.')
  if (doc.workspace_created) lines.push('(Created .codeframe/ in this repository: that is where proof9 keeps its ledger.)')
  return { ok: true, text: lines.join('\n') }
}

async function capture($: EngineInterface, text: string): Promise<string> {
  const first = (text.split('\n').find(line => line.trim()) ?? text).trim()
  const title = Array.from(first).slice(0, TITLE_MAX).join('').trim()
  return (await captureWith($, { title, description: text })).text
}

const CAPTURE_TOOL = {
  name: 'capture',
  description:
    'Capture a bug as a permanent proof requirement in this repository\'s ledger (cf proof capture): ' +
    'it creates the requirement and test stubs that keep the bug fixed. Use it after fixing a regression ' +
    'or a reported bug, with the person\'s agreement.',
  inputSchema: {
    type: 'object',
    properties: {
      title: { type: 'string', description: 'Short statement of what went wrong' },
      description: { type: 'string', description: 'What happened: expected versus actual' },
      where: { type: 'string', description: 'File, directory, route or API it happened in (default: the whole repository)' },
      severity: { type: 'string', enum: SEVERITIES, description: 'Default: medium' },
    },
    required: ['title', 'description'],
  },
  isDeferred: false,
}

// Told to Claude in a repository with a proof ledger: a few lines, no requirement list.
const LEDGER_SECTION = {
  id: 'proof9:ledger',
  scope: 'session' as const,
  text: [
    'This repository keeps a PROOF9 ledger: requirements proven to hold, each enforced by named tests (cf proof).',
    'After you fix a regression or a reported bug, offer to capture it with the mcp__proof9__capture tool so it stays fixed.',
    'When a commit or `cf proof run` reports a failing requirement, fix the code, not the test: never weaken, skip or delete a proof test.',
  ].join('\n'),
}

async function hasLedger($: EngineInterface): Promise<boolean> {
  const root = (await attempt(() => $.session.repo()))?.root
  return Boolean(root && (await attempt(() => $.fs.stat(`${root}/.codeframe`)))?.kind === 'dir')
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

async function ratchet($: EngineInterface, flags: string[]): Promise<string> {
  $.ui.toast('proof9: running your test suite to find the tests that pass today…')
  const ran = await cf($, ['proof', 'ratchet', '--json', ...flags], 600_000)
  if ('failed' in ran) return cannotRun(ran.failed)
  // Exit 2 with a document is "nothing to lock"; anything else non-zero is an error.
  const doc = ran.exitCode === 0 || ran.exitCode === 2 ? parse<Ratcheted>(ran) : null
  if (!doc) return `cf proof ratchet failed:\n${errorText(ran)}`

  const n = Object.keys(doc.locked).length
  const tests = n === 1 ? 'test' : 'tests'
  const lines: string[] = []
  if (ran.exitCode === 2) lines.push('Nothing to lock: no passing tests found.')
  else if (doc.dry_run && n) lines.push(`Would lock in ${n} passing ${tests} (dry run: nothing written).`)
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

/** Toasts what is wrong with the installed cf; true when it is usable. */
async function checkVersion($: EngineInterface): Promise<boolean> {
  const ran = await cf($, ['--version'], 10_000)
  if ('failed' in ran) {
    $.ui.toast(`proof9 needs the codeframe CLI. Install it with: ${INSTALL}`)
    return false
  }
  if (ran.exitCode !== 0) {
    $.ui.toast(`proof9: \`cf --version\` failed (${errorText(ran).split('\n')[0]}). Try: ${UPGRADE}`)
    return false
  }
  const found = parseVersion(ran.stdout)
  if (found && isOlder(found, MIN_VERSION)) {
    $.ui.toast(`proof9 needs codeframe ${MIN_VERSION.join('.')} or later; found ${found.join('.')}. Run: ${UPGRADE}`)
    return false
  }
  return true
}

type Listed = { requirements: LedgerRequirement[]; runs?: RunSummary[] }

const failureKey = (f: Failing) => `${f.id}:${f.tests.join(',')}`

async function emptyHiddenKey($: EngineInterface): Promise<string> {
  // Outside a git repo, the directory: a shared empty key would hide the band everywhere.
  const root = (await attempt(() => $.session.repo()))?.root ?? (await attempt(() => $.session.cwd()))
  return `emptyHidden:${root ?? ''}`
}

/**
 * Reads the ledger and refreshes everything drawn from it: the status line
 * (`proof9 · N obligations · M failing`) and the band. The ledger, not the last
 * run, is the source: a scoped run that does not touch a still-failing
 * requirement must not clear its band.
 */
async function refreshLedger($: EngineInterface): Promise<void> {
  const ran = await cf($, ['proof', 'list', '--json'], 10_000)
  const doc = 'failed' in ran || ran.exitCode !== 0 ? null : parse<Listed>(ran)
  // A ledger that cannot be read leaves the last known state: a transient error
  // must not make a failing requirement's band vanish.
  if (!doc) return
  const reqs = doc.requirements
  // Failing as `cf proof status` counts it (#1488): not waived, a failed obligation.
  // A lapsed waiver no longer covers it — read-only, as the merge gate decides
  // (#1276); `list`, unlike `status`, does not revert the stored status.
  const failing: Failing[] = reqs.filter(isFailing).map(toFailing)
  const noun = reqs.length === 1 ? 'obligation' : 'obligations'
  $.ui.status(reqs.length ? `proof9 · ${reqs.length} ${noun} · ${failing.length} failing` : 'proof9 · no obligations yet')
  await update($, failingAtom, () => failing)
  await update($, ledgerAtom, () => reqs)
  if (doc.runs) await update($, runsAtom, () => doc.runs ?? [])
  // A dismissal ends with its failure, so a later regression shows again.
  const live = new Set(failing.map(failureKey))
  await update($, dismissedAtom, keys => keys.filter(k => live.has(k)))
  const hidden = Boolean(await attempt(async () => $.store.get(await emptyHiddenKey($))))
  await update($, emptyAtom, () => reqs.length === 0 && !hidden)
}

function toFailing(r: LedgerRequirement): Failing {
  const gates = r.obligations.filter(o => o.status === 'failed').map(o => o.gate)
  const tests = r.evidence_rules.filter(t => t.gate !== null && gates.includes(t.gate)).map(t => t.test_id)
  return { id: r.id, title: r.title, tests: tests.length ? tests : gates.map(g => `the ${g} gate (no named test)`) }
}

const isWaived = (r: LedgerRequirement) => r.status === 'waived' && !r.waiver?.expired
/** Failing as `cf proof status` counts it (#1488); a lapsed waiver no longer covers it (#1276). */
const isFailing = (r: LedgerRequirement) => !isWaived(r) && r.obligations.some(o => o.status === 'failed')


/** One pane row: a symbol and a word per status, so none is told apart by color alone. */
function rowLabel(r: LedgerRequirement): string {
  const mark = r.status === 'waived' && r.waiver?.expired ? `! waiver expired${isFailing(r) ? ' · FAILING' : ''}`
    : isFailing(r) ? '✗ FAILING'
      : r.status === 'waived' ? '– waived'
        : r.status === 'satisfied' ? '✓ satisfied'
          : '○ open'
  return `${mark}  ${r.id}  ${r.title}`
}

const rowOrder = (r: LedgerRequirement) =>
  isFailing(r) ? 0 : r.status === 'open' ? 1 : r.status === 'satisfied' ? 2 : 3

/** Ledger text made safe inside the plugin's Markdown: on one line, so it can never start a
 *  block (a rule, heading or list), with mid-line markup characters escaped. Shown, never rendered. */
const md = (text: string) => text.replace(/\s*\n\s*/g, ' ').replace(/([\\`*_[\]()#|<>~])/g, '\\$1')

type Shown = {
  requirement: LedgerRequirement & {
    severity: string
    source: string
    scope: Record<string, string[]>
    waiver: { reason: string; expires: string | null; expired: boolean; approved_by: string } | null
  }
  evidence: { gate: string; status: string; artifact_checksum: string; run_id: string; timestamp: string | null }[]
}

async function selectRequirement($: EngineInterface, id: string): Promise<void> {
  await update($, selectedAtom, () => id)
  await update($, detailAtom, () => null) // no previous detail under the new row
  const ran = await cf($, ['proof', 'show', id, '--json'])
  // A later selection that answered first wins: never show one requirement's
  // evidence under another's name.
  if ((await read($, selectedAtom)) !== id) return
  const doc = 'failed' in ran || ran.exitCode !== 0 ? null : parse<Shown>(ran)
  if (!doc) {
    await update($, detailAtom, () => `Could not read ${md(id)}: ${md('failed' in ran ? ran.failed : errorText(ran))}`)
    return
  }
  const r = doc.requirement
  const scope = Object.entries(r.scope).filter(([, v]) => v.length).map(([k, v]) => `${k}: ${v.map(md).join(', ')}`)
  const lines = [
    `**${md(r.id)}** — ${md(r.title)}`,
    `Status: ${md(r.status)} · severity ${md(r.severity)} · source ${md(r.source)}`,
    `Scope: ${scope.join('; ') || 'none'}`,
    `Obligations: ${r.obligations.map(o => `${md(o.gate)} ${md(o.status)}`).join(', ') || 'none'}`,
    '',
    doc.evidence.length ? '**Evidence**' : 'No evidence recorded yet.',
    ...doc.evidence.slice(0, 10).map(e =>
      `- ${md(e.gate)} **${md(e.status)}** · checksum \`${e.artifact_checksum}\` · run ${md(e.run_id)} · ${md(e.timestamp ?? '')}`),
  ]
  if (r.waiver) {
    lines.push('', `**Waiver** (${r.waiver.expired ? 'expired' : 'in force'}): ${md(r.waiver.reason)}` +
      ` · approved by ${md(r.waiver.approved_by || 'unknown')}${r.waiver.expires ? ` · expires ${md(r.waiver.expires)}` : ''}`)
  }
  await update($, detailAtom, () => lines.join('\n'))
}

/** One cell per run, oldest first: green passed, red failed, yellow verified nothing. */
function historyCells(runs: RunSummary[], columns: number): string {
  const shown = runs.slice(0, columns).reverse()
  const words = new Uint32Array(shown.length * 3)
  shown.forEach((run, i) => {
    words.set([0x2588, run.vacuous ? 0xccaa00 : run.passed ? 0x22aa55 : 0xdd3333, 0x01000000], i * 3)
  })
  let binary = ''
  for (const byte of new Uint8Array(words.buffer)) binary += String.fromCharCode(byte)
  return btoa(binary)
}

async function runProof($: EngineInterface, full: boolean): Promise<void> {
  const ran = await cf($, ['proof', 'run', ...(full ? ['--full'] : []), '--json'], 600_000)
  if ('failed' in ran) $.ui.toast(cannotRun(ran.failed).replace(/\n/g, ' '))
  await refreshLedger($)
  const selected = await read($, selectedAtom)
  if (selected) await selectRequirement($, selected)
}

/** Appends a notice to the transcript: the person reads it, the model does not. */
async function notice($: EngineInterface, text: string): Promise<void> {
  await $.session.append({ message: { type: 'system', content: [{ type: 'text', text }] } })
}

async function askToFix($: EngineInterface, failing: Failing[]): Promise<void> {
  const list = failing.map(f => `- ${f.id} "${f.title}": ${f.tests.join(', ')}`).join('\n')
  await $.prompt.submit({
    text: `proof9: these proven requirements fail:\n${list}\nFix the code so these tests pass again; do not weaken or delete the tests. Then run \`cf proof run\` to re-check them.`,
  })
}

async function showEvidence($: EngineInterface, id: string): Promise<void> {
  // shortcut: plain `cf proof show` text until the /proof pane (#1491) draws it.
  const ran = await cf($, ['proof', 'show', id])
  await notice($, 'failed' in ran ? cannotRun(ran.failed) : (ran.stdout || errorText(ran)).trim())
}

async function waive($: EngineInterface, id: string, typed: string): Promise<void> {
  const m = /^(.*?)\s+until\s+(\d{4}-\d{2}-\d{2})\s*$/.exec(typed.trim())
  const reason = (m?.[1] ?? typed).trim()
  if (!reason) {
    $.ui.toast('proof9: a reason is required to waive a requirement.')
    return
  }
  const ran = await cf($, ['proof', 'waive', id, '--reason', reason, ...(m ? ['--expires', m[2] ?? ''] : [])])
  if ('failed' in ran || ran.exitCode !== 0) {
    // Keep the input open with what was typed; say why it was refused.
    $.ui.toast(`proof9 could not waive ${id}: ${'failed' in ran ? ran.failed : errorText(ran)}`)
    return
  }
  await update($, waivingAtom, () => null)
  await refreshLedger($)
}

type ProofRun = {
  failed: boolean
  vacuous: boolean
  empty_reason: string | null
  description: string | null
  requirements: { id: string; title: string; gates: { gate: string; outcome: string; tests: string[] }[] }[]
}

/** What a pre-commit proof run found, in the words each audience needs. */
type Verdict =
  | { kind: 'failing'; person: string; claude: string; deny: string }
  | { kind: 'note'; person: string }
  | { kind: 'error'; person: string }
  | { kind: 'quiet' }

async function preCommitVerdict($: EngineInterface, timeoutSeconds: number): Promise<Verdict> {
  // Plain `cf proof run`: its scope is the working tree (modified + staged +
  // untracked), a superset of what the commit holds, so it checks more, never less.
  const ran = await cf($, ['proof', 'run', '--json'], timeoutSeconds * 1000)
  if ('failed' in ran) {
    if (/timed out/i.test(ran.failed)) {
      return { kind: 'error', person: `the proof run was cut short after ${timeoutSeconds} s` }
    }
    return { kind: 'error', person: cannotRun(ran.failed).replace(/\n/g, ' ') }
  }
  const doc = parse<ProofRun>(ran)
  // Exit 1 means a failure: without `failed: true` beside it the document is not
  // one we can read, and block mode must not wave the commit through.
  if (!doc || typeof doc.failed !== 'boolean' || ![0, 1, 2].includes(ran.exitCode) || (ran.exitCode === 1 && !doc.failed)) {
    return { kind: 'error', person: `cf proof run failed: ${errorText(ran).split('\n')[0]}` }
  }
  if (doc.failed) {
    const broken = doc.requirements
      .map(r => ({ ...r, tests: r.gates.filter(g => g.outcome === 'failed').flatMap(g => g.tests.length ? g.tests : [`${g.gate} gate`]) }))
      .filter(r => r.tests.length)
    const list = broken.map(r => `${r.id} "${r.title}": ${r.tests.join(', ')} failed`)
    if (!list.length) list.push('the proof run reported a failure; run `cf proof run` to see it')
    return {
      kind: 'failing',
      person: !broken.length
        ? 'proof9: the proof run reported a failure'
        : broken.length === 1
          ? `proof9: this breaks ${broken[0]?.id} "${broken[0]?.title}", which was proven to work. Claude has been told which test fails; the commit went ahead.`
          : `proof9: this breaks ${broken.length} requirements that were proven to work (${broken.map(r => r.id).join(', ')}). Claude has been told which tests fail; the commit went ahead.`,
      // The run checks the working tree, which can hold more than the commit.
      claude: [
        'proof9: your working tree breaks requirements that were proven to hold:',
        ...list.map(l => `- ${l}`),
        'Fix the code so these tests pass again; do not weaken or delete the tests. `cf proof run` re-checks them.',
      ].join('\n'),
      deny: `proof9 blocked the commit; in your working tree ${list.join('; ')}. Fix the failure, or set proof9's mode to warn.`,
    }
  }
  if (doc.empty_reason === 'no_requirements') {
    return { kind: 'note', person: 'proof9 has nothing to check yet. Capture a bug with /proof, or lock in the tests that pass today with /proof ratchet.' }
  }
  if (doc.vacuous || ran.exitCode === 2) {
    return { kind: 'note', person: `proof9: nothing was verified${doc.description ? ` (${doc.description})` : ''}; this is not a pass.` }
  }
  return { kind: 'quiet' }
}

export const register: Register = (on, options) => {
  const block = options.mode === 'block'
  const limit = options.timeoutSeconds
  const timeoutSeconds = typeof limit === 'number' && limit > 0 ? limit : 120

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'proof',
      description: 'Capture a bug as a permanent proof obligation (or: /proof ratchet)',
      argumentHint: '<what went wrong> | ratchet [--dry-run]',
    })
    // A tool that cannot be registered must not cost the rest of session start.
    await attempt(() => $.tool.register(CAPTURE_TOOL))
    if (await checkVersion($)) await refreshLedger($)
    return next(e)
  })

  on('tool.call', { tool: 'mcp__proof9__capture' }, async ($, e) => {
    const input = e as unknown as Partial<Record<'title' | 'description' | 'where' | 'severity', unknown>>
    const str = (v: unknown) => (typeof v === 'string' ? v.trim() : '')
    const fields = { title: str(input.title), description: str(input.description), where: str(input.where), severity: str(input.severity) || undefined }
    if (!fields.title || !fields.description) return { deny: 'proof9 capture needs a title and a description.' }
    if (fields.severity && !SEVERITIES.includes(fields.severity)) {
      return { deny: `proof9 capture: severity must be one of ${SEVERITIES.join(', ')}.` }
    }
    const captured = await captureWith($, fields)
    if (!captured.ok) return { deny: captured.text }
    await attempt(() => refreshLedger($))
    return { result: captured.text }
  }).catch(() => ({ deny: 'proof9 capture failed unexpectedly; run `cf proof capture` to see why.' }))

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    return (await hasLedger($)) ? { ...composed, sections: [...composed.sections, LEDGER_SECTION] } : composed
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (!isGitCommit(e.command)) {
      if (!runsCfProof(e.command)) return next(e)
      // Claude ran the proof itself (say, after "Ask Claude to fix"): redraw from the ledger.
      const ran = await next(e)
      await attempt(() => refreshLedger($))
      return ran
    }
    const verdict = await preCommitVerdict($, timeoutSeconds)
    if (verdict.kind === 'error' && block) {
      return { deny: `proof9 could not check this commit (${verdict.person}); block mode fails closed.` }
    }
    if (verdict.kind === 'failing' && block) {
      $.ui.toast(verdict.deny)
      await attempt(() => refreshLedger($))
      return { deny: verdict.deny }
    }
    if (verdict.kind !== 'quiet') {
      $.ui.toast(verdict.kind === 'error' ? `proof9 could not check this commit: ${verdict.person}` : verdict.person)
    }
    const ran = await next(e)
    await attempt(() => refreshLedger($))
    // Warn mode: Claude reads the failures after the commit's own output and can fix them now.
    return verdict.kind === 'failing' && ran.deny === undefined
      ? { ...ran, context: [...(ran.context ?? []), verdict.claude] }
      : ran
  }).catch(($, e, next) =>
    next.called || !block ? next(e) : { deny: 'proof9: its pre-commit check failed; block mode fails closed.' },
  )

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const table = $.ui.resolve(e)
    const { Box, Button, Text } = table
    // Mobile has no Input (the API's surface tables): no waive form there.
    const Input = e.surface !== 'mobile' ? $.ui.resolve(e).Input : undefined
    const dismissed = await read($, dismissedAtom)
    const shown = (await read($, failingAtom)).filter(f => !dismissed.includes(failureKey(f)))
    const first = shown[0]
    if (first) {
      if (Input && (await read($, waivingAtom)) === first.id) {
        return (
          <Box>
            <Text>Waive {first.id}: </Text>
            <Input
              key="waive-reason"
              placeholder="reason (required); add ' until YYYY-MM-DD' for an expiry"
              autoFocus
              onSubmit={value => waive($, first.id, value)}
            />
            <Button key="cancel" label="Cancel" onPress={() => update($, waivingAtom, () => null)} />
          </Box>
        )
      }
      const more = shown.length > 1 ? ` (+${shown.length - 1} more)` : ''
      return (
        <Box flexDirection="column">
          <Text color="red">
            proof9: {first.id} "{first.title}" fails: {first.tests.join(', ')}{more}
          </Text>
          <Box>
            <Button key="fix" label="Ask Claude to fix" variant="primary" onPress={() => askToFix($, shown)} />
            <Button key="evidence" label="Show evidence" onPress={() => showEvidence($, first.id)} />
            {Input ? <Button key="waive" label="Waive…" onPress={() => update($, waivingAtom, () => first.id)} /> : null}
            <Button
              key="dismiss"
              label="Dismiss"
              role="dismiss"
              onPress={() => update($, dismissedAtom, keys => [...keys, failureKey(first)])}
            />
          </Box>
        </Box>
      )
    }
    if (await read($, emptyAtom)) {
      return (
        <Box>
          <Text>proof9: No proof obligations yet. </Text>
          <Button
            key="ratchet"
            label="Lock in passing tests"
            variant="primary"
            onPress={async () => {
              await notice($, await ratchet($, []))
              await refreshLedger($)
            }}
          />
          <Button key="capture" label="Capture a bug" onPress={() => $.prompt.fill({ text: '/proof ' })} />
          <Button
            key="dismiss-empty"
            label="Dismiss"
            role="dismiss"
            onPress={async () => {
              await $.store.set(await emptyHiddenKey($), true)
              await update($, emptyAtom, () => false)
            }}
          />
        </Box>
      )
    }
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const table = $.ui.resolve(e)
    const { Box, Button, Markdown, Text } = table
    // Raster is the terminal's alone (the API's surface tables); others get text.
    const Raster = e.surface === 'terminal' ? $.ui.resolve(e).Raster : undefined
    const ledger = [...(await read($, ledgerAtom))].sort((a, b) => rowOrder(a) - rowOrder(b))
    const runs = await read($, runsAtom)
    const selected = await read($, selectedAtom)
    const detail = await read($, detailAtom)
    const failing = ledger.filter(isFailing)
    const last = runs[0]
    const lastWord = !last ? '' : last.vacuous ? 'passed with nothing verified' : last.passed ? 'passed' : 'FAILED'
    const columns = Math.max(1, Math.min(runs.length, e.props.bodyColumns - 2))
    const chosen = ledger.find(r => r.id === selected)
    return (
      <Box flexDirection="column">
        <Text bold>
          PROOF9 ledger · {ledger.length} {ledger.length === 1 ? 'obligation' : 'obligations'} · {failing.length} failing
        </Text>
        {runs.length && Raster ? <Raster key="history" columns={columns} rows={1} cells={historyCells(runs, columns)} /> : null}
        {runs.length && !Raster ? (
          <Text>{runs.slice(0, columns).reverse().map(r => (r.vacuous ? '○' : r.passed ? '✓' : '✗')).join('')}</Text>
        ) : null}
        <Text dimColor>
          {last ? `Last run ${last.started_at ?? ''}: ${lastWord}` : 'No runs yet.'}
        </Text>
        {ledger.length === 0 ? (
          <Text>{'No proof obligations yet. Capture one with /proof <what went wrong>, or lock in passing tests with /proof ratchet.'}</Text>
        ) : null}
        {ledger.map(r => (
          <Button key={`req-${r.id}`} plain onPress={() => selectRequirement($, r.id)}>
            {rowLabel(r)}
          </Button>
        ))}
        {chosen && detail ? <Markdown key="detail" text={detail} /> : null}
        <Box>
          {chosen && isFailing(chosen) ? (
            <Button
              key="fix"
              label="Ask Claude to fix"
              variant="primary"
              onPress={() => askToFix($, failing.filter(f => f.id === chosen.id).map(toFailing))}
            />
          ) : null}
          <Button key="run" label="Run proof" onPress={() => runProof($, false)} />
          <Button key="run-full" label="Run full" onPress={() => runProof($, true)} />
        </Box>
        <Text dimColor>{USAGE}</Text>
      </Box>
    )
  })

  on('command.run', { command: 'proof' }, async ($, e) => {
    const args = e.args.trim()
    const flags = ratchetFlags(args)
    if (flags === null) return { text: USAGE }
    if (flags) return { text: await ratchet($, flags) }
    const text = args || (await attempt(() => $.ui.selection()))?.text.trim()
    if (!text) {
      // Read first, so the pane's first paint is the ledger, not an empty one.
      await refreshLedger($)
      await $.ui.open({ id: PANE, title: 'proof9 ledger' })
      return { text: 'Opened the proof9 ledger pane.' }
    }
    return { text: await capture($, text) }
  })
}
