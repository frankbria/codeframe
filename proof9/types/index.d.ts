/** A requirement the ledger records as failing: not waived, with a failed obligation. */
export type Failing = { id: string; title: string; tests: string[] }

/** A requirement as `cf proof list --json` reports it (the fields the plugin reads). */
export type LedgerRequirement = {
  id: string
  title: string
  status: string
  obligations: { gate: string; status: string }[]
  evidence_rules: { test_id: string; gate: string | null }[]
  waiver: { expired: boolean } | null
}

/** A run as `cf proof status --json` reports it, newest first. */
export type RunSummary = { run_id: string; started_at: string | null; passed: boolean; vacuous: boolean; duration_ms: number | null }

declare module 'claude-code' {
  interface PluginState {
    proof9: {
      failing: Failing[]
      /** Failure keys the person dismissed this session. */
      dismissed: string[]
      /** The ledger is empty and the empty-ledger band was not dismissed for this repo. */
      emptyLedger: boolean
      /** The requirement whose waiver reason is being typed. */
      waiving: string | null
      /** The ledger as last read, for the /proof pane. */
      ledger: LedgerRequirement[]
      runs: RunSummary[]
      /** The requirement selected in the pane, and its detail as Markdown. */
      selected: string | null
      detail: string | null
    }
  }
}
