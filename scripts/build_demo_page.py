"""Render public/index.html — a static, interactive capture of the dashboard.

The real dashboard is two long-running processes (FastAPI + Streamlit) over an
in-memory request log, which static hosting cannot run. This page embeds real
responses captured from the running service (demo/*.json: /analytics/summary
and /analytics/timeseries at three intervals, for a healthy week and a
degraded one) and re-implements the page's rendering rules in the browser —
same KPI formatting, same alert thresholds, same null handling.

    python scripts/build_demo_page.py                    # writes public/index.html
    python scripts/build_demo_page.py ../rankshift/public/serving/analytics/index.html
                                                         # also mirrored on the RankShift site
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "public" / "index.html"

data = {}
for scenario in ("healthy", "degraded"):
    data[scenario] = {
        "summary": json.loads((DEMO / f"{scenario}-summary.json").read_text()),
        "series": {iv: json.loads((DEMO / f"{scenario}-{iv}.json").read_text())
                   for iv in ("1h", "6h", "1d")},
    }
captured = max(data[s]["summary"]["last_updated"] for s in data)[:10]
payload = json.dumps(data, separators=(",", ":"))

HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RankShift Serving · Analytics Dashboard</title>
<meta name="description" content="Request analytics for the RankShift Serving prediction API — traffic, latency, error rate and model-output drift, captured from the running service.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='13' font-size='13'>📈</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
:root{--ground:#EAEEF2;--surface:#FBFCFD;--surface-2:#DFE5EB;--ink:#101820;--muted:#55636E;--faint:#8494A0;--line:#C9D3DC;--blue:#16688A;--blue-soft:rgba(22,104,138,.13);--alarm:#A03626;--alarm-soft:rgba(160,54,38,.11);--ok:#2F6B4F;--ok-soft:rgba(47,107,79,.12);--warn:#8A6A12;--warn-soft:rgba(178,138,22,.14);--shadow:0 1px 2px rgba(16,24,32,.06),0 10px 30px -20px rgba(16,24,32,.4);--display:"Fraunces",Georgia,serif;--body:"Source Sans 3",system-ui,sans-serif;--data:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0E1419;--surface:#161D24;--surface-2:#1D262E;--ink:#E4EAEF;--muted:#93A2AD;--faint:#6B7A85;--line:#26313A;--blue:#57B4D4;--blue-soft:rgba(87,180,212,.15);--alarm:#E07A6A;--alarm-soft:rgba(224,122,106,.14);--ok:#6FBF95;--ok-soft:rgba(111,191,149,.14);--warn:#E0B454;--warn-soft:rgba(224,180,84,.14)}}
*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.55}
.wrap{max-width:1040px;margin:0 auto;padding:40px 24px 80px}
header{margin-bottom:28px}.eyebrow{font-family:var(--data);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:12px}
h1{font-family:var(--display);font-weight:600;font-size:clamp(32px,5vw,50px);line-height:1.05;letter-spacing:-.02em;margin:0 0 12px}
.thesis{font-size:19px;color:var(--muted);max-width:68ch;margin:0}
h2{font-family:var(--display);font-weight:600;font-size:24px;margin:36px 0 10px}
.snap{border-left:3px solid var(--blue);background:var(--blue-soft);padding:14px 18px;border-radius:0 7px 7px 0;font-size:15px;margin:22px 0}
.snap code{font-family:var(--data);font-size:.86em;background:var(--surface-2);padding:2px 5px;border-radius:3px}
.controls{display:flex;flex-wrap:wrap;gap:22px 34px;align-items:flex-end;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px 20px;box-shadow:var(--shadow);margin:18px 0}
.controls .grp{display:flex;flex-direction:column;gap:7px}.controls .lbl{font-size:13px;color:var(--muted)}
.seg{display:flex;gap:6px}.seg label{cursor:pointer;font-family:var(--data);font-size:12px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:7px 12px}
.seg input{display:none}.seg label:has(input:checked){background:var(--blue-soft);border-color:var(--blue);color:var(--ink)}
.controls label.sl{font-size:13px;color:var(--muted);min-width:190px}.controls label.sl output{float:right;font-family:var(--data);font-weight:600;color:var(--ink)}
.controls input[type=range]{width:100%;margin-top:4px;accent-color:var(--blue)}
.status{font-size:14px;color:var(--muted);margin:14px 0 6px}.status b{color:var(--ink)}.status code{font-family:var(--data);font-size:.86em}
.banner{border-left:3px solid var(--warn);background:var(--warn-soft);padding:12px 16px;border-radius:0 7px 7px 0;font-size:15px;margin:10px 0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px;box-shadow:var(--shadow)}
.kpi .l{font-size:13px;color:var(--muted)}.kpi .v{font-family:var(--data);font-size:30px;font-weight:600;margin:6px 0 4px;font-variant-numeric:tabular-nums}
.kpi .d{font-family:var(--data);font-size:13px;font-weight:600;display:inline-block;padding:2px 8px;border-radius:999px}
.kpi .d.up{color:var(--ok);background:var(--ok-soft)}.kpi .d.down{color:var(--alarm);background:var(--alarm-soft)}.kpi .d.none{color:var(--faint)}
.alerts{display:grid;gap:8px;margin:6px 0 14px}.alert{border-left:3px solid var(--warn);background:var(--warn-soft);padding:11px 16px;border-radius:0 7px 7px 0;font-size:15px}
.alert.none{border-color:var(--ok);background:var(--ok-soft);color:var(--muted)}
.charts{display:grid;gap:18px}.chart{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px 8px;box-shadow:var(--shadow)}
.chart h3{font-family:var(--body);font-size:15px;font-weight:600;margin:0 0 6px}.chart svg{width:100%;height:220px;display:block}
.chart .grid{stroke:var(--line);stroke-width:1}.chart .ax{font-family:var(--data);font-size:11px;fill:var(--faint)}.chart .ln{fill:none;stroke:var(--blue);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.chart .pt{fill:var(--blue)}
details{background:var(--surface);border:1px solid var(--line);border-radius:10px;margin:22px 0;box-shadow:var(--shadow)}summary{cursor:pointer;padding:14px 18px;font-weight:600}
.tbl{max-height:420px;overflow:auto;border-top:1px solid var(--line)}table{border-collapse:collapse;width:100%;font-size:13px;font-family:var(--data)}
th,td{padding:8px 14px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}th{position:sticky;top:0;background:var(--surface);color:var(--muted);font-weight:600}th:first-child,td:first-child{text-align:left}
.how{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:20px 22px;box-shadow:var(--shadow)}.how p{margin:8px 0;color:var(--muted);font-size:15px}.how code{font-family:var(--data);font-size:.86em;background:var(--surface-2);padding:2px 5px;border-radius:3px}
pre{font-family:var(--data);font-size:13px;background:var(--surface-2);padding:14px 16px;border-radius:7px;overflow:auto;line-height:1.5}
footer{margin-top:44px;font-size:14px;color:var(--muted);border-top:1px solid var(--line);padding-top:18px}a{color:var(--blue)}
@media (max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body><div class="wrap">
<header>
  <div class="eyebrow"><a href="/serving/" style="color:inherit;text-decoration:none">RankShift Serving · plain-language tour</a> · station 04 · request analytics · captured __CAPTURED__</div>
  <h1>📈 Analytics Dashboard</h1>
  <p class="thesis">Is the service being called, is it slowing down, are errors rising, and has the model's output distribution moved? Four numbers and four charts, derived from a request log the service writes about itself.</p>
</header>

<div class="snap">This is a <strong>static capture</strong> of the running dashboard, not the live service. The live version is two long-running processes — a FastAPI API that logs every request it serves into an in-memory ring buffer, and a Streamlit page that reads two aggregation endpoints — which static hosting cannot run. The responses below were captured verbatim from <code>/analytics/summary</code> and <code>/analytics/timeseries</code>; the rendering rules (formats, thresholds, null handling) are the page's own, re-implemented here. <a href="https://github.com/PSCRedefine/AnalyticsDashboard#quick-start">Run it live in two commands.</a></div>

<div class="controls">
  <div class="grp"><span class="lbl">Scenario</span><div class="seg">
    <label><input type="radio" name="sc" value="healthy" checked>healthy week</label>
    <label><input type="radio" name="sc" value="degraded">degraded week</label></div></div>
  <div class="grp"><span class="lbl">Interval</span><div class="seg">
    <label><input type="radio" name="iv" value="1h" checked>1h</label>
    <label><input type="radio" name="iv" value="6h">6h</label>
    <label><input type="radio" name="iv" value="1d">1d</label></div></div>
  <label class="sl">Error-rate alert above <output id="o-err">2.00%</output><input type="range" id="t-err" min="0.5" max="10" step="0.1" value="2"></label>
  <label class="sl">Latency alert above <output id="o-lat">300 ms</output><input type="range" id="t-lat" min="50" max="600" step="10" value="300"></label>
  <label class="sl">Probability drift alert at <output id="o-drift">±0.100</output><input type="range" id="t-drift" min="0.02" max="0.3" step="0.01" value="0.1"></label>
</div>

<p class="status" id="status"></p>
<div class="banner" id="synthetic" hidden></div>
<div class="kpis" id="kpis"></div>
<div class="alerts" id="alerts"></div>
<div class="charts" id="charts"></div>
<details><summary>Raw Data</summary><div class="tbl" id="raw"></div></details>

<h2>How the numbers get there</h2>
<div class="how">
<pre>client ──POST /predict──→ middleware: start clock → route scores, writes probability
                                       and model_version to request.state
                        → middleware: stop clock, append one entry (in `finally`)
                                       ↓
                              deque(maxlen=200_000)  ← the only data source
                                       ↓
              GET /analytics/summary        GET /analytics/timeseries
              this window · previous · Δ   one row per bucket, gaps kept</pre>
<p><strong>Nothing is not zero.</strong> An empty window has no average response time; the API returns <code>null</code> and the page renders <code>-</code>. Empty buckets keep their place with <code>requests: 0</code> so an outage stays visible instead of being joined across. Failed requests never reached the model, so they don't drag the probability average down.</p>
<p><strong>Honest about the source.</strong> <code>in_memory_api_logs</code> means every entry came from a request the service served. <code>in_memory_api_logs+synthetic_backfill</code> means at least one entry was injected by the demonstration backfill tool — and the page says so in a banner. Both captures here contain backfilled history, because a seven-day chart needs seven days.</p>
<p><strong>Alerts are window averages</strong>, as specified — which has a blind spot: a single bad day inside a healthy week averages out under both thresholds while being obvious in the charts. Move the sliders above and watch which alerts fire on the degraded week.</p>
</div>

<footer>
  <p>Source, tests (101) and the spec: <a href="https://github.com/PSCRedefine/AnalyticsDashboard">PSCRedefine/AnalyticsDashboard</a> · part of <a href="https://github.com/PSCRedefine">RankShift Serving</a> · research: <a href="https://github.com/PSCRedefine/rankshift">RankShift</a>. Regenerate this page with <code>python scripts/build_demo_page.py</code> from <code>demo/*.json</code>.</p>
</footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  const DATA = JSON.parse(document.getElementById("data").textContent);
  const $ = id => document.getElementById(id);
  const q = n => document.querySelector('input[name='+n+']:checked').value;
  const fmt = (v, d, suf="") => v == null ? "-" : v.toFixed(d) + suf;
  const delta = (v, d, suf, inverse) => {
    if (v == null) return '<span class="d none">no previous window</span>';
    const good = inverse ? v <= 0 : v >= 0;
    return '<span class="d ' + (good ? "up" : "down") + '">' + (v > 0 ? "↑ +" : v < 0 ? "↓ " : "") + v.toFixed(d) + suf + '</span>';
  };
  const tfmt = iso => { const d = new Date(iso); return d.toLocaleString("en-US", {month:"short", day:"2-digit", hour:"2-digit", minute:"2-digit", hour12:false, timeZone:"UTC"}); };

  function chart(title, rows, key, yTitle, scale=1, range=null){
    const W=900, H=220, L=54, R=14, T=14, B=34;
    const vals = rows.map(r => r[key] == null ? null : r[key]*scale);
    const present = vals.filter(v => v != null);
    let lo = range ? range[0] : Math.min(...present), hi = range ? range[1] : Math.max(...present);
    if (!range) { const pad = (hi - lo || 1) * 0.12; lo = Math.max(0, lo - pad); hi = hi + pad; }
    const x = i => L + (W-L-R) * (rows.length === 1 ? 0.5 : i/(rows.length-1));
    const y = v => T + (H-T-B) * (1 - (v-lo)/(hi-lo || 1));
    let path = "", pts = "", seg = [];
    vals.forEach((v,i) => { if (v == null) { seg = []; return; } seg.push(i); path += (seg.length===1 ? "M" : "L") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; if (rows.length <= 60) pts += '<circle class="pt" cx="'+x(i).toFixed(1)+'" cy="'+y(v).toFixed(1)+'" r="3"/>'; });
    let grid = "";
    [0, .5, 1].forEach(f => { const v = lo + (hi-lo)*f, yy = y(v); grid += '<line class="grid" x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+'"/><text class="ax" x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end">'+(hi >= 100 ? v.toFixed(0) : hi >= 5 ? v.toFixed(1) : v.toFixed(2))+'</text>'; });
    const ticks = Math.min(6, rows.length);
    for (let k = 0; k < ticks; k++) { const i = Math.round(k*(rows.length-1)/Math.max(1,ticks-1)); grid += '<text class="ax" x="'+x(i)+'" y="'+(H-10)+'" text-anchor="middle">'+tfmt(rows[i].timestamp)+'</text>'; }
    return '<div class="chart"><h3>'+title+'</h3><svg viewBox="0 0 '+W+' '+H+'">'+grid+'<path class="ln" d="'+path+'"/>'+pts+'<text class="ax" transform="translate(12 '+((T+H-B)/2)+') rotate(-90)" text-anchor="middle">'+yTitle+'</text></svg></div>';
  }

  function render(){
    const sc = q("sc"), iv = q("iv"); const S = DATA[sc].summary, rows = DATA[sc].series[iv].data;
    const cur = S.current, d = S.delta, prev = S.previous;
    const tErr = +$("t-err").value/100, tLat = +$("t-lat").value, tDrift = +$("t-drift").value;
    $("o-err").textContent = (tErr*100).toFixed(2)+"%"; $("o-lat").textContent = tLat+" ms"; $("o-drift").textContent = "±"+tDrift.toFixed(3);
    $("status").innerHTML = "<b>Data Source:</b> <code>"+S.source+"</code> · <b>Last Updated:</b> "+S.last_updated+" · <b>Window:</b> "+S.start.slice(0,10)+" → "+S.end.slice(0,10)+" at "+iv;
    const syn = S.source.endsWith("synthetic_backfill"); $("synthetic").hidden = !syn;
    $("synthetic").textContent = "This window contains backfilled entries that no client actually sent. They are here to demonstrate the charts; they are not real traffic.";
    const hasPrev = prev.total_requests > 0;
    $("kpis").innerHTML =
      '<div class="kpi"><div class="l">Total Requests</div><div class="v">'+cur.total_requests.toLocaleString()+'</div>'+delta(hasPrev ? d.total_requests : null, 0, "", false)+'</div>' +
      '<div class="kpi"><div class="l">Avg Response Time</div><div class="v">'+fmt(cur.avg_response_time_ms,1,"ms")+'</div>'+delta(d.avg_response_time_ms,1,"ms",true)+'</div>' +
      '<div class="kpi"><div class="l">Avg Error Rate</div><div class="v">'+fmt(cur.error_rate==null?null:cur.error_rate*100,2,"%")+'</div>'+delta(d.error_rate==null?null:d.error_rate*100,2,"pp",true)+'</div>' +
      '<div class="kpi"><div class="l">Avg Probability</div><div class="v">'+fmt(cur.avg_probability,3)+'</div>'+delta(d.avg_probability,3,"",false)+'</div>';
    const al = [];
    if (cur.error_rate != null && cur.error_rate > tErr) al.push("⚠️ Error rate is high: "+(cur.error_rate*100).toFixed(2)+"% of requests did not return 2xx, above the "+(tErr*100).toFixed(1)+"% threshold.");
    if (cur.avg_response_time_ms != null && cur.avg_response_time_ms > tLat) al.push("⚠️ Average latency is high: "+cur.avg_response_time_ms.toFixed(1)+" ms, above the "+tLat+" ms threshold.");
    if (d.avg_probability != null && Math.abs(d.avg_probability) >= tDrift) al.push("⚠️ Average predicted probability moved by "+(d.avg_probability>0?"+":"")+d.avg_probability.toFixed(3)+" against the previous window. Check whether the input mix or the model changed.");
    $("alerts").innerHTML = al.length ? al.map(a => '<div class="alert">'+a+'</div>').join("") : '<div class="alert none">No alert at these thresholds.</div>';
    if (!rows.length) { $("charts").innerHTML = '<div class="alert none">当前时间窗口内没有可展示的数据。 No requests were logged in this window.</div>'; $("raw").innerHTML = ""; return; }
    $("charts").innerHTML = chart("Requests per Interval", rows, "requests", "requests") + chart("Average Response Time (ms)", rows, "avg_response_time_ms", "ms") + chart("Error Rate (%)", rows, "error_rate", "%", 100) + chart("Average Predicted Probability", rows, "avg_probability", "probability", 1, [0,1]);
    $("raw").innerHTML = '<table><thead><tr><th>timestamp</th><th>requests</th><th>avg_response_time_ms</th><th>error_rate</th><th>avg_probability</th></tr></thead><tbody>' +
      rows.map(r => '<tr><td>'+r.timestamp+'</td><td>'+r.requests+'</td><td>'+fmt(r.avg_response_time_ms,4)+'</td><td>'+fmt(r.error_rate,4)+'</td><td>'+fmt(r.avg_probability,4)+'</td></tr>').join("") + '</tbody></table>';
  }
  document.querySelectorAll("input").forEach(el => ["input", "change"].forEach(ev => el.addEventListener(ev, render)));
  render();
})();
</script>
</body></html>
'''
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML.replace("__DATA__", payload).replace("__CAPTURED__", captured))
print(f"wrote {OUT} ({OUT.stat().st_size/1000:.0f} KB), captured {captured}")
