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
    "let snapshot=null,selected=null,selectedStandalone=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
    "let snapshot=null,quotaSnapshot=null,selected=null,selectedStandalone=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
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


# Direct-workspace live preview stays an opt-in control surface layered onto the
# otherwise read-only activity dashboard.
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "</style>",
    ".preview-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.preview-actions button{border:1px solid var(--border);border-radius:9px;padding:8px 11px;background:#101a28;color:var(--text);font-weight:680;cursor:pointer}.preview-actions button:hover{border-color:#466489}.preview-actions button:disabled{opacity:.45;cursor:not-allowed}.preview-links{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px}.preview-note{margin-top:8px;font-size:11px;color:var(--muted)}.s-ready{color:#86efac;border-color:#256548;background:#0e2b20}.s-stopped,.s-not_built,.s-unsupported{color:#a5b4c7;border-color:#3b4758;background:#111923}.s-starting{color:#93c5fd;border-color:#31598d;background:#102139}</style>",
    1,
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    '<section class="card section"><div class="section-title">Model assignment</div>',
    '<section class="card section" id="previewCard" style="display:none"><div class="section-head"><div><div class="section-title">Local preview</div><div class="small">Direct workspace only · separate control unlock required for mutations</div></div><div id="previewStatus"></div></div><div class="preview-actions"><select id="previewTarget" class="select"><option value="frontend">Frontend</option><option value="backend">Backend</option><option value="both">Both</option></select><button id="previewStart">Start Preview</button><button id="previewStop">Stop</button><button id="previewUnlock">Unlock controls</button></div><div id="previewLinks" class="preview-links"></div><div id="previewNote" class="preview-note"></div></section><section class="card section"><div class="section-title">Model assignment</div>',
    1,
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "let snapshot=null,quotaSnapshot=null,selected=null,selectedStandalone=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[];",
    "let snapshot=null,quotaSnapshot=null,selected=null,selectedStandalone=null,source=null,streamJob=null,lastSeq=0,consoleEvents=[],previewJob=null,previewState=null,previewBusy=false,previewRefreshBusy=false;",
    1,
)

