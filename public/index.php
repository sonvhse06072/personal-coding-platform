<!doctype html>
<html><head><meta charset="utf-8"><title>Personal Coding Platform</title>
<style>body{font-family:system-ui;max-width:900px;margin:60px auto;padding:0 24px;line-height:1.5}code{background:#eee;padding:2px 6px;border-radius:4px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{border:1px solid #ddd;border-radius:10px;padding:16px}</style></head>
<body><h1>Personal Coding Platform v1</h1><p>DDEV is the supervisor. Core services start together with <code>ddev start</code>.</p>
<div class="cards"><div class="card"><h3>n8n</h3><p>Control plane / event orchestration.</p><a href="https://<?= htmlspecialchars($_SERVER['HTTP_HOST']) ?>:5679">Open n8n</a></div>
<div class="card"><h3>Router</h3><p>Complexity, policy, budget and model routing.</p><a href="https://<?= htmlspecialchars($_SERVER['HTTP_HOST']) ?>:8091/docs">Open API docs</a></div>
<div class="card"><h3>Coding Runtime</h3><p>Worktrees, agents, verification and anti-loop execution.</p><a href="https://<?= htmlspecialchars($_SERVER['HTTP_HOST']) ?>:8788/docs">Open API docs</a></div></div>
<h2>Useful commands</h2><pre>ddev start
ddev platform-status
ddev platform-test
ddev logs -s coding-runtime</pre></body></html>
