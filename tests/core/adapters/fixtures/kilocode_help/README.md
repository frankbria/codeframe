# kilocode CLI help fixtures

Verbatim `kilo --help` output from the two incompatible CLIs that both answer to
`kilo`. `_detect_surface` is matched against these rather than against text
invented for the test — the same reason #914 checks in the codex app-server
schema.

| file | version | captured |
|---|---|---|
| `help-0.22.0.txt` | `@kilocode/cli@0.22.0` (2026-01-15) | 2026-08-01 |
| `help-7.4.17.txt` | `@kilocode/cli@7.4.17` (2026-07-29) | 2026-08-01 |

Regenerate with:

```
npm install -g @kilocode/cli@<version>
kilo --help > help-<version>.txt 2>&1
```

The 7.x file contains ANSI/box-drawing characters from the banner; that is
deliberate, since the real output does too and the detector must cope with it.
