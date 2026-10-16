import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Failing } from '../types'
import { isGitCommit, runsCfProof } from './commit.ts'

const failingAtom = atom({ plugin: 'proof9', key: 'failing' } as const, [])
const dismissedAtom = atom({ plugin: 'proof9', key: 'dismissed' } as const, [])
const emptyAtom = atom({ plugin: 'proof9', key: 'emptyLedger' } as const, false)
const waivingAtom = atom({ plugin: 'proof9', key: 'waiving' } as const, null)

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

async function capture($: EngineInterface, text: string): Promise<string> {
  const first = (text.split('\n').find(line => line.trim()) ?? text).trim()
  const title = Array.from(first).slice(0, TITLE_MAX).join('').trim()
  // The repo root scopes the requirement to the whole repository (fail closed).
  const where = (await attempt(() => $.session.repo()))?.root ?? '.'
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

type Listed = {
  requirements: {
    id: string
    title: string
    status: string
    obligations: { gate: string; status: string }[]
    evidence_rules: { test_id: string; gate: string | null }[]
  }[]
}

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
  const failing: Failing[] = reqs
    .filter(r => r.status !== 'waived' && r.obligations.some(o => o.status === 'failed'))
    .map(r => {
      const gates = r.obligations.filter(o => o.status === 'failed').map(o => o.gate)
      const tests = r.evidence_rules.filter(t => t.gate !== null && gates.includes(t.gate)).map(t => t.test_id)
      return { id: r.id, title: r.title, tests: tests.length ? tests : gates.map(g => `${g} gate`) }
    })
  const noun = reqs.length === 1 ? 'obligation' : 'obligations'
  $.ui.status(reqs.length ? `proof9 · ${reqs.length} ${noun} · ${failing.length} failing` : 'proof9 · no obligations yet')
  await update($, failingAtom, () => failing)
  // A dismissal ends with its failure, so a later regression shows again.
  const live = new Set(failing.map(failureKey))
  await update($, dismissedAtom, keys => keys.filter(k => live.has(k)))
  const hidden = Boolean(await attempt(async () => $.store.get(await emptyHiddenKey($))))
  await update($, emptyAtom, () => reqs.length === 0 && !hidden)
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
  await update($, waivingAtom, () => null)
  const ran = await cf($, ['proof', 'waive', id, '--reason', reason, ...(m ? ['--expires', m[2] ?? ''] : [])])
  if ('failed' in ran || ran.exitCode !== 0) {
    await notice($, `proof9 could not waive ${id}: ${'failed' in ran ? ran.failed : errorText(ran)}`)
  }
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
      person: broken.length
        ? `proof9: ${broken.length} proven requirement(s) fail: ${broken.map(r => r.id).join(', ')}`
        : 'proof9: the proof run reported a failure',
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
    return { kind: 'note', person: 'proof9: no proof obligations yet. Capture a bug with /proof, or lock in passing tests with /proof ratchet.' }
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
    if (await checkVersion($)) await refreshLedger($)
    return next(e)
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
      $.ui.toast(verdict.person)
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
    const Input = 'Input' in table ? table.Input : undefined
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

  on('command.run', { command: 'proof' }, async ($, e) => {
    const args = e.args.trim()
    const flags = ratchetFlags(args)
    if (flags === null) return { text: USAGE }
    if (flags) return { text: await ratchet($, flags) }
    const text = args || (await attempt(() => $.ui.selection()))?.text.trim()
    if (!text) return { text: USAGE }
    return { text: await capture($, text) }
  })
}
