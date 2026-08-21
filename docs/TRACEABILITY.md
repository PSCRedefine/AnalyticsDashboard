# Requirements Traceability

Every requirement in [SPEC.md](SPEC.md), where it is implemented, and what
proves it. 101 tests.

## 2 · Page requirements

| § | Requirement | Implementation | Evidence |
|---|---|---|---|
| 2.1 | Title `📈 Analytics Dashboard` | `st.title` in `app.py` | [screenshot](../image/ui_analytics_dashboard.png) |
| 2.1 | Sidebar entry | `st.selectbox("Select Page", ["Analytics Dashboard"])` | same |
| 2.1 | Auto-fetch on entry, no controls | Window computed at module level; no widgets gate the fetch | same |
| 2.1 | Default 7 days at 1 h | `DEFAULT_WINDOW_DAYS`, `DEFAULT_INTERVAL` | `test_summary_defaults_to_a_seven_day_window`, `test_timeseries_defaults_to_one_hour_buckets` |
| 2.2 | Data Source | Caption above the cards | [screenshot](../image/ui_analytics_dashboard.png) |
| 2.2 | Last Updated | Same caption, from `store.last_updated()` | `test_last_updated_is_the_newest_entry` |
| 2.3 | Four `st.metric` cards | `show_metric` × 4 | [screenshot](../image/ui_analytics_dashboard.png) |
| 2.3 | Current value and delta | `summary.current` / `summary.delta` | `test_delta_is_current_minus_previous` |
| 2.4 | Four line charts | `line_chart` × 4 | [screenshot](../image/ui_analytics_dashboard.png) |
| 2.4 | X = timestamp, ascending | Sorted client-side; server returns oldest first | `test_buckets_are_returned_oldest_first` |
| 2.4 | Container-width charts | `width="stretch"` | see the note below |
| 2.5 | `Raw Data`, collapsed by default | `st.expander("Raw Data")` | [screenshot](../image/ui_alerts_and_raw_data.png) |
| 2.6 | Three alert banners | Threshold block in `app.py` | [screenshot](../image/ui_alerts_and_raw_data.png) |

**On `use_container_width=True`.** The specification's phrasing names that
parameter; this repository passes `width="stretch"`. They are the same
instruction — Streamlit renamed it, and the pinned version emits a deprecation
warning for the old spelling that would show up in the running app.

## 3 · Functional requirements

### 3.1 / 3.2 — Initialisation and fetch order

| Criterion | Implementation | Evidence |
|---|---|---|
| Real data by default | The log is real traffic; `source` says so, and says when it is not | `test_real_entries_report_the_real_source`, `test_one_synthetic_entry_changes_the_source` |
| Summary first, then timeseries | Sequential calls, each with its own `st.stop()` on failure | Read `app.py` |
| Both share one window | `window` dict built once and passed to both | `test_the_summary_total_matches_the_sum_of_the_buckets` |
| `data` → DataFrame, timestamps parsed and sorted | `pd.to_datetime(..., utc=True).sort_values` | [screenshot](../image/ui_alerts_and_raw_data.png) |

### 3.3 — KPI definitions

| Metric | Source field | Format | Test |
|---|---|---|---|
| Total Requests | `current.total_requests` | integer | `test_the_four_aggregates` |
| Avg Response Time | `current.avg_response_time_ms` | `24.3ms`, 1 dp | `test_the_four_aggregates` |
| Avg Error Rate | `current.error_rate` | `×100`, `1.11%`, 2 dp | `test_error_rate_is_a_fraction_not_a_percentage` |
| Avg Probability | `current.avg_probability` | `0.293`, 3 dp | `test_probability_averages_only_over_rows_that_have_one` |

