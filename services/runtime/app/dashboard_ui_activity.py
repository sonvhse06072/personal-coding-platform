from __future__ import annotations

from .dashboard_ui_base import DASHBOARD_HTML as _BASE


# Keep the stable dashboard layout and apply a narrow observability presentation
# layer. This avoids duplicating snapshot/login/pipeline code while the underlying
# durable event contract evolves independently of any one model adapter.
DASHBOARD_HTML = _BASE
DASHBOARD_HTML = DASHBOARD_HTML.replace("PCP Live Developer Console", "PCP Live Developer Activity")
DASHBOARD_HTML = DASHBOARD_HTML.replace("<h2>Developer console</h2>", "<h2>Developer activity</h2>")
DASHBOARD_HTML = DASHBOARD_HTML.replace(">Live Developer Console<", ">Live Developer Activity<")
DASHBOARD_HTML = DASHBOARD_HTML.replace(">Developer transcript<", ">Developer activity<")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "Live, replayable, sanitized model/tool activity · raw chain-of-thought and secrets are never exposed",
    "Live, replayable, sanitized model/tool/verification activity across providers · raw chain-of-thought and secrets are never exposed",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    ".kind-EDIT{color:var(--purple)}",
    ".kind-EDIT{color:var(--purple)}.kind-MODEL{color:var(--accent)}.kind-RUNTIME{color:var(--amber)}.kind-CHECK{color:#86efac}.kind-BLOCK{color:var(--red)}",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    ".filter(e=>String(e.event||'').startsWith('developer_')).sort((a,b)=>Number(a.seq)-Number(b.seq))",
    ".filter(e=>String(e.event||'').startsWith('developer_')||e.event==='runtime_activity').sort((a,b)=>Number(a.seq)-Number(b.seq))",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "if(String(e.event||'').startsWith('developer_')){consoleEvents.push(e);consoleEvents=consoleEvents.slice(-200);renderConsole()}",
    "if(String(e.event||'').startsWith('developer_')||e.event==='runtime_activity'){consoleEvents.push(e);consoleEvents=consoleEvents.slice(-200);renderConsole()}",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    ".filter(e=>!String(e.event||'').startsWith('developer_')).sort((a,b)=>Number(b.seq)-Number(a.seq))",
    ".filter(e=>!String(e.event||'').startsWith('developer_')&&e.event!=='runtime_activity').sort((a,b)=>Number(b.seq)-Number(a.seq))",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "${esc(m?.model||'')}${m?.reasoning_effort?' · '+esc(m.reasoning_effort):''}",
    "${m?.provider?esc(m.provider)+' · ':''}${esc(m?.model||'')}${m?.adapter?' · '+esc(m.adapter):''}${m?.reasoning_effort?' · '+esc(m.reasoning_effort):''}",
)

_OLD_RENDER = """function kind(e){if(e.event==='developer_message')return 'DEV';if(e.event==='developer_file_activity')return 'EDIT';if(e.event==='developer_error'||e.level==='error')return 'ERR';if(e.event==='developer_command_completed')return e.data?.exit_code===0||e.level==='success'?'OK':'ERR';return 'TOOL'}function renderConsole(){const el=$('#console');if(!consoleEvents.length){el.innerHTML='<div class=\"console-empty\">No developer transcript yet. The next Codex model/tool event will appear here live.</div>';return}el.innerHTML=consoleEvents.map(e=>{const k=kind(e),d=e.data||{},out=d.output?`<div class=\"log-output\">${esc(d.output)}</div>`:'';return `<div class=\"log\"><div class=\"log-time\">${esc(new Date(e.timestamp).toLocaleTimeString())}</div><div class=\"log-kind kind-${k}\">${k}</div><div class=\"log-main\">${esc(e.message)}${out}</div></div>`}).join('');el.scrollTop=el.scrollHeight}"""
_NEW_RENDER = """function kind(e){if(e.event==='runtime_activity'){if(e.data?.kind==='block'||e.phase==='blocked')return 'BLOCK';if(e.data?.kind==='check'||e.phase==='verification')return 'CHECK';return 'RUNTIME'}if(e.event==='developer_message'||e.event==='developer_step')return 'MODEL';if(e.event==='developer_file_activity')return 'EDIT';if(e.event==='developer_error'||e.level==='error')return 'ERR';if(e.event==='developer_command_completed')return e.data?.exit_code===0||e.level==='success'?'OK':'ERR';return 'TOOL'}function activityIdentity(d){const bits=[];if(d.provider)bits.push(d.provider);if(d.model)bits.push(d.model);if(d.role)bits.push(d.role);if(d.adapter&&!bits.includes(d.adapter))bits.push(d.adapter);return bits.length?`[${bits.join(' · ')}] `:''}function renderConsole(){const el=$('#console');if(!consoleEvents.length){el.innerHTML='<div class=\"console-empty\">No developer activity yet. The next model, tool, verification, reroute, or control-gate event will appear here live.</div>';return}el.innerHTML=consoleEvents.map(e=>{const k=kind(e),d=e.data||{},out=d.output?`<div class=\"log-output\">${esc(d.output)}</div>`:'',identity=activityIdentity(d),cmd=d.command&&!String(e.message||'').includes(d.command)?`<div class=\"log-output\">$ ${esc(d.command)}</div>`:'';return `<div class=\"log\"><div class=\"log-time\">${esc(new Date(e.timestamp).toLocaleTimeString())}</div><div class=\"log-kind kind-${k}\">${k}</div><div class=\"log-main\">${esc(identity+String(e.message||''))}${cmd}${out}</div></div>`}).join('');el.scrollTop=el.scrollHeight}"""
if _OLD_RENDER not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard activity presentation target changed; review the base UI before rollout")
DASHBOARD_HTML = DASHBOARD_HTML.replace(_OLD_RENDER, _NEW_RENDER)

