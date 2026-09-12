/**
 * Guard test for issues #971 and #1195.
 *
 * The status maps, the USD formatter and the workspace-storage key were each
 * duplicated verbatim across several components, and nothing linked the copies
 * together — so adding a status, or changing a storage key, silently left one
 * surface behind. #1195 closed the same class of leftover for badge-variant
 * typing, proof status colours and timestamp formatting. These are source
 * scans rather than behavioural tests on purpose: what regressed was the
 * *absence* of a single definition, which no render test can observe.
 * Precedent: `api.contract.test.ts`.
 */
import { readFileSync, readdirSync, statSync } from 'fs';
import { join } from 'path';

const SRC = join(__dirname, '..', '..');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue;
      out.push(...sourceFiles(full));
    } else if (/\.tsx?$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

const ALL_SOURCES = sourceFiles(SRC);
const rel = (f: string) => f.slice(SRC.length + 1);
const FORMAT_TS = join('lib', 'format.ts');

/** Files (relative) whose source matches `pattern`, excluding `allowed`. */
function offenders(pattern: RegExp, allowed: string[] = []): string[] {
  return ALL_SOURCES.filter(
    (f) => !allowed.includes(rel(f)) && pattern.test(readFileSync(f, 'utf8'))
  ).map(rel);
}

/** `file:line` for every line matching `pattern`, excluding `allowed` files. */
function offendingLines(pattern: RegExp, allowed: string[] = [], under = ''): string[] {
  const out: string[] = [];
  for (const file of ALL_SOURCES) {
    if (allowed.includes(rel(file)) || !rel(file).startsWith(under)) continue;
    readFileSync(file, 'utf8')
      .split('\n')
      .forEach((line, i) => {
        if (pattern.test(line)) out.push(`${rel(file)}:${i + 1}`);
      });
  }
  return out;
}

describe('#971 — status maps have a single definition', () => {
  it('is declared only in lib/taskStatusInfo.ts', () => {
    expect(
      offenders(/^\s*(export\s+)?const\s+(STATUS_LABEL|STATUS_BADGE_VARIANT)\b/m, [
        join('lib', 'taskStatusInfo.ts'),
      ])
    ).toEqual([]);
  });
});

// The thing the duplication actually looks like: an Intl currency option.
// Matching on function *names* (the #971 rule this replaces) missed any
// formatter not called format(Currency|Cost|Usd) — see #1195 item 5.
const CURRENCY_OPTION = /style:\s*['"]currency['"]/;

describe('#971 / #1195 — one USD formatter', () => {
  it('has no hand-rolled currency toFixed in components or pages', () => {
    // `toFixed(4)` is only ever a USD amount here. Deliberately not
    // matching a `$` next to a toFixed: `${(ms / 1000).toFixed(1)}` is a
    // template sigil, not a currency sign, and the two are
    // indistinguishable by regex. Non-USD precision (durations) is fine.
    expect(offendingLines(/toFixed\(4\)/)).toEqual([]);
  });

  it('the currency rule recognises the Intl option it is guarding against', () => {
    // Self-check so the rule below cannot rot into a vacuous pass.
    expect(CURRENCY_OPTION.test("toLocaleString('en-US', { style: 'currency' })")).toBe(true);
    expect(CURRENCY_OPTION.test('new Intl.NumberFormat("en", {style: "currency"})')).toBe(true);
    expect(CURRENCY_OPTION.test("{ style: 'percent' }")).toBe(false);
  });

  it('uses the Intl currency option only in lib/format.ts', () => {
    expect(offendingLines(CURRENCY_OPTION, [FORMAT_TS])).toEqual([]);
    expect(CURRENCY_OPTION.test(readFileSync(join(SRC, FORMAT_TS), 'utf8'))).toBe(true);
  });
});

describe('#971 — workspace storage key has a single definition', () => {
  it('appears as a literal only in lib/workspace-storage.ts', () => {
    expect(
      offenders(/codeframe_workspace_path/, [join('lib', 'workspace-storage.ts')])
    ).toEqual([]);
  });
});

describe('#1195 — badge variants are type-checked, not cast', () => {
  it('no Badge variant prop is cast with `as never`', () => {
    expect(offendingLines(/variant=\{[^}]*as never\}/)).toEqual([]);
  });

  it('STATUS_BADGE_VARIANT is typed against badgeVariants, not string', () => {
    const source = readFileSync(join(SRC, 'lib', 'taskStatusInfo.ts'), 'utf8');
    expect(source).toMatch(/STATUS_BADGE_VARIANT:\s*Record<TaskStatus,\s*BadgeVariant>/);
  });
});

describe('#1195 — proof status colours come from badge variants', () => {
  // Scope: a status *badge or pill* — a `bg-<hue>-N text-<hue>-N` pair, which
  // is what a copied badge variant looks like. GateRunBanner's live-run dots
  // and WaiveDialog's warning box are not badges and keep their own colours.
  it('has no raw status badge colour pair in src/components/proof', () => {
    expect(
      offendingLines(/\bbg-(red|green|gray|amber)-\d+ text-(red|green|gray|amber)-\d+\b/, [], join('components', 'proof'))
    ).toEqual([]);
  });
});

describe('#1195 — one timestamp formatter set', () => {
  it('formats displayed timestamps only through lib/format.ts', () => {
    expect(offendingLines(/\.toLocale(Date|Time)?String\(/, [FORMAT_TS])).toEqual([]);
  });

  it('imports the date-fns relative-time helpers only in lib/format.ts', () => {
    expect(offenders(/formatDistanceToNow(Strict)?/, [FORMAT_TS])).toEqual([]);
  });
});