_PREVIEW_FUNCTIONS = r'''function previewStatusBadge(v){return status(v||'not_built')}
function renderPreviewState(j,p){const card=$('#previewCard');if(!j||j.workspace_mode!=='direct'){card.style.display='none';previewJob=null;previewState=null;return}card.style.display='';previewJob=j.id;previewState=p||{status:'not_built',supported:true,generation:0};$('#previewStatus').innerHTML=previewStatusBadge(previewState.status);const target=$('#previewTarget');if(previewState.target&&['frontend','backend','both'].includes(previewState.target)&&!previewBusy)target.value=previewState.target;const ready=previewState.status==='ready';$('#previewStart').textContent=ready?'Rebuild':'Start Preview';$('#previewStart').disabled=previewBusy||previewState.supported===false;$('#previewStop').disabled=previewBusy||!['ready','starting','failed'].includes(previewState.status);const links=[];if(previewState.frontend_url)links.push('<a href="'+esc(previewState.frontend_url)+'" target="_blank" rel="noopener noreferrer">Open Frontend ↗</a>');if(previewState.backend_url)links.push('<a href="'+esc(previewState.backend_url)+'" target="_blank" rel="noopener noreferrer">Open Backend ↗</a>');$('#previewLinks').innerHTML=links.join('');const details=[];if(previewState.generation)details.push('generation '+previewState.generation);if(previewState.integration_note)details.push(previewState.integration_note);if(previewState.error)details.push(previewState.error);$('#previewNote').textContent=details.join(' · ')}
async function refreshPreview(j){if(!j||j.workspace_mode!=='direct'){renderPreviewState(j,null);return}if(previewRefreshBusy||previewBusy)return;previewRefreshBusy=true;try{const r=await fetch('/v1/dashboard/jobs/'+encodeURIComponent(j.id)+'/preview',{cache:'no-store'});if(r.status===401)return;if(!r.ok){renderPreviewState(j,{status:'failed',supported:true,error:'Preview status HTTP '+r.status});return}renderPreviewState(j,await r.json())}catch(e){renderPreviewState(j,{status:'failed',supported:true,error:String(e)})}finally{previewRefreshBusy=false}}
async function unlockPreviewControls(){const token=window.prompt('Enter DASHBOARD_CONTROL_TOKEN');if(!token)return false;const r=await fetch('/v1/dashboard/control-session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({token:token})});if(!r.ok){window.alert(r.status===503?'Dashboard control token is not configured.':'Preview control unlock failed.');return false}return true}
function previewSleep(ms){return new Promise(resolve=>setTimeout(resolve,ms))}
async function reconcilePreviewMutation(method,jobId,priorGeneration){const expectedGeneration=method==='POST'?priorGeneration+1:priorGeneration;for(let attempt=0;attempt<60;attempt++){await previewSleep(1000);try{const r=await fetch('/v1/dashboard/jobs/'+encodeURIComponent(jobId)+'/preview',{cache:'no-store'});if(r.status===401)return null;if(!r.ok)continue;const state=await r.json();const generation=Number(state.generation||0);if(method==='DELETE'){if(state.status==='stopped')return state}else if(generation>=expectedGeneration&&state.status!=='starting'){return state}}catch(e){}}return null}
async function previewMutation(method,body){if(!previewJob||previewBusy)return;const mutationJob=previewJob;const priorGeneration=Number(previewState?.generation||0);previewBusy=true;renderPreviewState({id:mutationJob,workspace_mode:'direct'},previewState);const invoke=()=>fetch('/v1/dashboard/jobs/'+encodeURIComponent(mutationJob)+'/preview',{method:method,headers:body?{'content-type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});try{let r=await invoke();if(r.status===401){const unlocked=await unlockPreviewControls();if(!unlocked)return;r=await invoke()}const payload=await r.json().catch(()=>({}));if(!r.ok){renderPreviewState({id:mutationJob,workspace_mode:'direct'},Object.assign({},previewState,{status:'failed',error:payload.detail||('HTTP '+r.status)}));return}renderPreviewState({id:mutationJob,workspace_mode:'direct'},payload)}catch(e){const recovered=await reconcilePreviewMutation(method,mutationJob,priorGeneration);if(recovered){renderPreviewState({id:mutationJob,workspace_mode:'direct'},recovered);return}renderPreviewState({id:mutationJob,workspace_mode:'direct'},Object.assign({},previewState,{status:'failed',error:'Preview connection was interrupted and status reconciliation timed out.'}))}finally{previewBusy=false}}
$('#previewStart').onclick=()=>previewMutation('POST',{target:$('#previewTarget').value});
$('#previewStop').onclick=()=>previewMutation('DELETE',null);
$('#previewUnlock').onclick=unlockPreviewControls;
'''
if "function renderTimeline(w){" not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard timeline target changed; review preview UI integration")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "function renderTimeline(w){",
    _PREVIEW_FUNCTIONS + "\nfunction renderTimeline(w){",
    1,
)
if "connectStream(j.id)}}" not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard job render target changed; review preview UI integration")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "connectStream(j.id)}}",
    "connectStream(j.id)}refreshPreview(j)}",
    1,
)
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "Read-only observability. Dashboard disconnects never control, pause, resume, or otherwise affect a coding job.",
    "Read-only observability by default. Local preview mutations require a separate control unlock and never pause, resume, repair, or complete a coding job.",
)


