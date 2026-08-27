# Analytics Dashboard 

## 1. Overview 

### 1.1 Page Purpose 

Analytics Dashboard is a system monitoring and analysis module within the Cognitive Shorts system front-end UI (built on Streamlit). This page displays how the back-end recommendation service has been running over a period of time, including request volume, average response time, error rate and the trend of the model output probability, so that it can be judged quickly whether the system is running normally. 

### 1.2 Page Goals 

This page is intended to answer the following questions: 

- Whether the system has been called recently 
- Whether the call volume is rising or falling 
- Whether API responses have become slower 
- Whether a relatively large number of errors have occurred 
- Whether the model output probability has fluctuated noticeably 

### 1.3 Intended Users 

- Testers: to observe whether API calls are stable 
- Operations staff: to view system traffic and error conditions 
- Algorithm engineers: to observe whether the model output distribution has changed 

---

## 2. Page Requirements (UI) 

The page as a whole is divided into five functional areas: **Title Area**, **Status Information Area**, **Core Metrics Area**, **Trend Charts Area** and **Raw Data Area** 

### 2.1 Page Title and Navigation 

- **Title**: `📈 Analytics Dashboard` 
- **Entry point**: select `"Analytics Dashboard"` in the left-hand Sidebar navigation bar 
- **Note**: in the current version, the Analytics page is not required to implement additional complex filter controls. After the page is opened it should automatically fetch and display the data for the default time window (for example: the default time window is the last 7 days and the aggregation granularity is 1 hour) 

### 2.2 Status Information Area (Status Summary) 

Located below the page title, used to display the data source and the refresh information used by the current dashboard 

**UI elements:** 

1. **Data Source**: displays the current data source, for example `in_memory_api_logs` 
2. **Last Updated**: displays the time of the most recent data update 

**Display purpose:** 

- To tell the user that what they are currently seeing is real runtime data 
- To tell the user when the page data was updated, so that it is not mistaken for a real-time streaming refresh 

### 2.3 Core Metrics Area (KPI Metrics) 

The top of the page displays 4 core metric cards 

**UI elements:** 

1. `Total Requests` 
2. `Avg Response Time` 
3. `Avg Error Rate` 
4. `Avg Probability` 

**Display requirements:** 

- Each metric is displayed as a card in `st.metric()` style 
- Must support displaying the metric value for the current period 
- Must support displaying the difference `delta` against the previous period 
- The numeric format must be consistent and easy to read 

### 2.4 Trend Charts Area (Trend Charts) 

The middle of the page displays 4 line charts, each used to show the trend of one core metric over the time dimension 

**UI elements:** 

1. **Chart 1**: `Requests per Interval` 
2. **Chart 2**: `Average Response Time (ms)` 
3. **Chart 3**: `Error Rate (%)` 
4. **Chart 4**: `Average Predicted Probability` 

**Chart requirements:** 

- The chart type must uniformly be a line chart or a line plus point chart 
- The X axis is the timestamp `timestamp` 
- The Y axis is the corresponding metric value 
- The charts are displayed in ascending time order 
- The chart width adapts to the page container 

### 2.5 Raw Data Area (Raw Data) 

Located at the bottom of the page, collapsed by default; once clicked it shows the detail data table behind the current charts 

**UI elements:** 

1. **Collapsible container title**: `Raw Data` 
2. **Data table**: displays the time series aggregation result returned by the back end 

**Display purpose:** 

- To make debugging and acceptance testing easier 
- To make it easier to check whether the charts and the raw data agree 

### 2.6 Status Prompt and Alert Area (Alerts) 

When a system metric reaches an abnormal threshold, the page should display a prompt message 

**UI elements:** 

1. **Error rate alert**: when the error rate is too high, display a yellow warning bar 
2. **Response time alert**: when the average response time is too high, display a yellow warning bar 
3. **Probability change prompt**: when the average probability has changed too much relative to the previous period, display a prompt bar 

---

## 3. Functional Requirements 

### 3.1 Page Initialisation Flow 

When the user opens the `Analytics Dashboard` page, the front end should automatically carry out the following flow: 

1. The page uses real data by default 
2. Generate the default time window; by default view the last `7d` of data 
3. Generate the time series request parameters: 
   - `start`: start time 
   - `end`: end time 
   - `interval`: time granularity, `1h` by default 