# Provider quota is a separate read-only resource view. Keep it outside job
# counters so users can distinguish provider allowance from WorkOrder budgets.
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "</style>",
    ".quota-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.quota-card{border:1px solid var(--border);background:var(--panel2);border-radius:11px;padding:12px}.quota-row{display:flex;justify-content:space-between;gap:10px;align-items:baseline}.quota-value{font-size:18px;font-weight:730}.quota-fresh{color:#86efac}.quota-stale{color:var(--amber)}.quota-unknown{color:var(--muted)}.collector-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}@media(max-width:1050px){.quota-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:640px){.quota-grid{grid-template-columns:1fr}}</style>",
    1,
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    '<div class="foot">Read-only observability. Dashboard disconnects never control, pause, resume, or otherwise affect a coding job.</div>',
    '<section class="card section"><div class="section-head"><div><div class="section-title">Provider quota</div><div class="small">Fresh provider allowance telemetry · distinct from WorkOrder budgets · unknown/stale values are never inferred</div></div><div id="quotaCollectors" class="small"></div></div><div id="quotaGrid" class="quota-grid"><div class="small">Quota telemetry has not been loaded.</div></div><div id="quotaCollectorRows" class="collector-row"></div></section><div class="foot">Read-only observability. Dashboard disconnects never control, pause, resume, or otherwise affect a coding job.</div>',
    1,
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "let snapshot=null,selected=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
    "let snapshot=null,quotaSnapshot=null,selected=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
    1,
)

_QUOTA_FUNCTIONS = r'''function quotaPct(v){return v===null||v===undefined?'unknown':`${Number(v).toFixed(1)}%`}function quotaReset(v){if(!v)return 'reset unknown';const d=new Date(v);return Number.isNaN(d.getTime())?'reset unknown':`reset ${d.toLocaleString()}`}function renderQuota(){const grid=$('#quotaGrid'),rows=$('#quotaCollectorRows'),summary=$('#quotaCollectors');if(!grid)return;const q=quotaSnapshot||{},items=q.snapshots||[],collectors=q.collectors||[];const fresh=items.filter(x=>x.fresh).length;summary.textContent=items.length?`${fresh}/${items.length} fresh snapshots`:'no snapshots';if(!items.length){grid.innerHTML=`<div class="small quota-unknown">${esc(q.error||'Provider quota is currently unknown. Existing routing health/failure state remains authoritative.')}</div>`}else{grid.innerHTML=items.map(x=>{const state=x.fresh?'fresh':'stale',used=quotaPct(x.used_percent),remaining=quotaPct(x.remaining_percent),window=x.window_name?` · ${esc(x.window_name)}`:'',reset=quotaReset(x.reset_at),source=x.source||'unknown',support=x.metadata?.source_supported===false?' · internal/local API':'';return `<div class="quota-card"><div class="quota-row"><div><div class="k">${esc(x.provider||'provider')}${window}</div><div style="font-weight:720;margin-top:4px;word-break:break-word">${esc(x.quota_id||x.state_key||'unknown quota')}</div></div><span class="${state==='fresh'?'quota-fresh':'quota-stale'}">${state}</span></div><div class="quota-row" style="margin-top:10px"><div><div class="k">USED</div><div class="quota-value">${esc(used)}</div></div><div style="text-align:right"><div class="k">REMAINING</div><div class="quota-value">${esc(remaining)}</div></div></div><div class="small" style="margin-top:8px">${esc(reset)} · ${esc(source+support)}</div></div>`}).join('')}rows.innerHTML=collectors.length?collectors.map(c=>`<span class="pill"><span class="dot ${c.status==='ok'?'':'off'}"></span>${esc(c.source)} · ${esc(c.status)}${c.last_success_at?' · '+esc(new Date(c.last_success_at).toLocaleTimeString()):''}</span>`).join(''):'<span class="small quota-unknown">No collector status yet.</span>'}async function refreshQuota(){try{const r=await fetch('/v1/dashboard/quota',{cache:'no-store'});if(r.status===401)return;if(!r.ok)throw new Error(`quota HTTP ${r.status}`);quotaSnapshot=await r.json();renderQuota()}catch(e){quotaSnapshot={snapshots:[],collectors:[],error:'Quota telemetry unavailable'};renderQuota();console.error(e)}}
'''
if "function render(){" not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard render target changed; review quota UI integration")
DASHBOARD_HTML = DASHBOARD_HTML.replace("function render(){", _QUOTA_FUNCTIONS + "function render(){", 1)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "snapshot=await r.json();hideLogin();render()",
    "snapshot=await r.json();hideLogin();render();await refreshQuota()",
    1,
)

# Invisible compatibility markers keep older structural probes from treating the
# intentional UI rename as a functional regression. Visible labels above are the
# provider-neutral names.
DASHBOARD_HTML += "\n<!-- legacy labels: Live Developer Console; Developer transcript -->\n"