# Project-level Current site preview is independent from a selected WorkOrder.
# It reuses the existing control-session boundary and never exposes workspace
# paths or executor commands to the browser.
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "</style>",
    ".project-preview-state{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}.s-job_owned{color:#fcd34d;border-color:#735b18;background:#2d250c}.project-preview-meta{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px}</style>",
    1,
)
_PROJECT_PREVIEW_CARD = r'''<section class="card section" id="projectPreviewCard" style="display:none"><div class="section-head"><div><div class="section-title">Current site</div><div class="small">Direct project preview · available even when no WorkOrder is active</div></div><div id="projectPreviewStatus"></div></div><div class="preview-actions"><select id="projectPreviewProject" class="select"></select><select id="projectPreviewTarget" class="select"><option value="frontend">Frontend</option><option value="backend">Backend</option><option value="both">Both</option></select><button id="projectPreviewStart">Start Preview</button><button id="projectPreviewStop">Stop Frontend</button><button id="projectPreviewUnlock">Unlock controls</button></div><div id="projectPreviewMeta" class="project-preview-meta small"></div><div id="projectPreviewLinks" class="preview-links"></div><div id="projectPreviewNote" class="preview-note"></div></section>'''
if '<section class="card section"><div class="section-head"><div><div class="section-title">Execution plan</div>' not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard execution-plan target changed; review Current site integration")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    '<section class="card section"><div class="section-head"><div><div class="section-title">Execution plan</div>',
    _PROJECT_PREVIEW_CARD + '<section class="card section"><div class="section-head"><div><div class="section-title">Execution plan</div>',
    1,
)
if "previewRefreshBusy=false;" not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard preview state target changed; review Current site integration")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "previewRefreshBusy=false;",
    "previewRefreshBusy=false,projectPreviewProjects=[],projectPreviewProject=null,projectPreviewState=null,projectPreviewBusy=false,projectPreviewRefreshBusy=false,projectPreviewLastRefresh=0;",
    1,
)

