# Security policy

## What SpriteMotion runs

SpriteMotion is a local authoring toolkit. Its web tools are small Python HTTP servers meant for one user on one
machine:

| Tool | Default address |
|---|---|
| Content Studio (`tools/uo-content/studio.py`) | `http://127.0.0.1:8772` |
| Fit Lab (`tools/fit-lab/run.py serve`) | `http://127.0.0.1:8774` |

Both bind to the loopback interface only and reject requests whose `Host` or `Origin` header is not
`127.0.0.1:<port>` or `localhost:<port>`, which blocks DNS-rebinding and cross-site requests from web pages.
State-changing requests accept JSON only. They are not designed to be exposed to a network: do not bind them to
`0.0.0.0`, port-forward them or put them behind a public reverse proxy.

The tools read and write files under the repository's ignored `workspace/` folder, the local asset-pack sidecar
(`SPRITEMOTION_SIDECAR`) and folders you choose. Client staging writes to a new output folder and never modifies the
source client installation.

## Supported versions

Only the current `main` branch is supported. There are no released versions yet.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/DatMoshu/SpriteMotion/security/advisories/new)
(repository **Security** tab, **Report a vulnerability**). Do not open a public issue for a security problem.

Include the affected tool and commit, steps to reproduce and the impact you observed. Do not attach game client
files, extracted art or commercial asset-pack content. The maintainer will acknowledge the report in the advisory,
land the fix on `main` and credit you there unless you prefer otherwise.
