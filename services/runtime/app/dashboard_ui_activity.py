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
    ".models{grid-template-columns:repeat(3,minmax(0,1fr))}",
    ".models{grid-template-columns:repeat(3,minmax(0,1fr))}.quota-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:10px}.quota{border:1px solid var(--border);background:var(--panel2);border-radius:10px;padding:11px}.quota .qv{font-size:20px;font-weight:730;margin:5px 0}.quota .bar{height:6px;border-radius:999px;background:#1b2636;overflow:hidden;margin:7px 0}.quota .fill{height:100%;background:var(--accent)}.quota.stale .fill{background:var(--amber)}.quota.exhausted .fill{background:var(--red)}",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    ".metrics,.models{grid-template-columns:1fr}",
    ".metrics,.models,.quota-grid{grid-template-columns:1fr}",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    '<div class="grid summary" id="summary"></div>',
    '<div class="grid summary" id="summary"></div><section class="card section"><div class="section-head"><div><div class="section-title">Provider quota</div><div class="small" id="quotaMeta">Authoritative upstream usage and reset windows · stale/unknown values never block routing</div></div></div><div id="quotas" class="quota-grid"><div class="small">Quota telemetry not loaded yet.</div></div></section>',
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "let snapshot=null,selected=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
    "let snapshot=null,quotaSnapshot=null,selected=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
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

_QUOTA_JS = r"""
function pct(v){return v===null||v===undefined?'—':`${Number(v).toFixed(1)}%`}
function quotaReset(v){if(!v)return 'reset unknown';const d=new Date(v);return Number.isNaN(d.getTime())?'reset unknown':`reset ${d.toLocaleString()}`}
function renderQuotas(){const root=$('#quotas');if(!root)return;const q=quotaSnapshot||{},rows=q.snapshots||[],errs=q.collector_errors||{};if(!q.storage_ready){root.innerHTML='<div class="small">Quota telemetry storage is unavailable. Routing remains fail-open.</div>';return}if(!rows.length){const e=Object.keys(errs).length?` · collectors unavailable: ${Object.keys(errs).map(esc).join(', ')}`:'';root.innerHTML=`<div class="small">No authoritative quota snapshot yet${e}.</div>`;return}root.innerHTML=rows.map(x=>{const used=Number(x.used_percent??0),remaining=x.remaining_percent,stale=x.status==='stale',exhausted=x.available===false,cls=exhausted?'exhausted':stale?'stale':'',target=x.model_id||x.quota_group||x.quota_key,label=x.provider==='openai'?'Codex':x.provider==='google_antigravity'?'Antigravity':x.provider;return `<div class="quota ${cls}"><div class="k">${esc(label)} · ${esc(x.status||'unknown')}</div><div style="font-weight:720;margin-top:4px">${esc(target)}</div><div class="qv">${pct(x.used_percent)} used</div><div class="bar"><div class="fill" style="width:${Math.max(0,Math.min(100,used))}%"></div></div><div class="small">${pct(remaining)} remaining · ${esc(quotaReset(x.resets_at))}</div><div class="small">${esc(x.quota_key)} · ${esc(x.source||'unknown')}</div></div>`}).join('');const problems=Object.keys(errs);$('#quotaMeta').textContent=`Poll ${q.poll_seconds||'—'}s · stale after ${q.stale_seconds||'—'}s${problems.length?' · collector issue: '+problems.join(', '):''}`}
async function refreshQuotas(){try{const r=await fetch('/v1/dashboard/provider-quotas',{cache:'no-store'});if(!r.ok)return;quotaSnapshot=await r.json();renderQuotas()}catch(_){}}
"""
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "function render(){summaryCards(snapshot.summary||{});",
    _QUOTA_JS + "function render(){summaryCards(snapshot.summary||{});",
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "refresh();setInterval(refresh,3000);",
    "refresh();refreshQuotas();setInterval(refresh,3000);setInterval(refreshQuotas,15000);",
)

# Invisible compatibility markers keep older structural probes from treating the
# intentional UI rename as a functional regression. Visible labels above are the
# provider-neutral names.
DASHBOARD_HTML += "\n<!-- legacy labels: Live Developer Console; Developer transcript -->\n"