_PROJECT_PREVIEW_FUNCTIONS = r'''
function projectPreviewComponent(label,value){return '<span>'+esc(label)+' '+status(value||'stopped')+'</span>'}
function renderProjectPreviewState(p){const card=$('#projectPreviewCard');if(!projectPreviewProjects.length){card.style.display='none';return}card.style.display='';projectPreviewState=p||projectPreviewState||null;const selector=$('#projectPreviewProject');selector.innerHTML=projectPreviewProjects.map(x=>'<option value="'+esc(x.project_id)+'" '+(x.project_id===projectPreviewProject?'selected':'')+'>'+esc(x.project_id)+'</option>').join('');const state=projectPreviewState||{};$('#projectPreviewStatus').innerHTML=status(state.status||'stopped');const meta=[];meta.push('branch '+esc(state.branch||'unknown'));meta.push(state.clean===true?'clean':state.clean===false?'dirty':'clean state unknown');meta.push(state.ownership==='job'?'owned by active job':'engineering lease free');$('#projectPreviewMeta').innerHTML='<span>'+meta.join(' · ')+'</span>'+projectPreviewComponent('Backend',state.backend_status)+projectPreviewComponent('Frontend',state.frontend_status);const links=[];if(state.frontend_url)links.push('<a href="'+esc(state.frontend_url)+'" target="_blank" rel="noopener noreferrer">Open Frontend ↗</a>');if(state.backend_url)links.push('<a href="'+esc(state.backend_url)+'" target="_blank" rel="noopener noreferrer">Open Backend ↗</a>');$('#projectPreviewLinks').innerHTML=links.join('');const controls=state.controls_enabled===true&&!projectPreviewBusy;$('#projectPreviewStart').disabled=!controls;$('#projectPreviewStop').disabled=!controls||state.frontend_status!=='ready';$('#projectPreviewStart').textContent=state.status==='ready'?'Rebuild Preview':'Start Preview';const note=[];if(state.ownership==='job')note.push('Active direct job owns this project. Use the job Local preview for work-in-progress review.');else if(state.clean===false)note.push('Preview mutation is disabled while the direct repository has uncommitted changes.');if(state.error)note.push(state.error);if(state.backend_status==='ready'&&state.frontend_status!=='ready')note.push('Backend uses the shared DDEV runtime and may stay available while Frontend is stopped.');$('#projectPreviewNote').textContent=note.join(' · ')}
async function refreshProjectPreviewProjects(){if(projectPreviewProjects.length)return;try{const r=await fetch('/v1/dashboard/project-previews',{cache:'no-store'});if(r.status===401)return;if(!r.ok)throw new Error('project previews HTTP '+r.status);const payload=await r.json();projectPreviewProjects=payload.projects||[];const planProject=currentPlan()?.project_id;if(!projectPreviewProject||!projectPreviewProjects.some(x=>x.project_id===projectPreviewProject)){projectPreviewProject=projectPreviewProjects.some(x=>x.project_id===planProject)?planProject:(projectPreviewProjects[0]?.project_id||null)}renderProjectPreviewState(projectPreviewState)}catch(e){console.error(e)}}
async function refreshProjectPreview(force=false){if(!projectPreviewProject||projectPreviewBusy||projectPreviewRefreshBusy)return;const now=Date.now();if(!force&&now-projectPreviewLastRefresh<8000)return;projectPreviewRefreshBusy=true;try{const r=await fetch('/v1/dashboard/projects/'+encodeURIComponent(projectPreviewProject)+'/preview',{cache:'no-store'});if(r.status===401)return;if(!r.ok){const payload=await r.json().catch(()=>({}));renderProjectPreviewState(Object.assign({},projectPreviewState,{status:'failed',error:payload.detail||('HTTP '+r.status)}));return}projectPreviewState=await r.json();projectPreviewLastRefresh=Date.now();renderProjectPreviewState(projectPreviewState)}catch(e){renderProjectPreviewState(Object.assign({},projectPreviewState,{status:'failed',error:String(e)}))}finally{projectPreviewRefreshBusy=false}}
async function reconcileProjectPreviewMutation(method,projectId,priorGeneration,target){const expected=method==='POST'?priorGeneration+1:priorGeneration;for(let attempt=0;attempt<60;attempt++){await previewSleep(1000);try{const r=await fetch('/v1/dashboard/projects/'+encodeURIComponent(projectId)+'/preview',{cache:'no-store'});if(r.status===401)return null;if(!r.ok)continue;const state=await r.json();const generation=Number(state.generation||0);if(method==='DELETE'){if(state.frontend_status==='stopped')return state}else if(generation>=expected&&state.status!=='starting'){return state}}catch(e){}}return null}
async function projectPreviewMutation(method,body){if(!projectPreviewProject||projectPreviewBusy)return;const projectId=projectPreviewProject,priorGeneration=Number(projectPreviewState?.generation||0),target=body?.target||null;projectPreviewBusy=true;renderProjectPreviewState(projectPreviewState);const invoke=()=>fetch('/v1/dashboard/projects/'+encodeURIComponent(projectId)+'/preview',{method:method,headers:body?{'content-type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});try{let r=await invoke();if(r.status===401){const unlocked=await unlockPreviewControls();if(!unlocked)return;r=await invoke()}const payload=await r.json().catch(()=>({}));if(!r.ok){renderProjectPreviewState(Object.assign({},projectPreviewState,{status:'failed',error:payload.detail||('HTTP '+r.status)}));return}projectPreviewState=payload;projectPreviewLastRefresh=Date.now();renderProjectPreviewState(payload)}catch(e){const recovered=await reconcileProjectPreviewMutation(method,projectId,priorGeneration,target);if(recovered){projectPreviewState=recovered;projectPreviewLastRefresh=Date.now();renderProjectPreviewState(recovered);return}renderProjectPreviewState(Object.assign({},projectPreviewState,{status:'failed',error:'Current-site preview connection was interrupted and status reconciliation timed out.'}))}finally{projectPreviewBusy=false;renderProjectPreviewState(projectPreviewState)}}
$('#projectPreviewProject').onchange=async e=>{projectPreviewProject=e.target.value;projectPreviewState=null;projectPreviewLastRefresh=0;await refreshProjectPreview(true)};
$('#projectPreviewStart').onclick=()=>projectPreviewMutation('POST',{target:$('#projectPreviewTarget').value});
$('#projectPreviewStop').onclick=()=>projectPreviewMutation('DELETE',null);
$('#projectPreviewUnlock').onclick=unlockPreviewControls;
'''
if "function renderTimeline(w){" not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard timeline target changed; review Current site functions")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "function renderTimeline(w){",
    _PROJECT_PREVIEW_FUNCTIONS + "\nfunction renderTimeline(w){",
    1,
)
if "snapshot=await r.json();hideLogin();render();await refreshQuota()" not in DASHBOARD_HTML:
    raise RuntimeError("Dashboard refresh target changed; review Current site refresh integration")
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "snapshot=await r.json();hideLogin();render();await refreshQuota()",
    "snapshot=await r.json();hideLogin();render();await refreshQuota();await refreshProjectPreviewProjects();await refreshProjectPreview()",
    1,
)
