/**
 * PROOF9 constants shared across the web UI.
 *
 * The 9 gate names mirror the `Gate` enum in
 * `codeframe/core/proof/models.py` and are the canonical wire values
 * accepted by the backend's `enabled_gates` field.
 *
 * SYNC: if a gate is added/removed in `codeframe/core/proof/models.py::Gate`,
 * mirror the change here AND in `GATE_LABELS` below.
 */

export const PROOF9_GATES = [
  'unit',
  'contract',
  'e2e',
  'visual',
  'a11y',
  'perf',
  'sec',
  'demo',
  'manual',
] as const;

export type Proof9Gate = (typeof PROOF9_GATES)[number];

export const GATE_LABELS: Record<Proof9Gate, string> = {
  unit: 'Unit',
  contract: 'Contract',
  e2e: 'E2E',
  visual: 'Visual',
  a11y: 'A11y',
  perf: 'Performance',
  sec: 'Security',
  demo: 'Demo',
  manual: 'Manual',
};