4. The front end calls the real back-end analytics API to obtain the data 
5. After the data has been obtained successfully, render the status information first, then the metric cards, the alert area, the charts area and the raw data area 

### 3.2 Data Retrieval Flow 

The page displays statistics computed from real request logs 

**Processing logic:** 

1. The front end first requests the summary API `/analytics/summary` 
2. If the summary API succeeds, then request the time series API `/analytics/timeseries` 
3. The front end parses the JSON data returned by the back end 
4. Extract the fields `source`, `last_updated`, `current`, `delta`, `data` and so on 
5. Convert `data` into a DataFrame, used for chart rendering 
6. If the `timestamp` field is present, convert it to a time type and sort in ascending time order 

### 3.3 Summary Metric Definitions 

#### 3.3.1 Total Requests 

- **Definition**: the total number of requests within the current statistics time range 
- **Type**: integer 
- **Source**: `summary.current.total_requests` 
- **Display form**: display the integer value directly 
- **Meaning of delta**: the total number of requests in the current period minus the total number of requests in the previous period 

#### 3.3.2 Avg Response Time 

- **Definition**: the average response time of all requests within the current statistics time range 
- **Unit**: milliseconds `ms` 
- **Type**: floating point number 
- **Source**: `summary.current.avg_response_time_ms` 
- **Display form**: keep 1 decimal place, for example `23.4ms` 
- **Meaning of delta**: the average response time of the current period minus the average response time of the previous period 

#### 3.3.3 Avg Error Rate 

- **Definition**: the average proportion of failed requests out of the total number of requests within the current statistics time range 
- **Unit**: percentage `%` 
- **Type**: floating point number 
- **Source**: `summary.current.error_rate` 
- **Display form**: display after multiplying by 100, keep 2 decimal places, for example `1.35%` 
- **Meaning of delta**: the error rate of the current period minus the error rate of the previous period 

#### 3.3.4 Avg Probability 

- **Definition**: the mean of the model predicted probability within the current statistics time range 
- **Range**: `0.0 ~ 1.0` 
- **Type**: floating point number or null 
- **Source**: `summary.current.avg_probability` 
- **Display form**: keep 3 decimal places, for example `0.742` 
- **Meaning of delta**: the average probability of the current period minus the average probability of the previous period 

### 3.4 Chart Definitions 

#### 3.4.1 Requests per Interval 

- **Definition**: the number of requests within each time granularity 
- **Example**: if `interval = 1h`, each point represents "the number of requests within that hour" 
- **Source field**: `timeseries.data[].requests` 
- **Purpose**: to observe the traffic trend and the peaks and troughs of access 

#### 3.4.2 Average Response Time (ms) 

- **Definition**: the average response time of requests within each time granularity 
- **Source field**: `timeseries.data[].avg_response_time_ms` 
- **Purpose**: to observe changes in API speed 

#### 3.4.3 Error Rate (%) 

- **Definition**: the proportion of failed requests within each time granularity 
- **Source field**: `timeseries.data[].error_rate` 
- **Display requirement**: the front end must multiply by `100` to convert to a percentage before plotting 
- **Purpose**: to observe service stability 

#### 3.4.4 Average Predicted Probability 

- **Definition**: the mean of the model output probability within each time granularity 
- **Source field**: `timeseries.data[].avg_probability` 
- **Y axis range**: it is recommended to fix it at `0 ~ 1` 
- **Purpose**: to observe whether the model output has shifted noticeably 

### 3.5 Alert Rules 

After the front end has obtained the summary metrics, it must evaluate them against the thresholds and display alert messages 

1. **Error rate alert**: if `error_rate > 0.02`, display an "error rate is high" alert 
2. **Response time alert**: if `avg_response_time_ms > 300`, display an "average latency is high" alert 
3. **Probability fluctuation prompt**: if `abs(delta.avg_probability) >= 0.1`, display an "average probability has changed considerably" prompt 

### 3.6 Empty Data and Exception Handling 

#### 3.6.1 Empty Data Handling 

1. If `timeseries.data` is an empty array, the page does not draw the charts 
2. The page displays the prompt message: `No data to display in the current time window.` 
3. The page stops rendering the remaining chart content 

