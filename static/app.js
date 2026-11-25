const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sign = (n) => (n > 0 ? "+" : n < 0 ? "−" : "") + Math.abs(n);
const SEV = { positive: "✓", neutral: "•", warning: "!", critical: "✕" };
const OUTCOME = { APPROVE: ["✓", "Approve"], REFER: ["!", "Refer to human"], DECLINE: ["✕", "Decline"] };
const RISK_AGENTS = ["kyc", "credit", "fraud", "compliance"];

let samples = [], graph = null, current = null, results = {}, showTable = false;

async function init() {
  [samples, graph] = await Promise.all([fetch("/api/samples").then((r) => r.json()), fetch("/api/graph").then((r) => r.json())]);
  const box = $("samples");
  samples.forEach((s) => {
    const b = document.createElement("button");
    b.className = "sample"; b.dataset.id = s.id; b.setAttribute("aria-pressed", "false");
    b.innerHTML = `<b>${esc(s.title)}</b><span>${esc(s.blurb)}</span>`;
    b.onclick = () => select(s.id);
    box.appendChild(b);
  });
  select(samples[0].id);
  buildPipeline();
}

function select(id) {
  const s = samples.find((x) => x.id === id);
  current = { ...s.application };
  document.querySelectorAll(".sample").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
  renderFields();
}

function renderFields() {
  const f = $("fields"); f.innerHTML = "";
  Object.entries(current).forEach(([k, v]) => {
    const wrap = document.createElement("div");
    const label = k.replace(/_/g, " ");
    if (typeof v === "boolean") {
      wrap.className = "field check";
      wrap.innerHTML = `<input type="checkbox" id="f_${k}" ${v ? "checked" : ""}><label for="f_${k}">${esc(label)}</label>`;
      wrap.querySelector("input").onchange = (e) => (current[k] = e.target.checked);
    } else {
      wrap.className = "field";
      const type = typeof v === "number" ? "number" : "text";
      wrap.innerHTML = `<label for="f_${k}">${esc(label)}</label><input type="${type}" id="f_${k}" step="any" value="${esc(v)}">`;
      wrap.querySelector("input").oninput = (e) => (current[k] = type === "number" ? e.target.valueAsNumber : e.target.value);
    }
    f.appendChild(wrap);
  });
}

function buildPipeline() {
  const p = $("pipeline"); p.innerHTML = "";
  const byId = Object.fromEntries(graph.agents.map((a) => [a.id, a]));
  const names = ["Stage 1 · Verify", "Stage 2 · Assess in parallel", "Stage 3 · Decide"];
  graph.stages.forEach((stage, i) => {
    const col = document.createElement("div"); col.className = "col";
    col.innerHTML = `<div class="col-label">${names[i]}</div>`;
    stage.forEach((id) => {
      const a = byId[id], el = document.createElement("div");
      el.className = "agent"; el.id = "agent_" + id; el.dataset.state = "idle";
      el.innerHTML = `<div class="agent-head"><div><b>${esc(a.name)}</b><div class="role">${esc(a.role)}</div></div><div class="status" id="st_${id}">Waiting</div></div><div id="body_${id}"></div>`;
      col.appendChild(el);
    });
    p.appendChild(col);
  });
}

function resetRun() {
  results = {}; buildPipeline();
  ["results", "contrib", "abl"].forEach((id) => ($(id).hidden = true));
  $("err").hidden = true;
}

function agentStart(id) {
  $("agent_" + id).dataset.state = "running";
  $("st_" + id).innerHTML = '<span class="spin"></span>Working';
}

function agentDone(id, r) {
  results[id] = r;
  $("agent_" + id).dataset.state = "done";
  const delta = RISK_AGENTS.includes(id)
    ? `<span class="chip ${r.risk_delta < 0 ? "lower" : r.risk_delta > 0 ? "raise" : ""}">${sign(r.risk_delta)} risk</span>`
    : `<span class="chip">decision</span>`;
  $("st_" + id).innerHTML = delta;
  const items = r.findings.map((f) => `<li><span class="sev ${f.severity}" aria-hidden="true">${SEV[f.severity]}</span><span>${esc(f.label)}</span>${RISK_AGENTS.includes(id) ? `<span class="d">${sign(f.delta)}</span>` : ""}</li>`).join("");
  const stop = r.hard_stop ? `<div class="summary" style="color:var(--crit);font-weight:600">Hard stop: ${esc(r.hard_stop.reason)}</div>` : "";
  $("body_" + id).innerHTML = `<div class="summary">${esc(r.summary)}</div>${stop}<div class="conf">Confidence ${Math.round(r.confidence * 100)}% · ${r.compute_ms} ms</div><ul>${items}</ul>`;
  if (RISK_AGENTS.includes(id)) { $("contrib").hidden = false; renderChart(); }
}

function tipHtml(r) {
  const top = [...r.findings].filter((f) => f.delta !== 0).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 3);
  return `<b>${esc(r.name)}: ${sign(r.risk_delta)} points</b>${top.map((f) => `${esc(f.label)} (${sign(f.delta)})`).join("<br>")}`;
}

