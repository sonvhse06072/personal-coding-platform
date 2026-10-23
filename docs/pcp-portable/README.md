# PCP portable install — B1.1 (fresh WSL2 install only)

**Status:** first-install source implementation. CI can test safety and the exact shell contract with **fake Docker/DDEV**. A clean physical/virtual WSL2 transfer and real start are **NOT YET ATTESTED**; do not call this production-ready or say PCP automatically accepts tasks.

## Prerequisites

- WSL2 Ubuntu (or compatible Linux), one working Docker provider and **DDEV**. DDEV is already the canonical PCP lifecycle manager and requires Docker. Git is needed to obtain source. A regular, non-root user is mandatory.
- No host Python, PHP, Node/npm, Codex CLI, OpenCode CLI, Antigravity CLI or local PostgreSQL installation.
- Fresh checkout under the Linux filesystem. The existing `scripts/bootstrap.sh` is the **legacy** installer and is not used for this portable mode. Do **not** run this installer on a current legacy instance, Chợ Nhạc tree, G0/F2 or old G1 workspace.

## Initial preparation and start

From a **new** clone of `sonvhse06072/personal-coding-platform`:

```bash
bash scripts/pcp-portable-bootstrap.sh --check     # read-only diagnosis
bash scripts/pcp-portable-bootstrap.sh --prepare   # private env and scoped secrets
bash scripts/pcp-portable-bootstrap.sh --start     # explicitly start DDEV
```

For a one-step first install after inspecting the source and accepting Docker/DDEV side effects, use only the last `--start` invocation. Subsequent normal startup is still `ddev start`. All commands run in a **subprocess**, not an interactive shell with imported `set -e`.

The preparation tool requires an absent `.ddev/.env` (fresh) or an already private portable-mode `.ddev/.env` with `PCP_ANTIGRAVITY_MODE=disabled` and exact Codex pin. A legacy setup, unexpected secret files, symlinks or stale pins **STOP**, never undergo automatic credential/ProjectBaseline migration. It produces only its own ignored `.ddev/.env` (nonsecret) and existing service-scoped `.ddev/.env.<service>.local` files with private permissions. Never commit or paste these files. Retrying a failed setup only revisits the same portable-owned setup; it does **not** reset durable PCP jobs or their credentials.

The existing `scope-service-secrets.sh` and `n8n-control-plane.sh prepare-env` run **inside one disposable non-root `python:3.13-slim-bookworm` setup container**. It has a read-only rootfs, no network, no Docker socket, no mounted user home or external projects, and a read/write bind of **only this fresh PCP checkout** to create local files. The image may need to be pulled by Docker on first use; it is **not yet pinned to a multiarch digest**. The checked-in `config/tool-versions.env` is authoritative for the generated `CODEX_VERSION`.

`.ddev/config.yaml` remains unchanged and uses its existing `pre-start` host hook. Under the explicit portable flag, `scripts/antigravity-bridge.sh` exits before any host `agy`, Python, keyring, background process or settings mutation. On old installs without the flag, behavior stays unchanged. Antigravity Individual (host-keyring-dependent) is therefore **disabled** for portable mode until a separate container-safe authentication contract is accepted; do not mount/copy the owner's host keyring as a workaround.

After first start, Codex/OpenCode binaries run **inside coding-runtime**, not on WSL. Provider and GitHub authentication are separate one-time tasks scoped to the proper container/credentials; these are not performed by the installer. For example, only after checking the expected container identity, authenticate Codex via `ddev exec -s coding-runtime codex login`. A new recipient never inherits the previous owner's credentials. Source-merged PRs do not prove this auth mode, the actual model entitlement or the Runtime worker is live.

## Safety and known gaps

- `--check` is read-only. `--prepare` creates local configuration and scoped secrets, but never starts DDEV. `--start` requests DDEV boot **explicitly**; it does not create a coding job or call the model.
- The existing `ddev-executor` still gets the **host Docker socket**. This is a high-privilege boundary; internal Docker networks/project labels alone do not confine its Docker API. Do not infer isolation from the portable boot. Future B2 work needs a separate protected review.
- The Runtime image already includes Python/Node and Codex/OpenCode, but OpenCode still uses an unpinned default version in the existing build path. Do not claim fully reproducible supply-chain provenance until pinned separately.
- Existing n8n/Runtime/Guardian is not yet a proven unattended GitHub task consumer. The PC/WSL/Docker must remain running to work; when powered off, new tasks can queue but cannot execute.
- No automatic migration or rollout to an existing owner's PCP state is authorized, and **no interaction with Chợ Nhạc**, frozen T01/F2, #752 G1-T02, or Guardian is part of this task.

## Acceptance still pending

1. Actual clean disposable WSL2/Docker/DDEV installation (not simulated) with no host Python/Node/agy, scoped auth and no Docker cross-project overlap.
2. Validated startup, service health, restart persistence, scoped one-time provider login, source and secret hygiene.
3. B2 durable authenticated local task intake → Codex work → bounded tests → draft PR → exact GitHub CI → PM review → result. **Zero per-task WSL interaction after setup** is the product target, not an accepted result today.

References: [Phase B #764](https://github.com/sonvhse06072/personal-coding-platform/issues/764), [B1.1 #765](https://github.com/sonvhse06072/personal-coding-platform/issues/765), [DDEV hooks](https://ddev.github.io/ddev/en/stable/users/configuration/hooks/), [DDEV .env scoping](https://ddev.github.io/ddev/en/stable/users/configuration/environment-variables/).