#### 3.6.2 API Exception Handling 

1. If the `/analytics/summary` or `/analytics/timeseries` request fails 
2. The front end should catch the exception information 
3. The page displays the error message directly, for example: `Data source unavailable: {error}` 

#### 3.6.3 Null Value Handling 

1. If a given metric value is `None`, the page should display `-` rather than raising an error 
2. If `avg_probability` is empty at a given time point, the chart is allowed to have a null value at that point 
3. If there is no data for the previous period, the related `delta` may be empty and the change value is not required to be displayed 

---

## 4. Detailed Processing Flow (Processing Flow) 

Understand and implement it in the order "back end records logs -> back end aggregates -> front end requests -> front end renders" 

### 4.1 Overall Flow Summary 

1. The user calls the prediction API `/predict` 
2. The back-end middleware automatically records the log of this request 
3. The request log is written into the in-memory log queue `request_logs` 
4. The user opens the `Analytics Dashboard` page 
5. The front end automatically calls `/analytics/summary` to obtain the summary metrics 
6. The front end automatically calls `/analytics/timeseries` to obtain the time series data 
7. The front end converts the returned result into metric cards, line charts and a raw data table 
8. If a metric is abnormal, the front end additionally displays an alert message 

### 4.2 Back-end Log Recording Flow 

The data precondition of the Analytics Dashboard is: the back end must record request logs first. Log collection must be implemented first, otherwise the dashboard has no real data source. 

**Processing steps:** 

1. Register a global HTTP middleware in FastAPI 
2. When each request comes in, first read the current request path `request.url.path` 
3. If the path is one of the following internal routes, do not write an analytics log: 
   - `/` 
   - `/analytics/*` 
   - `/docs` 
   - `/openapi.json` 
4. Record the request start time `start_ts` 
5. Execute the business API logic `call_next(request)` 
6. When the request succeeds, record the response status code `status_code` 
7. If an `HTTPException` occurs, record the corresponding exception status code 
8. If an unknown exception occurs, record `500` by default 
9. Record the end time `end_ts` in `finally` 
10. Compute the request duration `duration_ms = end_ts - start_ts` 
11. Assemble a single log dictionary containing at least the following fields: 

```json
{ 
  "timestamp": "2026-04-28T10:00:00+00:00", 
  "endpoint": "/predict", 
  "status_code": 200, 
  "response_time_ms": 23.5 
}
```

12. If the current request is the model prediction API and the business code has obtained the predicted probability and the model version, the following should also be added: 

```json
{ 
  "model_version": "LightGBM_v1", 
  "probability": 0.812 
}
```

13. Append the log to the in-memory queue, for example `deque(maxlen=200000)` 

### 4.3 Prediction API and Log Interaction Flow 

So that the Analytics Dashboard can display the information related to `Avg Probability` and `model_version`, after the prediction API has finished predicting it must put these values into `request.state` for the middleware to read. 

**Processing steps:** 

1. `/predict` receives the recommendation request parameters passed in by the front end 
2. The back end builds the model input features 
3. The back end performs data validation 
4. The back end calls the model to make a prediction 
5. Compute the predicted class and the predicted probability 
6. Write the following information into `request.state`: 
   - `request.state.probability = probability` 
   - `request.state.model_version = the current model name or version` 
7. Return the prediction result to the front end 
8. After the request completes, the middleware reads these additional fields from `request.state` and writes them into the log 

### 4.4 Summary API `/analytics/summary` Processing Flow 

This API is responsible for returning the overall statistics of the "current period" and the "previous period", used to render the 4 KPI cards at the top. 

**Request parameters:** 

- `start`: statistics start time, optional 
- `end`: statistics end time, optional 
- `endpoint`: filter by API path, optional 
- `model_version`: filter by model version, optional 
- `status_code_family`: filter by status code family, optional, allowed values `2xx`, `4xx`, `5xx` 

**Processing steps:** 

1. Parse the `start` and `end` time strings 
2. If `end` is empty, default to the current UTC time 
3. If `start` is empty, default to `end - 7 days` 
4. If `end <= start`, return `400 Bad Request` directly 
5. Compute the current time window length `window = end - start` 
6. Compute the previous period time range: 
   - `prev_start = start - window` 
   - `prev_end = start` 
