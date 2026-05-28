# Contributing To trueRiver

trueRiver is planned as free software under `AGPL-3.0-or-later`.

By contributing, you agree that your contribution may be distributed under the
same project license. Do not submit code, assets, examples, or generated output
unless you have the right to contribute them under that license.

## Before Submitting

- Keep user media, database dumps, avatars, `.env` files, signing keys, local
  SDK files, and generated APKs out of Git.
- Do not bump `VERSION`, create release tags, or include generated web build
  changes in pull requests unless the maintainer asks for release packaging
  work.
- Before pushing or opening a pull request, run:

```bash
./scripts/pre-push-check.sh
```

This runs whitespace checks, Python compilation and the API smoke tests,
including the Android TV Basic Auth endpoints.

- Avoid copying code from tutorials, StackOverflow, gists, or other projects
  unless the license permits it and the source is clearly documented.
- Include or update tests when touching parsers, streaming, metadata inference,
  authentication, playback, subtitles, or release packaging.
- Keep third-party license obligations visible in `NOTICE.md` and
  `THIRD_PARTY_NOTICES/`.

## Developer Certificate Of Origin

trueRiver requires Developer Certificate of Origin sign-off for external
contributions.

Add a sign-off line to each commit:

```bash
git commit -s -m "README now explains the local media workflow"
```

That adds:

```text
Signed-off-by: Your Name <you@example.com>
```

By signing off, you certify that you wrote the contribution or otherwise have
the right to submit it to trueRiver under `AGPL-3.0-or-later`, and that the
contribution can be distributed under that license.

The DCO text is published at:

```text
https://developercertificate.org/
```

## Commit Messages

Use commit subjects that explain what changed, not what someone should do next.

Good examples:

- `README now explains the local media workflow`
- `Android release builds now use the signed keystore path`
- `Frontend notices are collected from the npm install tree`

Avoid vague imperative subjects when a human-facing explanation would be clearer,
especially near release work.
