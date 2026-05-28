# Third-party notices

This directory collects license texts and package-specific notes for third-party software used by trueRiver.

Current status:

- Common license texts are present for the first release-prep pass.
- `soundtouchjs.md` records the LGPL-2.1 dependency that affects the web frontend bundle.
- `Tabler-Icons-MIT.txt` preserves the MIT license notice for Tabler Icons after removing the full vendored icon pack.
- `frontend-npm/` contains copied package-level license and notice files from the installed frontend npm dependency tree. Regenerate it with `scripts/collect-frontend-notices.sh` after dependency changes.

Before a public binary release, regenerate this directory from the final dependency state and include it with the release attachments.
