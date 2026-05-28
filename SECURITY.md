# Security Policy

trueRiver is preparing for a public tech-demo release. Until the first public
release is tagged, security reports should be sent privately to the project
owner through the repository contact channel.

## Supported Versions

Only tagged public releases are supported. Development snapshots and private
candidate branches are not supported for production use.

## Reporting A Vulnerability

Please do not open a public issue for a suspected vulnerability that exposes
credentials, user media, private metadata, authentication bypasses, or remote
code execution paths.

Open a private security advisory when the repository host supports it, or
contact the project owner through the public profile linked in `AUTHORS`.

Include:

- affected version or commit;
- affected component: backend, web frontend, Android TV app, Docker packaging;
- reproduction steps;
- expected impact;
- whether user media, credentials, tokens, or server access are involved.

## Release Baseline

Public release candidates must pass a secrets scan before publication and must
not include user media, scan dumps, avatars, runtime databases, `.env` files,
Android signing keys, local SDK configuration, or personal deployment defaults.