Delta labels use `pp` for the error rate — the change in a percentage is
percentage points. Response time and error rate use `delta_color="inverse"`,
because up is bad for both; reasoning in [ANALYTICS.md](ANALYTICS.md#why-the-kpi-colours-are-not-the-reference-screenshots).

### 3.4 — Chart definitions

| Chart | Field | Notes | Test |
|---|---|---|---|
| Requests per Interval | `requests` | Bucket counts including zeroes | `test_an_empty_bucket_keeps_its_place_with_zero_requests` |
| Average Response Time (ms) | `avg_response_time_ms` | Unit in the title | `test_one_row_per_bucket_with_the_four_chart_fields` |
| Error Rate (%) | `error_rate × 100` | Converted on the page only | `test_error_rate_is_a_fraction_not_a_percentage` |
| Average Predicted Probability | `avg_probability` | Y pinned to 0–1 | `test_a_bucket_of_only_failures_has_no_probability` |

The probability axis is fixed rather than autoscaled. Autoscaling turns a
half-point wobble into a mountain range, which is the opposite of what a drift
chart is for.

### 3.5 — Alert rules

| Rule | Threshold | Implementation |
|---|---|---|
| Error rate | `> 0.02` | `ERROR_RATE_ALERT` |
| Response time | `> 300 ms` | `RESPONSE_TIME_ALERT_MS` |
| Probability drift | `abs(delta) >= 0.1` | `PROBABILITY_DRIFT_ALERT` |

All three firing: [screenshot](../image/ui_alerts_and_raw_data.png).

These evaluate the **window average**, as specified — which has a documented
blind spot for short incidents inside a long window. See
[ANALYTICS.md](ANALYTICS.md#alert-thresholds-are-window-averages-and-that-has-a-blind-spot).

### 3.6 — Empty and error handling

| Criterion | Implementation | Evidence |
|---|---|---|
| Empty `data` → no charts | `if not rows: … st.stop()` | [screenshot](../image/ui_empty_window.png) |
| Message `当前时间窗口内没有可展示的数据。` | Verbatim, with an English line naming the fix | same |
| Rendering stops | `st.stop()` | same |
| Endpoint failure → `数据源不可用：{error}` | Verbatim on both call sites | Read `app.py` |
| `None` → `-` | `number()` | [screenshot](../image/ui_empty_window.png) |
| A null probability point is allowed | Nulls pass through to Plotly | `test_a_bucket_of_only_failures_has_no_probability` |
| No previous window → no delta | Server nulls the averages; the page drops the count delta | `test_delta_against_an_empty_previous_window_is_null_not_the_current_value` |

## 4 · Processing flow

### 4.2 — Log collection

| Step | Implementation | Evidence |
|---|---|---|
| Global HTTP middleware | `RequestLoggingMiddleware` | `test_a_prediction_is_logged_with_all_six_fields` |
| Skip internal routes | `config.EXCLUDED_PATHS` / `EXCLUDED_PREFIXES` | `test_internal_routes_are_not_logged`, `test_the_analytics_routes_do_not_log_themselves` |
| Time the call | `time.perf_counter()` around `call_next` | `test_a_prediction_is_logged_with_all_six_fields` |
| Record the status | From the response | same |
| `HTTPException` → its status | `except HTTPException` | `test_a_failed_prediction_is_logged_with_its_status_and_no_probability` |
| Unknown exception → 500 | `except Exception` | `test_a_route_that_raises_is_logged_as_a_500` |
| Four required fields | `RequestLogStore.record` | `test_records_the_four_required_fields` |
| Plus `probability`, `model_version` | From `request.state` | `test_the_probability_comes_from_request_state` |
| `deque(maxlen=200000)` | `config.LOG_CAPACITY` | `test_the_buffer_is_bounded_and_drops_the_oldest` |

`/health` is excluded beyond the specification's list. Reasoning in
[ANALYTICS.md](ANALYTICS.md#health-is-excluded-and-the-specification-does-not-say-so).

### 4.3 — Prediction / log handoff

`/predict` sets `request.state.probability` and `request.state.model_version`;
the middleware reads them in its `finally` block, after the response exists.
Verified by `test_the_probability_comes_from_request_state`, which asserts the
logged value equals the value the client received.

### 4.4 — `/analytics/summary`

| Step | Evidence |
|---|---|
| Parse `start` / `end` | `test_a_naive_timestamp_is_read_as_utc`, `test_a_z_suffix_is_accepted`, `test_an_unparseable_timestamp_is_a_400` |
| Default `end` to now, `start` to −7 d | `test_summary_defaults_to_a_seven_day_window` |
| `end <= start` → 400 | `test_an_inverted_window_is_a_400`, `test_an_equal_start_and_end_is_a_400` |
| Previous window of equal length | `test_summary_compares_against_the_window_immediately_before` |
| Four aggregates per window | `test_the_four_aggregates` |
| Empty window → 0 and nulls | `test_an_empty_window_counts_zero_and_averages_nothing` |
| `delta = current − previous` | `test_delta_is_current_minus_previous` |
| Filters applied and echoed | `test_summary_echoes_its_filters`, `test_summary_filters_narrow_the_result` |

### 4.5 — `/analytics/timeseries`

| Step | Evidence |
|---|---|
| Interval parsing | `test_valid_intervals`, `test_a_bare_m_means_minutes_not_months` |
| Invalid interval → 400 | `test_invalid_intervals_raise`, `test_an_invalid_interval_is_a_400` |
| No matching logs → `data: []` | `test_an_empty_window_returns_an_empty_data_array_not_an_error` |
| `is_error` from the status code | `test_anything_that_is_not_a_2xx_counts_as_an_error` |
| Resample and aggregate | `test_one_row_per_bucket_with_the_four_chart_fields` |
| Rows carry the five fields | `test_timeseries_points_carry_the_five_chart_fields` |

## 5 · Response shape

`SummaryResponse` and `TimeseriesResponse` are Pydantic models, so the shape is
enforced by the framework rather than by convention. Field presence is asserted
by `test_summary_returns_every_field_the_page_reads` and
`test_timeseries_returns_every_field_the_charts_read`.

## 6 · Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Title visible | [screenshot](../image/ui_analytics_dashboard.png) |
| 2 | Data fetched with no clicks | same |
| 3 | Data Source and Last Updated correct | same |
| 4 | Four KPI cards | same |
| 5 | Four trend charts | same |
| 6 | Charts and raw table agree | `test_the_summary_total_matches_the_sum_of_the_buckets`, [screenshot](../image/ui_alerts_and_raw_data.png) |
| 7 | Empty window shows a prompt, not a blank or an error | [screenshot](../image/ui_empty_window.png) |
| 8 | Endpoint failure shows an error | `数据源不可用：{error}` on both call sites |
| 9 | Thresholds produce banners | [screenshot](../image/ui_alerts_and_raw_data.png) |
| 10 | Raw Data expands | same |
