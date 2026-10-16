// Whether a Bash command line runs `git commit`.
//
// A regex cannot see shell structure: it missed `GIT_DIR=x git commit` and
// `git -C "a b" commit` (a failing commit through block mode) and matched
// `echo "x; git commit"` or a heredoc body (a non-commit denied). This splits
// the line into simple commands the way the shell would — quotes kept whole,
// heredoc bodies and line continuations understood — and asks of each whether
// its program is git and its subcommand is `commit`.
//
// Command substitution inside double quotes is scanned too; single quotes stay
// opaque, as the shell keeps them.
//
// shortcut: not a shell parser — `sudo -u bob git commit`, aliases, functions,
// `bash -c "git commit"`, `xargs git commit` and `find -exec git commit` are not
// seen; upgrade if one of them matters.

// Words that run the command after them.
const WRAPPERS = new Set(['env', 'sudo', 'time', 'command', 'nohup', 'exec', '!', 'then', 'do', 'else', 'elif', 'if', 'while', 'until', '{', '}'])

// A redirection word: `>x`, `2>`, `2>&1`, `&>/dev/null`, `<in`. With no target
// attached (`>`, `2>`), its target is the next word.
const REDIRECT = /^(?:\d*|&)(?:>>?|<|>&|<&|>\|)(.*)$/

// git's global options that take the next word as their value.
const GIT_VALUE_OPTS = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix', '--config-env'])

/** Index of the `)` closing a `$(` whose body starts at ``start`` (quotes,
 *  escapes and nested parentheses understood), or ``line.length``. */
function closingParen(line: string, start: number): number {
  let depth = 1
  for (let k = start; k < line.length; k++) {
    const ch = line[k]
    if (ch === '\\') k++
    else if (ch === "'") k = (line.indexOf("'", k + 1) + 1 || line.length + 1) - 1
    else if (ch === '"') k = closingQuote(line, k + 1)
    else if (ch === '(') depth++
    else if (ch === ')' && --depth === 0) return k
  }
  return line.length
}

/** Index of the `"` closing a double-quoted span that starts at ``start``:
 *  a `$(…)` inside it may hold quotes of its own. */
function closingQuote(line: string, start: number): number {
  for (let k = start; k < line.length; k++) {
    const ch = line[k]
    if (ch === '\\') k++
    else if (ch === '$' && line[k + 1] === '(') k = closingParen(line, k + 2)
    else if (ch === '`') k = (line.indexOf('`', k + 1) + 1 || line.length + 1) - 1
    else if (ch === '"') return k
  }
  return line.length
}

/** The simple commands of a command line, each as its list of words. */
export function simpleCommands(line: string): string[][] {
  const commands: string[][] = []
  const nested: string[][] = []
  const pendingHeredocs: { delimiter: string; tabs: boolean }[] = []
  let words: string[] = []
  let word = ''
  let inWord = false
  const endWord = () => {
    if (inWord) words.push(word)
    word = ''
    inWord = false
  }
  const endCommand = () => {
    endWord()
    if (words.length) commands.push(words)
    words = []
  }

  let i = 0
  while (i < line.length) {
    const c = line[i] ?? ''
    if (c === '\\') {
      if (line[i + 1] !== '\n') {
        word += line[i + 1] ?? ''
        inWord = true
      }
      i += 2
    } else if (c === "'") {
      const end = line.indexOf("'", i + 1)
      word += line.slice(i + 1, end < 0 ? undefined : end)
      inWord = true
      i = end < 0 ? line.length : end + 1
    } else if (c === '"') {
      // Double quotes keep `$(…)` and backticks live, at any depth:
      // `OUT="$(git -C "a b" commit)"` commits.
      const end = closingQuote(line, i + 1)
      for (let k = i + 1; k < end; k++) {
        if (line[k] === '\\') {
          k++
        } else if (line[k] === '$' && line[k + 1] === '(') {
          const close = closingParen(line, k + 2)
          nested.push(...simpleCommands(line.slice(k + 2, close)))
          k = close
        } else if (line[k] === '`') {
          const close = line.indexOf('`', k + 1)
          nested.push(...simpleCommands(line.slice(k + 1, close < 0 ? end : close)))
          k = close < 0 ? end : close
        }
      }
      word += line.slice(i + 1, end).replace(/\\(.)/g, '$1')
      inWord = true
      i = end + 1
    } else if (line.startsWith('<<<', i)) {
      endWord()
      i += 3
    } else if (line.startsWith('<<', i)) {
      endWord()
      const m = /^<<(-?)\s*(?:'([^']*)'|"([^"]*)"|([^\s;&|()<>]+))/.exec(line.slice(i))
      if (m) pendingHeredocs.push({ delimiter: m[2] ?? m[3] ?? m[4] ?? '', tabs: m[1] === '-' })
      i += m ? m[0].length : 2
    } else if (c === '\n') {
      endCommand()
      i++
      // A heredoc body is data, not commands: skip to each delimiter line.
      for (const { delimiter, tabs } of pendingHeredocs.splice(0)) {
        while (i < line.length) {
          const eol = line.indexOf('\n', i)
          const text = line.slice(i, eol < 0 ? undefined : eol)
          i = eol < 0 ? line.length : eol + 1
          if ((tabs ? text.replace(/^\t+/, '') : text) === delimiter) break
        }
      }
    } else if (c === '$' && line[i + 1] === '(') {
      endCommand()
      i += 2
    } else if (c === '&' && (/[<>]$/.test(word) || line[i + 1] === '>')) {
      // Part of a redirection (`2>&1`, `&>file`), not a separator.
      word += c
      inWord = true
      i++
    } else if (';&|()`'.includes(c)) {
      endCommand()
      i++
    } else if (c === ' ' || c === '\t') {
      endWord()
      i++
    } else {
      word += c
      inWord = true
      i++
    }
  }
  endCommand()
  return [...commands, ...nested]
}

/** ``words`` without its redirections, which the shell applies, not passes. */
function withoutRedirections(words: string[]): string[] {
  const kept: string[] = []
  for (let i = 0; i < words.length; i++) {
    const m = REDIRECT.exec(words[i] ?? '')
    if (!m) kept.push(words[i] ?? '')
    else if (!m[1]) i++ // a bare operator: its target is the next word
  }
  return kept
}

function runsGitCommit(all: string[]): boolean {
  const words = withoutRedirections(all)
  let k = 0
  while (k < words.length) {
    const w = words[k] ?? ''
    // Leading assignments, wrappers, and a wrapper's own flags (`env -i`, `time -p`).
    if (WRAPPERS.has(w) || /^\w+=/.test(w) || (k > 0 && w.startsWith('-'))) k++
    else break
  }
  if ((words[k] ?? '').split('/').pop() !== 'git') return false
  let j = k + 1
  while (j < words.length && (words[j] ?? '').startsWith('-')) {
    j += GIT_VALUE_OPTS.has(words[j] ?? '') ? 2 : 1
  }
  return words[j] === 'commit'
}

/** True when any simple command in ``line`` is `git … commit`. */
export function isGitCommit(line: string): boolean {
  return simpleCommands(line).some(runsGitCommit)
}
