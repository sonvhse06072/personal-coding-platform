# G0D-01 Bootstrap v2 — 2026-10-10

- Corrects `ddev list -j` decoding: DDEV 1.25.x returns a JSON envelope with `.raw[]` and can emit newline-delimited informational envelopes.
- Adds a hard **no-touch** preflight gate. When **any other DDEV project** is running, healthy, paused or otherwise not clearly stopped, the bootstrap refuses to call `ddev config` or `ddev start`; it does not stop those projects. The shared router is explicitly exempt from the project status rule.
- Handles malformed/missing JSON, unknown project status, target-name collision, symlink target and preexisting fixture without modification. A fake DDEV binary in offline tests proves that Chợ Nhạc `running` prevents target creation or DDEV startup.
- Replaces prior bootstrap ZIP; **do not run the older ZIP**. Neither ZIP is equivalent to a verified Drupal 11 installation, Composer lock, DDEV environment or GitHub-hosted Kernel test.

**Operational restriction:** Since Chợ Nhạc is currently running in the Owner's DDEV environment, running this bootstrap on that WSL host is deliberately BLOCKED. Use a separate isolated VM/runner where no other DDEV projects run. Do not stop/restart Chợ Nhạc to bypass the gate.
