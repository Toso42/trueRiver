# Release Artifacts

Generate release attachments from a clean source checkout:

```bash
./scripts/build-release-artifacts.sh
```

Source commits and pull requests do not bump the public version. Release tags
and release artifacts are prepared by the maintainer.

When no version is passed, the script reads the tag name from `VERSION`. Prepare
that file before a release with:

```bash
./scripts/prepare-release-version.sh prerelease
VITE_TRIVER_VERSION="$(cat VERSION)" ./scripts/build-frontend.sh
git add VERSION frontend/source/package.json frontend/source/package-lock.json frontend/package/build
git commit -m "Prepare trueRiver $(cat VERSION)"
git tag -a "$(cat VERSION)" -m "trueRiver $(cat VERSION)"
```

The frontend build helper produces a public, relocatable bundle. It must not
embed the maintainer's local/public hostname; browser API and stream requests
resolve from the origin that serves the app.

Do not include `apk/source/app/build.gradle` in that commit unless you
intentionally prepared Android with `--android`.

The script:

- validates the committed web frontend under `frontend/package/build/`;
- creates `trueriver-source-<version>.tar.gz` as a complete source archive from
  `HEAD`, including the built web frontend;
- creates `trueriver-install-<version>.tar.gz` with the same source tree, the
  built web frontend, and a short install README at the archive root while
  preserving the project README as `README.project.md`;
- creates `trueriver-windows-<version>.zip` with the same source tree, the
  built web frontend, and PowerShell helpers for Docker Desktop installs;
- creates `trueriver-web-<version>.zip`;
- creates `trueriver-third-party-notices-<version>.zip`;
- copies an Android TV APK when `TRIVER_APK_PATH` points to one;
- writes `release-notes-<version>.md` and `checksums.txt`.

Public releases should run this only from the exact tag or commit being
published. The generated files are release attachments and are ignored by Git
under `release/artifacts/`.

For prerelease tech demos, use `v0.1.0-techdemo.N`. For stable releases, use
normal semver tags such as `v0.1.1`, `v0.2.0` or `v1.0.0`.

Normal users should install from `trueriver-install-<version>.tar.gz` when they
want the server and web app together without downloading Node/npm dependencies.
Git checkouts and source archives are also installable because they include
`frontend/package/build/`; developers can rebuild the web app explicitly.
Windows users should use `trueriver-windows-<version>.zip`.
