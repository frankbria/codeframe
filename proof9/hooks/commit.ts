// Whether a Bash command line runs `git commit`.
//
// A regex cannot see shell structure: it missed `GIT_DIR=x git commit` and
// `git -C "a b" commit` (a failing commit through block mode) and matched
// `echo "x; git commit"` or a heredoc body (a non-commit denied). This splits
// the line into simple commands the way the shell would — quotes kept whole,
// heredoc bodies and line continuations understood — and asks of each whether
// its program is git and its subcommand is `commit`.
//
// shortcut: not a shell parser — `sudo -u bob git commit`, aliases, functions
// and `bash -c "git commit"` are not seen; upgrade if one of them matters.

// Words that run the command after them.
const WRAPPERS = new Set(['env', 'sudo', 'time', 'command', 'nohup', 'exec', '!', 'then', 'do', 'else', 'if', 'while', 'until', '{', '}'])

// git's global options that take the next word as their value.
const GIT_VALUE_OPTS = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix', '--config-env'])

/** The simple commands of a command line, each as its list of words. */
export function simpleCommands(line: string): string[][] {
  const commands: string[][] = []
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
      let j = i + 1
      while (j < line.length && line[j] !== '"') j += line[j] === '\\' ? 2 : 1
      word += line.slice(i + 1, j).replace(/\\(.)/g, '$1')
      inWord = true
      i = j + 1
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
  return commands
}

function runsGitCommit(words: string[]): boolean {
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