7. Filter the current period logs from `request_logs` 
8. Filter the previous period logs from `request_logs` 
9. Compute the aggregated metrics separately for each period: 
   - `total_requests = the total number of logs` 
   - `avg_response_time_ms = the mean of response_time_ms` 
   - `error_rate = the mean proportion of non-2xx requests` 
   - `avg_probability = the mean over all logs carrying a probability field` 
10. If a period has no data: 

   - `total_requests = 0` 
   - the remaining average fields may return `None` 

11. Compute `delta = current - previous` 
12. Return JSON data with a uniform structure 

**Response example:** 

```json
{ 
  "source": "in_memory_api_logs", 
  "last_updated": "2026-04-28T10:30:00+00:00", 
  "start": "2026-04-21T10:30:00+00:00", 
  "end": "2026-04-28T10:30:00+00:00", 
  "filters": { 
    "endpoint": null, 
    "model_version": null, 
    "status_code_family": null 
  }, 
  "current": { 
    "total_requests": 120, 
    "avg_response_time_ms": 24.1, 
    "error_rate": 0.0167, 
    "avg_probability": 0.733 
  }, 
  "previous": { 
    "total_requests": 98, 
    "avg_response_time_ms": 22.5, 
    "error_rate": 0.0100, 
    "avg_probability": 0.701 
  }, 
  "delta": { 
    "total_requests": 22, 
    "avg_response_time_ms": 1.6, 
    "error_rate": 0.0067, 
    "avg_probability": 0.032 
  } 
}
```

### 4.5 Time Series API `/analytics/timeseries` Processing Flow 

This API is responsible for returning the trend data aggregated by time granularity, used to render the 4 line charts. 

**Request parameters:** 

- `start`: statistics start time, optional 
- `end`: statistics end time, optional 
- `interval`: aggregation granularity, `1h` by default 
- `endpoint`: filter by API path, optional 
- `model_version`: filter by model version, optional 
- `status_code_family`: filter by status code family, optional 

**Processing steps:** 

1. Parse `start` and `end` 
2. If `end` is empty, take the current time 
3. If `start` is empty, default to the last `7 days` 
4. Validate that `end > start`, otherwise return `400` 
5. Parse `interval` into a time bucket, for example: 
   - `5min` -> 5 minutes 
   - `1h` -> 1 hour 
   - `1d` -> 1 day 
6. Filter the logs meeting the conditions from `request_logs` 
7. If the filtered result is empty, return `data: []` directly 
8. Convert the logs into a DataFrame 
9. Convert `timestamp` to a time type and set it as the index 
10. Add the auxiliary field `is_error`: 
    - if the status code is not `2xx`, record it as `1` 
    - otherwise record it as `0` 
11. Use `resample(interval)` to aggregate over time 
12. Compute the aggregation results: 
    - `requests`: the number of requests within that bucket 
    - `avg_response_time_ms`: the average response time within that bucket 
    - `error_rate`: the mean of `is_error` within that bucket 
    - `avg_probability`: the mean probability within that bucket 
13. Convert the aggregation result row by row into a JSON array and return it 

**Response example:** 

```json
{ 
  "source": "in_memory_api_logs", 
  "last_updated": "2026-04-28T10:30:00+00:00", 
  "start": "2026-04-21T10:30:00+00:00", 
  "end": "2026-04-28T10:30:00+00:00", 
  "interval": "1h", 
  "data": [ 
    { 
      "timestamp": "2026-04-28T08:00:00+00:00", 
      "requests": 12, 
      "avg_response_time_ms": 19.2, 
      "error_rate": 0.0, 
      "avg_probability": 0.721 
    }, 
    { 
      "timestamp": "2026-04-28T09:00:00+00:00", 
      "requests": 15, 
      "avg_response_time_ms": 25.6, 
      "error_rate": 0.0667, 
      "avg_probability": 0.744 
    } 
  ] 
}
```

### 4.6 Front-end Page Rendering Flow 

When implementing the front-end page, the data may be handled in the following order: 

1. Render the page title `📈 Analytics Dashboard` 
2. Compute the default time window `start` and `end` 
3. Assemble the request parameters `params = {start, end, interval}` 
4. Request `/analytics/summary` 
5. If it fails, display the error message 
6. Request `/analytics/timeseries` 
7. If it fails, display the error message 
8. Take the following out of `summary`: 
   - `current` 
   - `delta` 
   - `source` 
   - `last_updated` 
