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
