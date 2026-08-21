# Design Notes

The decisions in this repository that are not obvious from the code, and the
reasoning behind them.

## The log is the feature

The Analytics page has no data source of its own. Everything on it is derived
from requests this process served, which means the middleware in
`middleware.py` is not plumbing around the feature — it *is* the feature, and
the two routes are a query language over what it recorded.

That inverts the usual priority. The middleware has three properties, in this
order:

1. **It cannot break a request.** Recording happens in a `finally` block, and
   `RequestLogStore.record` swallows its own failures. An observability layer
   that can fail a request is worse than no observability layer.
2. **It counts the failures.** A route that raises is logged as a 500 before the
   exception continues on its way. Dropping it would make the error-rate chart
   go quiet exactly when the service starts failing.
3. **It does not count itself.** `/analytics/*` is excluded, so a dashboard left
   open on a wall display does not become the busiest client of the service it
   is monitoring.

## `/health` is excluded, and the specification does not say so

Specification 4.2 step 3 lists `/`, `/analytics/*`, `/docs` and
`/openapi.json`. This service also excludes `/health`.

A container healthcheck runs every ten seconds. Left in, it contributes 8,640
requests a day at a millisecond of latency each — enough to halve the reported
average response time of a low-traffic service and to dominate its request
count. The chart would then be mostly a picture of the healthcheck.

This is a deliberate, documented departure. The list lives in
`config.EXCLUDED_PATHS` so it can be changed in one place.

## In memory, and what that costs

A `deque(maxlen=200_000)`. At roughly 200 bytes an entry that is about 40 MB
resident, which buys a week of traffic for a service doing a few requests a
second.

Three consequences, all accepted rather than worked around:

- **It does not survive a restart.** A deploy resets the dashboard to its empty
  state. `scripts/seed_traffic.py` refills it with real calls.
- **It is per process.** Two uvicorn workers would hold two disjoint logs and
  the dashboard would show whichever one answered. The compose file runs
  `--workers 1` for that reason, and the comment there says so. A second worker
  is not a scaling knob here, it is a correctness bug.
- **The oldest entry falls out, never the newest.** A traffic burst costs you
  history, not the present — which is the right way round for a page whose job
  is telling you what is happening now.

Fixing all three means moving the log out of process, which is a different
system: Redis, a time-series database, or a log pipeline. The specification asks
for an in-memory deque, and this is what one honestly is.

## Windows are half-open

`[start, end)`. Consecutive windows tile without double-counting the boundary,
which the summary route needs because it compares a window against the one
immediately before it. With closed intervals, a request landing exactly on the
boundary would be counted in both and the deltas would be quietly wrong.

## Nothing is not zero

The single most repeated decision in this codebase.

An empty window has **no** average response time. Reporting `0.0 ms` draws a
line at the bottom of the latency chart that reads as "very fast" instead of
"nothing happened", and the same trick makes an outage look like a period of
perfect health.

So: counts fall back to `0`, averages fall back to `null`, and the page renders
`null` as `-`. A delta whose previous side is null is omitted rather than shown
as `+0` — no comparison and no change are different statements.

Empty **buckets** are kept rather than dropped, with `requests: 0` and null
averages. Dropping them would join the line straight across the gap, which
hides the outage completely.

`avg_probability` averages only over entries that carry one. A 404 never reached
the model. Counting it as a zero would drag the drift chart down every time a
client sent a bad identifier — turning a client-side bug into what looks like
model degradation.

## The backfill route, and why it announces itself

The log starts empty, so a freshly started service renders the empty state
correctly and unhelpfully. `scripts/seed_traffic.py` fixes that honestly by
making real calls — but they all land in the minute you ran it, so a seven-day
window shows one bucket.

`scripts/backfill_history.py` fills the days before now with entries no client
ever sent. That is fabricated data, and the code treats it as such:

- the route 404s unless `ANALYTICS_ALLOW_BACKFILL=1`;
- every entry it writes carries `synthetic: true`;
- any window containing one reports `source` as
  `in_memory_api_logs+synthetic_backfill`;
- the page turns that into a warning banner.

Fabricated data is a legitimate demonstration aid. Fabricated data that claims
to be real is not, and the difference is entirely in whether the system can say
which it is showing you.

## Alert thresholds are window averages, and that has a blind spot

Specification 3.5 applies the thresholds to the summary figures, which are
averages over the whole window. Over seven days, a one-day incident is diluted
by six good days: a day at 6% errors and 420 ms inside a week that is otherwise
healthy averages out to roughly 1.5% and 146 ms, and **neither banner fires**.

The charts show it plainly — a step change in the last day, impossible to miss.
The banners do not. That is a real property of averaging over a window, not a
bug in the implementation, and it is the reason the charts are on the page
rather than just the cards.

A production alerting rule would evaluate the most recent buckets rather than
the window mean. That is out of scope for this specification, and the trade is
worth stating rather than leaving for someone to discover during an incident.

## Why the KPI colours are not the reference screenshot's

The reference image draws a rising error rate in green and a falling response
time in red — Streamlit's default, where positive is good.

This page passes `delta_color="inverse"` for Avg Response Time and Avg Error
Rate. Up is bad for both. A rising error rate drawn in green is a dashboard
actively working against its reader.

The change in a percentage is labelled `pp`, not `%`, for the same class of
reason: a jump from 1% to 2% is `+1pp`, and calling it `+1%` makes a doubling
read as a rounding error.