9. Take `data` out of `timeseries` and convert it into a DataFrame 
10. If the DataFrame is not empty, convert `timestamp` into a time format and sort it 
11. Render the status information area 
12. Render the 4 metric cards 
13. Decide whether to display alerts according to the thresholds 
14. If there is no time series data, display the empty state and stop 
15. Use the DataFrame to draw the 4 line charts separately 
16. Display the raw aggregated data as a table at the bottom of the page 

### 4.7 Chart Rendering Detail Flow 

#### 4.7.1 Chart 1: Requests per Interval 

1. Take `timestamp` for the X axis 
2. Take `requests` for the Y axis 
3. Set the chart title to `Requests per Interval` 
4. Display the change in request volume as a line chart 

#### 4.7.2 Chart 2: Average Response Time (ms) 

1. Take `timestamp` for the X axis 
2. Take `avg_response_time_ms` for the Y axis 
3. Set the chart title to `Average Response Time (ms)` 
4. The unit is reflected in the title as `ms` 

#### 4.7.3 Chart 3: Error Rate (%) 

1. Take `timestamp` for the X axis 
2. Take `error_rate * 100` for the Y axis 
3. Set the chart title to `Error Rate (%)` 
4. Note that the front end must convert the decimal ratio into a percentage value before plotting 

#### 4.7.4 Chart 4: Average Predicted Probability 

1. Take `timestamp` for the X axis 
2. Take `avg_probability` for the Y axis 
3. Set the chart title to `Average Predicted Probability` 
4. It is recommended to fix the Y axis range at `0 ~ 1`, to make probability fluctuation easier to observe 

---

## 5. Back-end Support Requirements (API Requirements) 

### 5.1 Log Collection Support 

1. A global HTTP middleware must be implemented to record logs of business requests 
2. The log must record at least the following fields: 
   - `timestamp` 
   - `endpoint` 
   - `status_code` 
   - `response_time_ms` 
3. If a model prediction result exists, it should also support recording: 
   - `probability` 
   - `model_version` 
4. The log container may use an in-memory `deque` with a maximum length set, to avoid unbounded growth 

### 5.2 Summary API Support 

1. Provide the `GET /analytics/summary` route 
2. Support the time range parameters `start`, `end` 
3. Support the filter parameters `endpoint`, `model_version`, `status_code_family` 
4. Support returning the current period, previous period and difference results 
5. When the time parameters are invalid, it should return `400 Bad Request` 

### 5.3 Time Series API Support 

1. Provide the `GET /analytics/timeseries` route 
2. Support the time granularity parameter `interval` 
3. Support aggregating the raw logs into time buckets 
4. The returned fields must be consistent with the front-end chart fields 
5. When `interval` is invalid, it should return `400 Bad Request` 

### 5.4 Data Definition Requirements 

The data structure returned by the back end must be stable; the front end depends directly on the following fields for rendering: 

**The Summary API must return:** 

- `source` 
- `last_updated` 
- `start` 
- `end` 
- `filters` 
- `current` 
- `previous` 
- `delta` 

**The Timeseries API must return:** 

- `source` 
- `last_updated` 
- `start` 
- `end` 
- `interval` 
- `data` 

**Each data entry in Timeseries must contain:** 

- `timestamp` 
- `requests` 
- `avg_response_time_ms` 
- `error_rate` 
- `avg_probability` 

---

## 6. Acceptance Criteria 

1. After opening the `Analytics Dashboard` page, the page title can be seen 
2. After the page is opened, the data is fetched automatically without any extra clicks 
3. `Data Source` and `Last Updated` are displayed correctly at the top 
4. The page displays the 4 KPI metric cards correctly 
5. The page displays the 4 trend charts correctly 
6. The values in the charts and in the raw data table are logically consistent 
7. When there is no data within the time range, the page displays an empty state prompt rather than a blank page or an error 
8. When the analytics API fails, the page can display the error message 
9. When the error rate, the response time or the probability change exceeds a threshold, the page displays the corresponding alert 
10. The raw aggregated data can be expanded and viewed in the `Raw Data` area 

