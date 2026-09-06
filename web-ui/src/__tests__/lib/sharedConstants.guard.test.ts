/**
 * Guard test for issue #971.
 *
 * The status maps, the USD formatter and the workspace-storage key were each
 * duplicated verbatim across several components, and nothing linked the copies
 * together — so adding a status, or changing a storage key, silently left one
 * surface behind. These are source scans rather than behavioural tests on
 * purpose: what regressed was the *absence* of a single definition, which no
 * render test can observe. Precedent: `api.contract.test.ts`.
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

describe('#971 — status maps have a single definition', () => {
  it('is declared only in lib/taskStatusInfo.ts', () => {
    const offenders = ALL_SOURCES.filter(
      (f) =>
        rel(f) !== join('lib', 'taskStatusInfo.ts') &&
        /^\s*(export\s+)?const\s+(STATUS_LABEL|STATUS_BADGE_VARIANT)\b/m.test(readFileSync(f, 'utf8'))
    ).map(rel);

    expect(offenders).toEqual([]);
  });
});

describe('#971 — one USD formatter', () => {
  it('has no hand-rolled currency toFixed in components or pages', () => {
    const offenders: string[] = [];
    for (const file of ALL_SOURCES) {
      const source = readFileSync(file, 'utf8');
      source.split('\n').forEach((line, i) => {
        // `toFixed(4)` is only ever a USD amount here. Deliberately not
        // matching a `$` next to a toFixed: `${(ms / 1000).toFixed(1)}` is a
        // template sigil, not a currency sign, and the two are
        // indistinguishable by regex. Non-USD precision (durations) is fine.
        if (/toFixed\(4\)/.test(line)) {
          offenders.push(`${rel(file)}:${i + 1}`);
        }
      });
    }

    expect(offenders).toEqual([]);
  });

  it('declares no local currency formatter outside lib/format.ts', () => {
    const offenders = ALL_SOURCES.filter(
      (f) =>
        rel(f) !== join('lib', 'format.ts') &&
        /function\s+format(Currency|Cost|BadgeCost|Usd|USD)\b/.test(readFileSync(f, 'utf8'))
    ).map(rel);

    expect(offenders).toEqual([]);
  });
});

describe('#971 — workspace storage key has a single definition', () => {
  it('appears as a literal only in lib/workspace-storage.ts', () => {
    const offenders = ALL_SOURCES.filter(
      (f) =>
        rel(f) !== join('lib', 'workspace-storage.ts') &&
        readFileSync(f, 'utf8').includes('codeframe_workspace_path')
    ).map(rel);

    expect(offenders).toEqual([]);
  });
});
