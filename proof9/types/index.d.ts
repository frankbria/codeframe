/** A requirement the ledger records as failing: not waived, with a failed obligation. */
export type Failing = { id: string; title: string; tests: string[] }

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
    }
  }
}
