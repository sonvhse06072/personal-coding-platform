# #832: same-identity #831 recovery and integrated rollout packet

Source WorkOrder: [PM6496080714](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6496080714).
[Independent review5697253728](https://github.com/sonvhse06072/personal-coding-platform/pull/832#pullrequestreview-5697253728)
accepts the narrow lease correction at79f7f4 and holds merge for this integrated
recovery. One writer, same [PR832](https://github.com/sonvhse06072/personal-coding-platform/pull/832),
branch `ai/815-successor831-live`, checkout `/home/sonvh/pcp-successor831-live`.
No source/adoption/PM acceptance is inferred from this report.

## Immutable identity and retained physical state

Task source **S=b97ade581fecad4db2146258e5ca02c3902189e0** remains main during
source work. Future **R is the independently accepted merge of completed832**;
it is unknown now. Baseline `pcp-local-successor-830-b97ade5-20261029` stays pinned
to S, including its authority classes. No baseline revision is rewritten.

- Issue831 body SHA256 `c05077c5838a3fb1fbd0ba53930f2348fc7ec52531a049df55761540ed000858`.
- Goal SHA256 `b3d8bbf7a58da8d15605d23670e02f4b3af9d2c966cdfdf8f45d424a41e47640`.
- Same deterministic job `a8851f89dd3e4e582c697ec1fe6d8cdb`.
- Same three paths: `scripts/pcp-light-evidence-summary.py`,
  `tests/test_pcp_light_evidence_summary.py`, `docs/pcp-light/evidence-summary.md`.
- Original receipt **claimed/gen1**, no job/lease/workspace/model/remote branch/PR.
  Raw private preimage hash `32b527abe26e594c58fc4c96614cebd75bfe33883379f624b8c40088bde9540e`
  uses `json.dumps(to_jsonb(receipt), indent=2) + '\n'`, PostgreSQL JSONB key order.
  The permit additionally binds the parsed entire row; it never refreshes it.
- Backup `v4-blocked.dump`,29082B, SHA256
  `2161e71599a83b57decb542c8e7c3b43d1c07678c21cbb416cba5836887abd8a`.
- Original disabled activation raw SHA256
  `bfa447d7e79afe7f53267598d280beb084c6a88ebf6d8dcb5d22f9b05a5752a4`,
  canonical digest `04687cdd66588566f0b4a5d6680fcfcc0f19f186c9dd26ed7187ececcd3c58c2`,
  expiry2026-10-30T10:51:28.134568Z remains unchanged. A new permit has its own expiry.

Private evidence: `/home/sonvh/.local/state/pcp-831-claim-recovery-v1`;
original evidence `/home/sonvh/.local/state/pcp-successor831-live-v1` remains intact.
Full dumps, manifests, inspect/env/auth data are private, never PR attachments.
Existing running/stopped V4 identities are in the [original receipt](2026-10-29-successor831-live.md#backups-shutdown-and-dashboard)
and [operations](../../pcp-portable/local-operations.md#current831-execution-and-no-replay-checkpoint).
Only DB8b72a8…, observer5d6b3e… and frontendd22a5b… remain running. Historical S
workers f8d63b… / cade4f… / f03edb… remain stopped. V3/rollback resources untouched.
**https://localhost:18443/dashboard**, trusted HTTPS, `loopback_readonly`, no
login/token/cookie. A claim without a job does not appear as an admitted job.

## Behavior and evidence

`PCP_LOCAL_CLAIM_RECOVERY_ENABLED=owner-approved` plus fixed private
`/config/pcp-local-claim-recovery.json` and byte-exact
`/config/pcp-local-original-activation.json` are required. Both files must be
regular, private0600, root/service-owned. No HTTP assertion supplies authority.
No original activation expiry/image/source value is overwritten. The effective
activation carries a separate recovery decision, included in observation digests.

| Boundary | Behavior |
| --- | --- |
| Plan | Read-only repeatable-read snapshot; full original receipt or exact audited job; competing ownership blocks readiness to register/execute. |
| Register | Existing strict registrar, lock(5260112,808), full receipt comparison, no competing job/claim/lease; one job/event plus full original registered preimage/audit in one transaction. Receipt stays claimed/gen1. No enqueue/model. |
| Duplicate/COMMIT uncertainty | GET plan first. Exact durable registration is returned; no second INSERT/event/enqueue. Conflicting decision or drift fails closed. PostgreSQL sequence gaps after rolled-back INSERT are retained, never reset. |
| Explicit execute | Separate session lock(5260112,831), fresh readiness and absence of workspace/remote side effects, one local queue hydration. Full-row fence consumes claimed/gen1→running/gen2 before lease/model. |
| Crash around queue | Before enqueue can retry the explicit execute step after exact reconciliation; lost enqueue acknowledgement reuses its same local item. A restarted process hydrates from the unchanged audited queued job. |
| Crash after fence | `execution_fenced_no_replay`; observe-only even before lease/model. No automatic reset or second invocation. |
| Verified/terminal | `verified_delivery_only` uses existing verified commit/publisher reconciliation; `terminal_observe_only` never resumes. No self-approval. |
| Task/platform split | GitHub actual main=R, exact S ancestry/commit/path range, no pilot-path changes including reverted intermediate edits. Runtime/ExecutorR, verifierS, RouterS only with unchanged service/model/policy inputs. Normal fresh admission checks are unchanged and run-once is disabled in recovery mode. |

SOURCE/FIXTURE evidence: supported permit/registrar/readiness/HTTP/queue checks,
real temporary-Git history and actual observe-route integration. The new positive
observe regression on old79f7f4 fails409 `pcp_local_runtime_isolation_invalid`;
repaired path accepts the explicit mapping, reports actual mainR and verifies S.
The original17 lease/readiness regressions are retained. Real PostgreSQL tests
exercise full receipt/job drift, races, competing ownership, rollback, lost
COMMIT/enqueue acknowledgements, and running fence crashes. Provider/GitHub/Docker
observations in those cases are explicit doubles; no model is invoked.

Final restored-copy rehearsal PASS (initial copy and its evidence also retained): original dump hash verified, restored with
`pg_restore --exit-on-error --no-owner --no-privileges` into isolated
`pcp831_rehearsal_candidate`; scoped real role `pcp_831_fixture_runtime_candidate` passed schema/sequence
rights. Pinned PostgreSQL17 image
`sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27`;
container `cc373616aff0b6a0143aca906ada559b87200ab4ea6a4f26d93c7a81ea5580c8`,
name `pcp-831-claim-recovery-fixture-v1`, network=none, no published ports, its own
anonymous volume and private Unix-socket bind. No live V4/V3 volume mounted.
Actual original receipt/active S baseline registered the SAME job through the
production registrar: claimed/gen1 preserved, one job/event, zero lease/model/test/
enqueue, other tables unchanged; exact retry unchanged. A fixture fence then
produced running/gen2 and prevented replay, preserving the complete job/zero
counters. External release/provider/remote authority was synthetic; its `e…e`
repair SHA is explicitly a fixture, not predicted or accepted R.

| Private rehearsal evidence | SHA256 |
| --- | --- |
| Full restored before rows | `ec7721bd5febe2abfe6032ef5316f85d5f625264c50544bf303c813bf9f49f4b` |
| Registered rows | `b964ee0f47f7675ad1fa6ce9beabcbca0b36e35f51a691fd5e8013e0ff6b1543` |
| Fenced rows | `7f517b57bad5b6494355234ea6fafbe16e5b87b586807b0cb7a41c037d8f6532` |
| Private fixture permit bytes | `279f6fbe200cd4016edb6eee86a1cac293e1372f28f5acf8ecc2ffe3bc54f1d8` |
| Canonical fixture permit decision | `d662fb3a5e64f2488d194b00d767ed247822e0b37c5260db77b2782e1dc7a697` |

The fixture is now **stopped/exited**, restart=no; no resources were removed.
Its private retained volume is
`15323622f35530813acd8397d1c94b19cf3b202d7f7bf679a0c6bdface28fc07`.
The final consistent34451B after dump has SHA256
`53ae3b9e05d070e3843540e9c3d8f7dec840ba6d1d4b3ee41c2146bcf8914a22`;
`pg_restore --list` passed. Earlier isolated copies/dumps are retained too.
Final read-only LIVE comparison matches all11 tables/three sequence values and
hash `62491980c3c6ab686661035c43175bedb19cc3915e877c172598b018bce94dff`;
all39 V4 container configs/images/mount records/running states match the preimage
(Docker mount-list enumeration sorted, no fields dropped). Main still S.

Full local verification: structure1742, Runtime2571/165 skipped, Router132,
Executor794 = **5239 passed/165 skipped**. Separately **91 passed** with actual
PostgreSQL enabled (77 database cases plus14 permit/client cases); these do not
turn the other skipped integrations into passes. Packet shell/Python blocks were
syntax checked without executing rollout. All four hosted suites must genuinely
execute on the final PR head; the exact run/head receipt is maintained on
[PR832](https://github.com/sonvhse06072/personal-coding-platform/pull/832), not inferred
from earlier-head CI or local tests. No protected packaging allowlist was changed:
the recovery code uses the existing task-queue helper and its approved image path.

PHYSICAL: isolated PG container/restore and trusted unchanged dashboard availability
are measured. LIVE recovery, R build/adoption, provider entitlement now, publisher
write,831 implementation/verification/Draft PR/CI, populated dashboard, VPN ON/parity
are **NOT TESTED** by this source session. Fixture PASS is not their acceptance.

## Single later integrated rollout — preparation, not current permission

PM must review the final PR832 diff/tests/rehearsal, approve eligible merge, obtain
all four genuinely executed postmerge suites and name exact R plus an integrated
execution record. The following commands belong only to that later decision.
Do not use79f7f4, the development head, fixture permit, or a newer arbitrary main
as R. A mismatch stops dependent mutation; retain evidence and continue independent
checks. No routine per-step Owner confirmation is necessary after that decision.

### 1. Accepted source, custody and build

Use a standalone shell/script, never set `-e` in the Owner's persistent shell.
Set `PCP_REPAIR_R` to the accepted full merge SHA and `PCP_RECOVERY_RECORD` to the
later815 execution-comment URL. These are mandatory operator inputs, not defaults.
The stopped old workers and their exact private create intents are retained.
Verify original hashes above, receipt/job/lease state by read-only DB reads, remote
`ai/a8851f89dd3e` branch and all-state PR absence, unchanged831 body and dashboard.
Take another consistent private `pg_dump -Fc` and full rows/sequences snapshot
before installing anything; compare to retained preimages, never rewrite them.

```sh
bash <<'SH'
set -eu
: "${PCP_REPAIR_R:?PM accepted merge SHA required}"
: "${PCP_RECOVERY_RECORD:?postmerge execution record required}"
test "${#PCP_REPAIR_R}" = 40
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
export PCP_REPAIR_R PCP_RECOVERY_RECORD
python3 - <<'PY'
import hashlib,json,os,subprocess,tarfile,re,stat
from pathlib import Path
S='b97ade581fecad4db2146258e5ca02c3902189e0';R=os.environ['PCP_REPAIR_R']
assert re.fullmatch('[0-9a-f]{40}',R) and R!=S
old=Path('/home/sonvh/.local/state/pcp-successor831-live-v1')
root=Path('/home/sonvh/pcp-local-adoption825-v4');rel=root/'releases'/('claim-recovery-'+R)
repo=Path('/home/sonvh/pcp-successor831-live')
D=['docker','--host','unix:///var/run/docker.sock']
def run(args):return subprocess.check_output(args,text=True).strip()
assert run(['git','-C',str(repo),'ls-remote','origin','refs/heads/main']).split()[0]==R
subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin',R],check=True)
subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',S,R],check=True)
record=old/'release-record.json'
assert hashlib.sha256(record.read_bytes()).hexdigest()=='6a40092f63997362155a0ea269a575a0c069a9f467afd546282e1917b50ee814'
pins=json.loads(record.read_text())['pins']
rel.mkdir(mode=0o700);(rel/'logs').mkdir();(rel/'rollback').mkdir();(rel/'build').mkdir()
subprocess.run(['git','clone','--no-local','--no-hardlinks',str(repo),str(rel/'source')],check=True)
subprocess.run(['git','-C',str(rel/'source'),'checkout','--detach',R],check=True)
assert not run(['git','-C',str(rel/'source'),'status','--porcelain'])
archive=rel/'services.tar'
with archive.open('xb') as f:subprocess.run(['git','-C',str(repo),'archive',R,'services/runtime','services/ddev-executor'],stdout=f,check=True)
with tarfile.open(archive) as tar:
 assert all(not m.issym() and not m.islnk() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in tar.getmembers())
 tar.extractall(rel/'build',filter='data')
images={}
for service in ('runtime','ddev-executor'):
 context=rel/'build/services'/service
 dockerfile=context/'Dockerfile.local';base=pins['node'] if service=='runtime' else pins['python']
 dockerfile.write_text('FROM '+base+'\n'+(context/'Dockerfile').read_text().split('\n',1)[1])
 for f in [context]+list(context.rglob('*')):
  assert not f.is_symlink()
  mode=stat.S_IMODE(f.stat().st_mode);f.chmod(mode|0o044|(0o011 if f.is_dir() or mode&0o111 else 0))
 iid=rel/'logs'/(service+'.iid');tag=root.name+'-'+service+':'+R
 assert not run(D+['image','ls','-q','--filter','reference='+tag])
 argv=D+['build','--builder','default','--file',str(dockerfile),'--tag',tag,'--iidfile',str(iid),
  '--label','org.opencontainers.image.revision='+R,'--label','org.pcp.local.instance='+root.name,
  '--build-arg','CODEX_VERSION='+pins['codex'],'--build-arg','OPENCODE_VERSION='+pins['opencode'],
  '--build-arg','DDEV_UID=1000','--build-arg','DDEV_GID=1000',str(context)]
 with (rel/'logs'/(service+'.build.log')).open('x') as log:subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
 images[service]=iid.read_text().strip()
 assert json.loads(run(D+['image','inspect',images[service]]))[0]['Config']['Labels']['org.opencontainers.image.revision']==R
(rel/'images.json').write_text(json.dumps(images,indent=2)+'\n')
# Populate R objects for read-only range verification; task checkout stays S.
canonical=root/'sources/personal-coding-platform'
assert run(['git','-C',str(canonical),'rev-parse','HEAD'])==S and not run(['git','-C',str(canonical),'status','--porcelain'])
subprocess.run(['git','-C',str(canonical),'fetch','--no-tags',str(rel/'source'),R],check=True)
PY
SH
```

Before adoption, inspect both actual images and archive/input trees; repeat the
existing offline non-root/read-only/noexec/tmpfs packaging probes with network=none
and no provider credentials. Compare shipped files and executable Git modes,
Docker20/Buildx/Git/pytest8.4.1/PyYAML6.0.2/Codex0.160.0 and immutable executable
askpass outside `/tmp`. Keep RuntimeS
`sha256:6f057d0851e3c3e6daefc9509341683974c52d7e8256900a81b597fba7b55089`
for verification. Retain RouterS
`sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319`;
require no commit in S..R touching services/router, config/models.yml or
config/routing-policy.yml. Do not rebuild or swap observer51349.

### 2. Create reviewed R workers, preserve registry, install fresh private permit

Keep the original four configuration files byte-exact: projects21f5df8…, baseline
0cdff53…, modelsa748fa…, policycc71c6… (full hashes in the original receipt).
Keep the existing credential files/homes and their boundaries. Do not execute the
old `start-runtime.py`: it creates another activation/auth home. Do not execute
old install scripts: they describe the prior baseline transition. The block below
reuses only hash-verified **recorded Docker create argv**, with explicit R/image/
recovery-switch deltas, and never prints private env or credential contents.
Original workers are retained under new stopped names; RouterS retains its ID.

```sh
bash <<'SH'
set -eu
: "${PCP_REPAIR_R:?required}" "${PCP_RECOVERY_RECORD:?required}"
export PCP_REPAIR_R PCP_RECOVERY_RECORD
python3 - <<'PY'
import hashlib,json,os,subprocess,time
from pathlib import Path
root=Path('/home/sonvh/pcp-local-adoption825-v4');old=Path('/home/sonvh/.local/state/pcp-successor831-live-v1')
R=os.environ['PCP_REPAIR_R'];rel=root/'releases'/('claim-recovery-'+R);cfg=root/'instance/config'
D=['docker','--host','unix:///var/run/docker.sock']
def run(args):return subprocess.check_output(args,text=True).strip()
def inspect(kind,name):return json.loads(run(D+[kind,'inspect',name]))[0]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def configuration(row):
 v={k:row[k] for k in ('Name','Config','HostConfig','Mounts')};v['Mounts']=sorted(v['Mounts'],key=lambda m:m['Destination'])
 return digest(v)
def save(path,value):
 with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
 path.chmod(0o600)
assert run(['git','-C',str(rel/'source'),'rev-parse','HEAD'])==R
assert not (cfg/'pcp-local-activation.json').exists()
assert not (cfg/'pcp-local-claim-recovery.json').exists()
expected={'projects.pcp-local.yml':'21f5df8c08c38c65a6f861702b2de9d287e89a32656a4ceb81c958369c057983',
 'project-baselines.pcp-local.yml':'0cdff53f95c5bcc15c780acee87d5d925d6c8cd9cf77afe60bca68a9da0a7021',
 'models.yml':'a748faf933fe5c792679a687f2b0870f97fb6f6af8bd70887cc9bb4d8758844d',
 'routing-policy.yml':'cc71c65bec662e4726ee056525f0a02a6a1bfd9e1f09f92abad22a37b9c9d615'}
assert all(sha(cfg/name)==value for name,value in expected.items())
images=json.loads((rel/'images.json').read_text());ids={}
inputs={'runtime':('f8d63b9721d37883ad111fd1e3cd46b79cb39b8535cfadc856d5dff791ceb938',
 '5c37b265d5e7616a570c3952a6b56a0adca3d3bd333af21e2fb9a25a1dc54807'),
 'ddev-executor':('cade4f36d11544a1bda50145a3d5095e7a92b7d561d1822e5d168196279479b8',
 'a54f615c49ce48a16ace8a2823bfec6c64bdb17abab8349a060c046ce5ae30fb')}
# Reconcile every input before the first rename/create.
intents={}
for service,(cid,expected_hash) in inputs.items():
 path=old/(service+'-create-intent.json');assert sha(path)==expected_hash
 row=inspect('container',cid);assert not row['State']['Running']
 argv=json.loads(path.read_text())['argv'];name=argv[argv.index('--name')+1]
 assert row['Name']=='/'+name and row['Image']!=images[service]
 intents[service]=(cid,name,argv)
for service,(cid,name,argv) in intents.items():
 run(D+['rename',cid,name+'-retained-S-'+cid[:8]])
 argv=list(argv);argv[-1]=images[service]
 for i,value in enumerate(argv):
  if value.startswith('org.opencontainers.image.revision='):argv[i]='org.opencontainers.image.revision='+R
  elif value.startswith('org.pcp.workorder='):argv[i]='org.pcp.workorder='+os.environ['PCP_RECOVERY_RECORD'].rsplit('-',1)[-1]
  elif value.startswith('PCP_LOCAL_SOURCE_COMMIT='):argv[i]='PCP_LOCAL_SOURCE_COMMIT='+R
 argv[-1:-1]=['--env','PCP_LOCAL_CLAIM_RECOVERY_ENABLED=owner-approved','--env','PCP_LOCAL_SOURCE_COMMIT='+R]
 save(rel/(service+'-create-intent.json'),{'argv':argv,'replaces_stopped':cid})
 ids[service]=run(argv)
 save(rel/(service+'-created.json'),{'id':ids[service],'image':images[service]})
ids['router']='f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6'
assert not inspect('container',ids['router'])['State']['Running']
raw=(old/'activation-original-private.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='bfa447d7e79afe7f53267598d280beb084c6a88ebf6d8dcb5d22f9b05a5752a4'
a=json.loads(raw);S=a['base_sha']
with (cfg/'pcp-local-original-activation.json').open('xb') as f:f.write(raw)
(cfg/'pcp-local-original-activation.json').chmod(0o600)
receipt=old/'claimed-receipt-original-private.json'
assert sha(receipt)=='32b527abe26e594c58fc4c96614cebd75bfe33883379f624b8c40088bde9540e'
roles={'verifier':{'image_id':a['verification_image'],'source_commit':S}}
for role,service in (('runtime','runtime'),('executor','ddev-executor'),('router','router')):
 row=inspect('container',ids[service]);source=R if role!='router' else S
 image=inspect('image',row['Image'])
 assert row['Image']==row['Config']['Image'] and image['Config']['Labels']['org.opencontainers.image.revision']==source
 assert all(m['BindOptions']=={'NonRecursive':True} for m in row['HostConfig']['Mounts'] if m['Type']=='bind')
 roles[role]={'image_id':row['Image'],'source_commit':source,'configuration_sha256':configuration(row)}
 save(rel/(role+'-configuration-private.json'),row)
repo=str(rel/'source')
commits=run(['git','-C',repo,'rev-list','--reverse','--topo-order',S+'..'+R]).splitlines()
paths=sorted(run(['git','-C',repo,'diff','--no-renames','--name-only',S,R,'--']).splitlines())
now=time.time()
permit=dict(version=1,decision_id='PCP-831-RECOVERY-'+R[:12],execution_record=os.environ['PCP_RECOVERY_RECORD'],
 not_before=now,expires_at=now+86400,receipt_before=json.loads(receipt.read_text()),
 original_activation_sha256=hashlib.sha256(raw).hexdigest(),original_activation_digest=digest(a),
 repair_source=R,repair_commits=commits,repair_paths=paths,roles=roles)
save(rel/'recovery-permit-private.json',permit);save(cfg/'pcp-local-claim-recovery.json',permit)
save(rel/'worker-ids.json',ids)
# No baseline/config counter/task edits; no models or ownership operations here.
for service in ('router','ddev-executor','runtime'):run(D+['start',ids[service]])
PY
SH
```

Reconcile a partially completed create/start from the saved per-service intents
and IDs before retrying. Never rerun the whole block after an uncertain result.
The runtime/executor mounted registry remains the existing private directory;
new files are only the original evidence copy and the new permit. No credential
is added to an image, observer or developer subprocess. Preserve separate fresh
build/inspect receipts for R, original S verifier/Router and observer51349.
Actual readiness must verify matching config fingerprints after startup. Do not
refresh a mismatched approved digest merely to accept Docker/config drift.

### 3. Full readiness, read-only plan, registration, reconciliation, execution

Run these using the **new Runtime container ID** in `worker-ids.json`. The client
uses its existing private bearer from the container environment and the shipped
internal8787 listener; no token is placed on argv, terminal or dashboard. The
default action is plan (GET). Each POST is deliberate; a transport/HTTP failure
requires GET/DB/remote reconciliation first, never an automatic retry loop.

```sh
bash <<'SH'
set -eu
: "${PCP_REPAIR_R:?required}"
PCP_RELEASE="/home/sonvh/pcp-local-adoption825-v4/releases/claim-recovery-${PCP_REPAIR_R}"
PCP_RUNTIME_ID=$(python3 - "$PCP_RELEASE/worker-ids.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['runtime'])
PY
)
docker --host unix:///var/run/docker.sock exec "$PCP_RUNTIME_ID" \
  python -m app.pcp_local_task_queue readiness
docker --host unix:///var/run/docker.sock exec "$PCP_RUNTIME_ID" \
  python -m app.pcp_local_task_queue plan
SH
```

Require readiness.ready=true with zero model/registration calls, and plan
`unregistered`, exact job/taskS/repairR/permit hash. Readiness includes actual
Runtime Git identity/toolchain, real schema/sequence rights, original approved
baseline and exclusive=True policy, current GitHub body/main, actual per-role
images/mounts/network/observer, scoped publisher and authoritative subscription
quota. Publisher PAT expires2026-11-04T08:29:46Z; preserved login validity is not
assumed. Only a genuine interactive account step goes to Owner, after independent
checks finish. Do not reset auth/counters or alter source to silence a blocker.

After the later integrated PM execution record authorizes this exact permit:

```sh
bash <<'SH'
set -eu
: "${PCP_REPAIR_R:?required}"
PCP_RUNTIME_ID=$(python3 - "$PCP_REPAIR_R" <<'PY'
import json,sys
from pathlib import Path
p=Path('/home/sonvh/pcp-local-adoption825-v4/releases')/('claim-recovery-'+sys.argv[1])/'worker-ids.json'
print(json.loads(p.read_text())['runtime'])
PY
)
docker --host unix:///var/run/docker.sock exec "$PCP_RUNTIME_ID" python -m app.pcp_local_task_queue register
docker --host unix:///var/run/docker.sock exec "$PCP_RUNTIME_ID" python -m app.pcp_local_task_queue plan
SH
```

Require `registered_not_started`, exactly one queued job/audit, original full
receipt still claimed/gen1, zero model/test counters and no lease/workspace/
remote effects. Record the job's full registered preimage privately. After lost
registration acknowledgement, plan plus exact DB afterimages determine whether
it committed; a duplicate register is read-only reconciliation. Never regenerate
the expected receipt or change decision ID to force acceptance.

```sh
bash <<'SH'
set -eu
: "${PCP_REPAIR_R:?required}"
PCP_RUNTIME_ID=$(python3 - "$PCP_REPAIR_R" <<'PY'
import json,sys
from pathlib import Path
p=Path('/home/sonvh/pcp-local-adoption825-v4/releases')/('claim-recovery-'+sys.argv[1])/'worker-ids.json'
print(json.loads(p.read_text())['runtime'])
PY
)
# Explicit single execution, only after the preceding state has been validated.
docker --host unix:///var/run/docker.sock exec "$PCP_RUNTIME_ID" python -m app.pcp_local_task_queue execute
SH
```

No run-once/new admission is used. If the request disconnects, check plan, job/
receipt/lease/counters/workspace and remote state. `registered_not_started` may
continue only with its exact initial preimage and no incompatible effects;
`execution_fenced_no_replay` requires PM disposition, not another execution.
`verified_delivery_only` permits the existing authenticated delivery reconciler
(`python -m app.pcp_local_task_queue deliver`) after exact proof/lease/remote
checks; it must not invoke a model. An expired/conflicting permit is not silently
reissued: preserve the audit and seek a concrete PM disposition.

### 4. Delivery, observation, shutdown and successor frame

Mandatory verification uses retained verifierS, task workspaceS plus only the
original three paths, actual executed targeted/full tests, unchanged verified
Git tree/modes/single parent, same lease/usage and one truthful commit. Before
publication retry, reconcile exact remote branch tip and all-state PRs; never
blindly create another Draft PR. Require a real Draft task PR and all required
executed hosted suites at its exact final head, then independent PM acceptance.
The repair PR832 is not the task's delivery PR.

Keep trusted tokenless HTTPS observer51349 available throughout. Check the actual
job projection, terminal duration from durable evidence, Unknown/zero/partial/
estimated usage provenance and reconnect after real job transitions. Fixture
checks cannot establish deployment or VPN parity. Measure connectivity in the
Owner's reported current VPN state; mark the other state NOT TESTED until Owner
voluntarily switches, without changing global VPN/DNS/trust/network settings.

Capture consistent post-state dump, full rows/sequences, proof/counter hashes,
permit/activation/image/container fingerprints and remote/CI receipts privately.
Stop only the three new/reused worker IDs from `worker-ids.json`; preserve all
containers, volumes, workspaces, images, credentials and evidence. Keep DB/
observer/frontend up. Disable the new permit by moving it intact into this
release's rollback directory **after stopping workers**; never restore the old
activation. Reconcile uncertain stop outcomes by exact ID before another stop.

```sh
bash <<'SH'
set -eu
: "${PCP_REPAIR_R:?required}"
python3 - <<'PY'
import json,os,subprocess
from pathlib import Path
root=Path('/home/sonvh/pcp-local-adoption825-v4')
rel=root/'releases'/('claim-recovery-'+os.environ['PCP_REPAIR_R'])
ids=json.loads((rel/'worker-ids.json').read_text())
D=['docker','--host','unix:///var/run/docker.sock']
for role in ('runtime','ddev-executor','router'):
 cid=ids[role];row=json.loads(subprocess.check_output(D+['inspect',cid]))[0]
 assert row['Id']==cid and row['Config']['Labels']['org.pcp.local.instance']==root.name
 if row['State']['Running']:subprocess.run(D+['stop','--time','15',cid],check=True,timeout=90)
permit=root/'instance/config/pcp-local-claim-recovery.json';target=rel/'rollback/disabled-recovery-permit.json'
assert not target.exists();permit.rename(target)
PY
SH
```

Rollback means preserve and stop the new workers/permit, **not** replay old S
workers, restore a DB over consumed ownership, release a lease, rewind counters
or publish the assisted V3 commit. Original V3 resources stay untouched. Source
S baseline remains the831 task authority until its independent disposition.
A successor baseline for subsequent fresh tasks is a **new immutable draft at R**
with final accepted build/input/image bindings and preserved protected classes;
activation and any next task require their own eligible PM decision. The next
currently admissible work is the existing same831 three-path evidence-summary
task under this recovery checkpoint, not a replacement issue.
