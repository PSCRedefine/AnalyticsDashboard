# Production readiness

What this service does not have yet, and what it would need before it carries
real traffic. Ordered by the risk of shipping without it.

Almost nothing here is a defect against the specification. The specification
stops where it stops; this document is where it would have to resume. It is
written to be argued with — each item states the risk, the remedy and the cost,
so that "accept this one" is a decision somebody can make on the record rather
than an omission nobody noticed.

## Blocking

### 1. The log does not survive the process

Entries live in a `deque` in one process's memory. A deploy resets the
dashboard to its empty state, and the compose file pins a single worker because
two workers would hold two disjoint logs. That pin is also a throughput ceiling
on the service being observed.

This is stated plainly in the README as the honest limit of an in-memory buffer.
It is repeated here because it is the item that has to change first: every other
improvement on this page is built on a store that forgets.

**Remedy.** Move the log out of the process. In practice that means emitting the
same signals to the platform's metrics and logging pipeline rather than storing
them here — see item 3.

**Cost.** High, and it removes most of this codebase. That is the correct
outcome.

### 2. Outcome monitoring is missing, so the expensive failure is invisible

The page watches request volume, latency, errors and the *distribution* of
model output. None of those detect the failure that costs money: the model
continuing to report an average probability of 0.38 while the real engagement
rate has moved to 0.25. The output distribution is unchanged in that scenario.
Every chart stays flat.

**Remedy.** A delayed-label job that joins predictions to the outcomes that
arrive later, recomputes Brier and ECE over that window, and alerts on the
calibration curve moving. Output drift is a proxy; calibration against
observed outcomes is the measurement.

**Cost.** Medium, and it requires a decision about how long to wait before an
absent engagement counts as a negative.

### 3. This reimplements metrics infrastructure in the request path

Timing every request, bucketing by interval, computing window aggregates and
retaining a bounded history is what a time-series database does. Doing it inside
the serving process buys the probability field — which the transport layer
genuinely cannot see — at the cost of owning storage, retention, concurrency and
cardinality.

**Remedy.** Keep the part that is actually novel: the route writing
`probability` and `model_version` to `request.state` so the middleware can
record them. Export those as metrics rather than storing them. Let the platform
own retention and let the page query the time-series database.

**Cost.** Medium. Most of the aggregation module becomes unnecessary, and the
single-worker pin goes away with it.

### 4. Alerts evaluate, but nothing is alerted

Three thresholds are computed and rendered. Nothing routes them anywhere: no
paging integration, no severity, no deduplication, no acknowledgement, no record
of what fired and what was done about it. An alert that is only visible on a
page somebody has to open is a colour, not an alert.

**Remedy.** Route to whatever the platform uses for on-call. Define severity and
an owner per alert before defining any more thresholds.

### 5. Window averages hide the incident they exist to catch

A single bad day inside a seven-day window averages out below every threshold
while being obvious in the charts. The README documents this and treats it as a
property of averaging, which it is — but the alerting is where it matters, and
there the property is a blind spot.

**Remedy.** Evaluate a short window alongside the long one and alert on the
shorter. Keep the long window for the cards, where it belongs.

### 6. Two aggregation paths held different ideas of a valid entry

`summarise` treats an absent `probability` key and an explicit `None` as the
same thing. `timeseries` did not, and raised on a window whose entries carried
an explicit `None`. It did not surface through HTTP only because the log store
strips `None` before the frame is ever built — the function was correct by
accident of its caller, not by contract.

Fixed, and the existing test covers it. The general lesson is the item: two
functions aggregating the same entries need one shared normalisation step, not
two independent assumptions about what an entry looks like.

### 7. The analytics routes are unauthenticated

Traffic volume, error rates, latency and the model's output distribution are all
readable by anyone who can reach the port.

**Remedy.** Authentication at the edge and an internal-only network placement.

---

## Required within the first quarter

- **Retention and downsampling.** The buffer holds 200,000 entries and then
  forgets. Real monitoring needs raw data for a short period and aggregates for
  a long one; "the last 200,000 requests" is neither.
- **Cardinality control on `model_version`.** It is a free-form string on every
  entry. Whatever stores it later will care.
- **Split `avg_probability` by endpoint.** Exact today with one prediction
  route, a blend the moment there are two.
- **Filters on the page.** `endpoint`, `model_version` and `status_code_family`
  work from `curl` and have no controls. The specification asked for none; an
  operator will.
- **Separate client errors from server errors in the health signal.** A 404 is
  the caller's mistake and a 500 is ours. Both count as errors today, which is
  right for a health signal and wrong for diagnosis.

---

## Accepted, with reasons

| Item | Why it is acceptable |
|---|---|
| Empty windows report null averages rather than zero | A zero draws a line that reads as "very fast" instead of "nothing happened", and makes an outage look like perfect health. |
| Empty buckets are kept rather than dropped | Dropping them joins the line across the gap and hides the outage entirely. |
| A missing previous window omits the delta | No comparison and no change are different statements. |
| `/analytics/*` excluded from its own log | Otherwise a dashboard left open becomes the busiest client of the service it monitors. |
| Backfilled entries flagged, and the flag reaches the page | Fabricated data is a legitimate demonstration aid; fabricated data that claims to be real is not. |

---

## What is already in place

Listed so this document reads as a review and not a confession.

| Concern | Where it is handled |
|---|---|
| Load failure does not kill the process | `/health` stays serviceable and reports the cause |
| Non-root container, dependency layer cached separately | `Dockerfile` |
| The console starts only behind a real health check | `docker-compose.yml` |
| Configuration is environment-backed, not hard-coded | `config.py` |
| The suite runs on every supported interpreter | `.github/workflows/tests.yml` |
