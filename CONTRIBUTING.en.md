# Contributing

🌐 [Leer en español](CONTRIBUTING.md)

Thank you for your interest in Algor. This project follows the
[Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating you agree to uphold it in issues, PRs and every project space.

🌐 [Leer en español](CONTRIBUTING.md)

The top priority is validating the same LCD `1b1c:0c57` on other motherboards and
Linux desktops. Use the **Compatibility result** issue form and the
[COMPATIBILITY.md](docs/COMPATIBILITY.md) guide. Always distinguish physical
observation, simulated tests and features not yet tested.

## Development

Set up the environment as described in the README. The workflow for proposing a
change is:

1. Fork the repository and clone your copy.
2. Create a descriptive branch from `main` (`git checkout -b fix/short-name`).
3. Make your changes and run the tests before committing:

```bash
python scripts/run_tests.py
python scripts/smoke_test.py
```

4. Open a Pull Request against `main` in the original repository.

The first command isolates preferences and data; avoid running the older tests
with `unittest discover` directly on your regular configuration. The GUI test
does not require an LCD. An optional private USB capture must not become a
requirement for the public code to be tested.

### Hardware safety rules

USB changes must maintain strict device identification, bounded timeouts,
exclusive interface ownership and no automatic memory-save retries. Do not
enable PWM/DC control as part of an LCD compatibility test. Pump and fans remain
under BIOS control by default; the only exception is the opt-in Reactive mode on
a channel tested and confirmed by the user through the guided procedure — see
[docs/PWM_REAL_CONTROL.md](docs/PWM_REAL_CONTROL.md). The pump is never a
candidate, in any change you propose.

### PR content

Include in your PR the problem it solves, the final behavior, tests and
physically verified models. Do not attach personal configuration, media, full USB
dumps, serial numbers or unreviewed logs.

## Code style

The project does not enforce an automatic formatter for now, but please follow
these conventions to keep diffs clean:

- PEP 8 as a general reference (4-space indentation, lines ≤ 100 characters).
- Variable and function names in `snake_case`; classes in `PascalCase`.
- Docstrings on public functions; comments only where intent is not obvious from
  the code.
- Do not include mass formatting changes in a functional PR — if you want to
  reformat, do it in a separate PR and explain the scope.

## Translations

Spanish is the source language (the text already written in the code); there is
no `es.po` catalog because none is needed. Every visible string goes through
`_()` (`from algor.core.i18n import _`), and `gettext` detects the system
language automatically (`LANGUAGE`/`LC_ALL`/`LC_MESSAGES`/`LANG`) — no manual
selector for now.

To add a new language:

```bash
mkdir -p algor/locale/<code>/LC_MESSAGES
cp algor/locale/algor.pot algor/locale/<code>/LC_MESSAGES/algor.po
# Translate each msgstr in the .po (Poedit or a text editor will do)
bash scripts/i18n_compile.sh
```

If you add or change a visible string in the code, run
`bash scripts/i18n_extract.sh` first — it regenerates `algor.pot` and merges
changes into every existing `.po` without losing completed translations — then
`bash scripts/i18n_compile.sh` to compile the `.mo` that the app actually reads
at runtime. CI validates that every `.po` compiles without errors.

## CI

[Tests](.github/workflows/tests.yml) installs dependencies and runs the suite
and simulated GUI on Python 3.10, 3.12 and 3.13. It also tests a public copy
with no local media or captures. It follows the recommended pattern from
[GitHub for Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
CI results do not certify compatibility with a physical device.
