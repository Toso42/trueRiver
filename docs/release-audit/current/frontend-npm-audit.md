# Frontend npm audit

Date: 2026-05-20

Command:

```bash
docker run --rm \
  -v /home/dockers/triver-publish-candidate/frontend/source:/frontend \
  -w /frontend \
  node:20-alpine \
  npm audit --audit-level=moderate
```

Result after Vite/plugin upgrade: passed audit threshold with zero findings.

Findings:

| Package | Advisory | Severity | Release impact |
| --- | --- | ---: | --- |
| `esbuild <=0.24.2` via `vite <=6.4.1` | `GHSA-67mh-4wv8-2f99` | Moderate | Resolved by upgrading to `vite@8.0.13` and `@vitejs/plugin-react@6.0.2`. |
| `postcss <8.5.10` | `GHSA-qx2v-qp2m-jg93` | Moderate | Resolved by conservative `npm audit fix`; `postcss` is now locked at `8.5.15`. |

Next action:

- Keep the Vite 8 build covered by the frontend Docker build smoke test.
- Re-run `npm audit --audit-level=moderate` before tagging any public release.