function renderChart() {
  const rows = RISK_AGENTS.filter((a) => results[a]).map((a) => results[a]);
  const max = Math.max(20, Math.ceil(Math.max(...rows.map((r) => Math.abs(r.risk_delta))) / 10) * 10);
  $("chart").innerHTML = '<div class="axis-note"><span>← lowers risk</span><span>raises risk →</span></div>' + rows.map((r) => {
    const w = (Math.abs(r.risk_delta) / max) * 50, cls = r.risk_delta < 0 ? "lower" : "raise";
    const pos = r.risk_delta < 0 ? `right:calc(50% + ${w}% + 6px)` : `left:calc(50% + ${w}% + 6px)`;
    const bar = r.risk_delta === 0 ? "" : `<div class="bar ${cls}" style="width:${w}%" tabindex="0" data-agent="${r.agent_id}" aria-label="${esc(r.name)} ${sign(r.risk_delta)} risk points"></div>`;
    return `<div class="chart-row"><div>${esc(r.name)}</div><div class="plot">${bar}<span class="val" style="${pos}">${sign(r.risk_delta)}</span></div></div>`;
  }).join("");
  $("chartTable").innerHTML = `<table><tr><th>Agent</th><th class="num">Risk points</th><th class="num">Confidence</th></tr>${rows.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${sign(r.risk_delta)}</td><td class="num">${Math.round(r.confidence * 100)}%</td></tr>`).join("")}</table>`;
  document.querySelectorAll(".bar").forEach((b) => {
    const r = results[b.dataset.agent];
    const show = (e) => { const t = $("tip"); t.innerHTML = tipHtml(r); t.style.display = "block"; const rc = b.getBoundingClientRect(); t.style.left = Math.min(innerWidth - 310, (e.clientX || rc.left) + 12) + "px"; t.style.top = (e.clientY || rc.bottom) + 12 + "px"; };
    b.onmousemove = show; b.onfocus = show; b.onmouseleave = b.onblur = () => ($("tip").style.display = "none");
  });
}

function complete(ev) {
  const u = results.underwriter, m = u.metrics, d = m.decision;
  $("results").hidden = false; $("abl").hidden = false;
  const [icon, label] = OUTCOME[d.outcome];
  $("badge").className = "badge " + d.outcome;
  $("badge").innerHTML = `<i aria-hidden="true">${icon}</i>${label}`;
  $("score").textContent = d.score;
  $("pin").style.left = d.score + "%";
  $("meter").setAttribute("aria-label", `Risk score ${d.score} of 100, outcome ${label}`);
  const stops = d.hard_stops.length ? ` Hard stop: ${d.hard_stops.map(esc).join("; ")}.` : "";
  $("memo").textContent = m.memo;
  $("memotag").textContent = (u.used_llm ? "Memo written by Claude from the agents' findings." : "Rule-based memo." + (m.llm_error ? ` Claude call failed (${m.llm_error}); the decision is unaffected.` : " Add an API key for a Claude-written memo.")) + " The decision itself always comes from the deterministic policy." + (d.hard_stops.length ? stops : "");
  $("offer").textContent = m.offer ? `Offer: $${m.offer.amount.toLocaleString()} over ${m.offer.term_months} months at ${m.offer.apr}% APR, about $${m.offer.monthly_payment.toLocaleString()} per month.` : "";

  const all = graph.agents.map((a) => results[a.id]).filter(Boolean);
  $("value").innerHTML = `<tr><th>Agent</th><th class="num">Compute</th><th class="num">Est. analyst</th></tr>` +
    all.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${r.compute_ms} ms</td><td class="num">${r.manual_minutes} min</td></tr>`).join("") +
    `<tr><td><b>Total</b></td><td class="num"><b>${ev.compute_ms_total} ms</b></td><td class="num"><b>${ev.manual_minutes_total} min</b></td></tr>`;

  $("ablation").innerHTML = `<tr><th>Agent removed</th><th class="num">Score without</th><th>Decision without</th><th>Verdict</th></tr>` +
    m.ablation.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${r.score_without}</td><td>${OUTCOME[r.outcome_without][1]}</td><td>${r.flips ? `<span class="pill yes">✕ Decisive: outcome changes</span>` : `<span class="pill no">• Not decisive</span>`}</td></tr>`).join("");
}

$("toggle").onclick = () => {
  showTable = !showTable;
  $("chart").hidden = showTable; $("chartTable").hidden = !showTable;
  $("toggle").textContent = showTable ? "Show as chart" : "Show as table";
};

async function httpError(res) {
  if (res.status === 422) {
    try {
      const first = (await res.json()).detail[0];
      return `Check "${first.field.replace(/_/g, " ")}": ${first.message}.`;
    } catch { return "Some application fields are invalid."; }
  }
  if (res.status === 429) return `Too many requests. Try again in ${res.headers.get("Retry-After") || "a few"} seconds.`;
  if (res.status === 503) return "The server is busy. Please try again shortly.";
  if (res.status === 413) return "The request was too large.";
  return `Request failed (${res.status}).`;
}

$("run").onclick = async () => {
  resetRun();
  const btn = $("run"); btn.disabled = true; btn.textContent = "Agents working...";
  let finished = false;
  try {
    const res = await fetch("/api/underwrite/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application: current, api_key: $("key").value.trim() || null }),
    });
    if (!res.ok) throw new Error(await httpError(res));
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2);
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5));
        if (ev.type === "agent_start") agentStart(ev.agent);
        else if (ev.type === "agent_done") agentDone(ev.agent, ev.result);
        else if (ev.type === "complete") { finished = true; complete(ev); }
        else if (ev.type === "error") throw new Error(ev.message);
      }
    }
    if (!finished) throw new Error("The connection closed before the analysis finished. Please try again.");
  } catch (e) {
    $("err").textContent = e instanceof TypeError ? "Could not reach the server. Check your connection and try again." : e.message;
    $("err").hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Run underwriting agents";
  }
};

init().catch(() => {
  $("err").textContent = "Could not load the app data. Please reload the page.";
  $("err").hidden = false;
});
