# Analytics Dashboard 

## 1. 概述 

### 1.1 页面定位 

Analytics Dashboard（分析看板）是 Cognitive Shorts 系统前端 UI（基于 Streamlit）中的一个系统监控与分析模块。该页面用于展示后端推荐服务在一段时间内的运行情况，包括请求量、平均响应时间、错误率以及模型输出概率变化趋势，快速判断系统是否正常运行。 

### 1.2 页面目标 

该页面是用于回答以下问题： 

- 系统最近有没有被调用 
- 调用量是升高还是降低 
- 接口响应是否变慢 
- 是否出现较多报错 
- 模型输出概率是否发生明显波动 

### 1.3 适用对象 

- 测试人员：用于观察接口调用是否稳定 
- 运维人员：用于查看系统流量与错误情况 
- 算法人员：用于观察模型输出分布是否变化 

---

## 2. 页面需求 (UI) 

页面整体划分为五个功能区：**标题区**、**状态信息区**、**核心指标区**、**趋势图表区** 和 **原始数据区** 

### 2.1 页面标题与导航 

- **标题**：`📈 Analytics Dashboard` 
- **入口**：左侧 Sidebar 导航栏选择 `"Analytics Dashboard"` 
- **说明**：当前版本中，Analytics 页面不要求额外实现复杂筛选控件。页面进入后应自动拉取默认时间窗口的数据并展示（例如：默认时间窗口为最近 7 天，统计粒度为 1 小时） 

### 2.2 状态信息区 (Status Summary) 

位于页面标题下方，用于展示当前看板所使用的数据来源和刷新信息 

**UI 元素：** 

1. **Data Source**：显示当前数据来源，例如 `in_memory_api_logs` 
2. **Last Updated**：显示最近一次数据更新时间 

**展示目的：** 

- 告知用户当前看到的是真实运行数据 
- 告知用户页面数据的更新时间，避免误判为实时流式刷新 

### 2.3 核心指标区 (KPI Metrics) 

页面顶部展示 4 个核心指标卡片 

**UI 元素：** 

1. `Total Requests` 
2. `Avg Response Time` 
3. `Avg Error Rate` 
4. `Avg Probability` 

**展示要求：** 

- 每个指标以 `st.metric()` 风格卡片展示 
- 支持显示当前周期指标值 
- 支持显示与上一周期的差值 `delta` 
- 数值格式需统一，便于阅读 

### 2.4 趋势图表区 (Trend Charts) 

页面中部展示 4 个折线图，每个图用于展示一个核心指标在时间维度上的变化趋势 

**UI 元素：** 

1. **图表 1**：`Requests per Interval` 
2. **图表 2**：`Average Response Time (ms)` 
3. **图表 3**：`Error Rate (%)` 
4. **图表 4**：`Average Predicted Probability` 

**图表要求：** 

- 图表类型统一为折线图或折线 + 点图 
- X 轴为时间戳 `timestamp` 
- Y 轴为对应指标值 
- 图表按照时间升序展示 
- 图表宽度自适应页面容器 

### 2.5 原始数据区 (Raw Data) 

位于页面底部，默认折叠，点击后可查看当前图表对应的明细数据表 

**UI 元素：** 

1. **折叠容器标题**：`Raw Data` 
2. **数据表格**：展示后端返回的时间序列聚合结果 

**展示目的：** 

- 方便调试与验收 
- 方便核对图表与原始数据是否一致 

### 2.6 状态提示与告警区 (Alerts) 

当系统指标达到异常阈值时，页面应显示提示信息 

**UI 元素：** 

1. **错误率告警**：错误率过高时显示黄色警告条 
2. **响应时间告警**：平均响应时间过高时显示黄色警告条 
3. **概率变化提示**：平均概率相对上一周期变化过大时显示提示条 

---

## 3. 功能需求 (Functional Requirements) 

### 3.1 页面初始化流程 

当用户进入 `Analytics Dashboard` 页面时，前端应自动执行以下流程： 

1. 页面默认使用真实数据 
2. 生成默认时间窗口，默认查看最近 `7d` 数据 
3. 生成时间序列请求参数： 
   - `start`：开始时间 
   - `end`：结束时间 
   - `interval`：时间粒度，默认 `1h` 
4. 前端调用后端真实 analytics 接口获取数据 
5. 获取数据成功后，先渲染状态信息，再渲染指标卡片、告警区、图表区、原始数据区 

### 3.2 数据获取流程 

页面使用真实请求日志统计结果进行展示 

**处理逻辑：** 

1. 前端先请求汇总接口 `/analytics/summary` 
2. 若汇总接口成功，再请求时间序列接口 `/analytics/timeseries` 
3. 前端解析后端返回的 JSON 数据 
4. 提取 `source`、`last_updated`、`current`、`delta`、`data` 等字段 
5. 将 `data` 转换为 DataFrame，用于图表渲染 
6. 若 `timestamp` 字段存在，则转换为时间类型并按时间升序排序 

### 3.3 汇总指标定义 

#### 3.3.1 Total Requests 

- **定义**：当前统计时间范围内请求总数 
- **类型**：整数 
- **来源**：`summary.current.total_requests` 
- **展示形式**：直接显示整数值 
- **delta 含义**：当前周期请求总数减去上一周期请求总数 

#### 3.3.2 Avg Response Time 

- **定义**：当前统计时间范围内所有请求的平均响应时间 
- **单位**：毫秒 `ms` 
- **类型**：浮点数 
- **来源**：`summary.current.avg_response_time_ms` 
- **展示形式**：保留 1 位小数，例如 `23.4ms` 
- **delta 含义**：当前周期平均响应时间减去上一周期平均响应时间 

#### 3.3.3 Avg Error Rate 

- **定义**：当前统计时间范围内错误请求数占总请求数的平均比例 
- **单位**：百分比 `%` 
- **类型**：浮点数 
- **来源**：`summary.current.error_rate` 
- **展示形式**：乘以 100 后显示，保留 2 位小数，例如 `1.35%` 
- **delta 含义**：当前周期错误率减去上一周期错误率 

#### 3.3.4 Avg Probability 

- **定义**：当前统计时间范围内模型预测概率的平均值 
- **范围**：`0.0 ~ 1.0` 
- **类型**：浮点数或空值 
- **来源**：`summary.current.avg_probability` 
- **展示形式**：保留 3 位小数，例如 `0.742` 
- **delta 含义**：当前周期平均概率减去上一周期平均概率 

### 3.4 图表定义 

#### 3.4.1 Requests per Interval 

- **定义**：每个时间粒度内的请求数 
- **示例**：若 `interval = 1h`，每个点表示“该小时内的请求次数” 
- **来源字段**：`timeseries.data[].requests` 
- **目的**：观察流量趋势与访问峰谷 

#### 3.4.2 Average Response Time (ms) 

- **定义**：每个时间粒度内请求平均响应时间 
- **来源字段**：`timeseries.data[].avg_response_time_ms` 
- **目的**：观察接口速度变化 

#### 3.4.3 Error Rate (%) 

- **定义**：每个时间粒度内错误请求占比 
- **来源字段**：`timeseries.data[].error_rate` 
- **展示要求**：前端绘图前乘以 `100` 转为百分比 
- **目的**：观察服务稳定性 

#### 3.4.4 Average Predicted Probability 

- **定义**：每个时间粒度内模型输出概率平均值 
- **来源字段**：`timeseries.data[].avg_probability` 
- **Y 轴范围**：建议固定在 `0 ~ 1` 
- **目的**：观察模型输出是否发生明显偏移 

### 3.5 告警规则 

前端在拿到汇总指标后，需要根据阈值进行判断并展示告警信息 

1. **错误率告警**：若 `error_rate > 0.02`，显示“错误率偏高”告警 
2. **响应时间告警**：若 `avg_response_time_ms > 300`，显示“平均延迟偏高”告警 
3. **概率波动提示**：若 `abs(delta.avg_probability) >= 0.1`，显示“平均概率变化较大”提示 

### 3.6 空数据与异常处理 

#### 3.6.1 空数据处理 

1. 若 `timeseries.data` 为空数组，则页面不绘制图表 
2. 页面显示提示信息：`当前时间窗口内没有可展示的数据。` 
3. 页面停止继续渲染后续图表内容 

#### 3.6.2 接口异常处理 

1. 若 `/analytics/summary` 或 `/analytics/timeseries` 请求失败 
2. 前端应捕获异常信息 
3. 页面直接显示错误信息，例如：`数据源不可用：{error}` 

#### 3.6.3 数据空值处理 

1. 若某项指标值为 `None`，页面应显示 `-`，而不是报错 
2. 若某个时间点的 `avg_probability` 为空，图表允许该点为空值 
3. 若上一周期无数据，则相关 `delta` 可为空，不强制显示变化值 

---

## 4. 详细处理流程 (Processing Flow) 

按照“后端记录日志 -> 后端聚合 -> 前端请求 -> 前端渲染”的顺序理解并实现 

### 4.1 整体流程总览 

1. 用户调用预测接口 `/predict` 
2. 后端中间件自动记录本次请求日志 
3. 请求日志写入内存日志队列 `request_logs` 
4. 用户进入 `Analytics Dashboard` 页面 
5. 前端自动调用 `/analytics/summary` 获取汇总指标 
6. 前端自动调用 `/analytics/timeseries` 获取时间序列数据 
7. 前端将返回结果转换为指标卡片、折线图和原始数据表 
8. 若指标异常，则前端额外显示告警信息 

### 4.2 后端日志记录流程 

Analytics Dashboard 的数据前提是：后端必须先记录请求日志。必须先实现日志采集，否则看板没有真实数据来源。 

**处理步骤：** 

1. 在 FastAPI 中注册一个全局 HTTP middleware 
2. 每次请求进入时，先读取当前请求路径 `request.url.path` 
3. 若路径为以下内部路由，则不写入 analytics 日志： 
   - `/` 
   - `/analytics/*` 
   - `/docs` 
   - `/openapi.json` 
4. 记录请求开始时间 `start_ts` 
5. 执行业务接口逻辑 `call_next(request)` 
6. 请求成功时，记录响应状态码 `status_code` 
7. 若发生 `HTTPException`，记录对应异常状态码 
8. 若发生未知异常，默认记录 `500` 
9. 在 `finally` 中记录结束时间 `end_ts` 
10. 计算请求耗时 `duration_ms = end_ts - start_ts` 
11. 组装单条日志字典，至少包含以下字段： 

```json
{ 
  "timestamp": "2026-04-28T10:00:00+00:00", 
  "endpoint": "/predict", 
  "status_code": 200, 
  "response_time_ms": 23.5 
}
```

12. 若当前请求是模型预测接口，且业务代码中得到了预测概率与模型版本，还应补充： 

```json
{ 
  "model_version": "LightGBM_v1", 
  "probability": 0.812 
}
```

13. 将日志追加写入内存队列，例如 `deque(maxlen=200000)` 

### 4.3 预测接口与日志联动流程 

为了让 Analytics Dashboard 能展示 `Avg Probability` 和 `model_version` 相关信息，预测接口在完成预测后，需要把这些值放入 `request.state` 中供 middleware 读取。 

**处理步骤：** 

1. `/predict` 接收前端传入的推荐请求参数 
2. 后端构造模型输入特征 
3. 后端执行数据校验 
4. 后端调用模型进行预测 
5. 计算预测类别与预测概率 
6. 将以下信息写入 `request.state`： 
   - `request.state.probability = probability` 
   - `request.state.model_version = 当前模型名称或版本` 
7. 返回预测结果给前端 
8. 中间件在请求完成后，从 `request.state` 读取这些附加字段并写入日志 

### 4.4 汇总接口 `/analytics/summary` 处理流程 

该接口负责返回“当前周期”和“上一周期”的整体统计指标，用于渲染顶部 4 个 KPI 卡片。 

**请求参数：** 

- `start`：统计开始时间，可选 
- `end`：统计结束时间，可选 
- `endpoint`：按接口路径过滤，可选 
- `model_version`：按模型版本过滤，可选 
- `status_code_family`：按状态码家族过滤，可选，允许值 `2xx`、`4xx`、`5xx` 

**处理步骤：** 

1. 解析 `start` 和 `end` 时间字符串 
2. 若 `end` 为空，则默认取当前 UTC 时间 
3. 若 `start` 为空，则默认取 `end - 7天` 
4. 若 `end <= start`，直接返回 `400 Bad Request` 
5. 计算当前时间窗口长度 `window = end - start` 
6. 计算上一周期时间范围： 
   - `prev_start = start - window` 
   - `prev_end = start` 
7. 从 `request_logs` 中筛选当前周期日志 
8. 从 `request_logs` 中筛选上一周期日志 
9. 对每个周期分别计算聚合指标： 
   - `total_requests = 日志总数` 
   - `avg_response_time_ms = response_time_ms 平均值` 
   - `error_rate = 非 2xx 请求占比平均值` 
   - `avg_probability = 所有带 probability 字段日志的平均值` 
10. 若某周期没有数据： 

   - `total_requests = 0` 
   - 其余平均值字段可返回 `None` 

11. 计算 `delta = current - previous` 
12. 返回统一结构的 JSON 数据 

**响应示例：** 

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

### 4.5 时间序列接口 `/analytics/timeseries` 处理流程 

该接口负责返回按时间粒度聚合后的趋势数据，用于渲染 4 个折线图。 

**请求参数：** 

- `start`：统计开始时间，可选 
- `end`：统计结束时间，可选 
- `interval`：聚合粒度，默认 `1h` 
- `endpoint`：按接口路径过滤，可选 
- `model_version`：按模型版本过滤，可选 
- `status_code_family`：按状态码家族过滤，可选 

**处理步骤：** 

1. 解析 `start` 和 `end` 
2. 若 `end` 为空，则取当前时间 
3. 若 `start` 为空，则默认取最近 `7天` 
4. 校验 `end > start`，否则返回 `400` 
5. 解析 `interval` 为时间桶，例如： 
   - `5min` -> 5 分钟 
   - `1h` -> 1 小时 
   - `1d` -> 1 天 
6. 从 `request_logs` 中筛选满足条件的日志 
7. 若筛选结果为空，则直接返回 `data: []` 
8. 将日志转换为 DataFrame 
9. 将 `timestamp` 转为时间类型，并设置为索引 
10. 新增辅助字段 `is_error`： 
    - 若状态码不是 `2xx`，则记为 `1` 
    - 否则记为 `0` 
11. 使用 `resample(interval)` 进行时间聚合 
12. 计算聚合结果： 
    - `requests`：该桶内请求数 
    - `avg_response_time_ms`：该桶内平均响应时间 
    - `error_rate`：该桶内 `is_error` 平均值 
    - `avg_probability`：该桶内概率平均值 
13. 将聚合结果逐行转换为 JSON 数组并返回 

**响应示例：** 

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

### 4.6 前端页面渲染流程 

在实现前端页面时，可按照以下顺序处理数据： 

1. 渲染页面标题 `📈 Analytics Dashboard` 
2. 计算默认时间窗口 `start` 和 `end` 
3. 组织请求参数 `params = {start, end, interval}` 
4. 请求 `/analytics/summary` 
5. 若失败，显示错误信息 
6. 请求 `/analytics/timeseries` 
7. 若失败，显示错误信息 
8. 从 `summary` 中取出： 
   - `current` 
   - `delta` 
   - `source` 
   - `last_updated` 
9. 从 `timeseries` 中取出 `data` 并转为 DataFrame 
10. 若 DataFrame 非空，则将 `timestamp` 转为时间格式并排序 
11. 渲染状态信息区 
12. 渲染 4 个指标卡片 
13. 根据阈值判断是否展示告警 
14. 若没有时间序列数据，则显示空状态并停止 
15. 使用 DataFrame 分别绘制 4 个折线图 
16. 在页面底部以表格方式展示原始聚合数据 

### 4.7 图表渲染细节流程 

#### 4.7.1 图表 1：Requests per Interval 

1. X 轴取 `timestamp` 
2. Y 轴取 `requests` 
3. 图表标题设为 `Requests per Interval` 
4. 以折线图方式展示请求量变化 

#### 4.7.2 图表 2：Average Response Time (ms) 

1. X 轴取 `timestamp` 
2. Y 轴取 `avg_response_time_ms` 
3. 图表标题设为 `Average Response Time (ms)` 
4. 单位在标题中体现为 `ms` 

#### 4.7.3 图表 3：Error Rate (%) 

1. X 轴取 `timestamp` 
2. Y 轴取 `error_rate * 100` 
3. 图表标题设为 `Error Rate (%)` 
4. 注意前端绘图前必须将小数比率转换为百分比值 

#### 4.7.4 图表 4：Average Predicted Probability 

1. X 轴取 `timestamp` 
2. Y 轴取 `avg_probability` 
3. 图表标题设为 `Average Predicted Probability` 
4. 建议固定 Y 轴范围为 `0 ~ 1`，便于观察概率波动 

---

## 5. 后端支持需求 (API Requirements) 

### 5.1 日志采集支持 

1. 必须实现全局 HTTP middleware，对业务请求进行日志记录 
2. 日志至少记录以下字段： 
   - `timestamp` 
   - `endpoint` 
   - `status_code` 
   - `response_time_ms` 
3. 若存在模型预测结果，还应支持记录： 
   - `probability` 
   - `model_version` 
4. 日志容器可使用内存 `deque`，并设置最大长度，避免无限增长 

### 5.2 汇总接口支持 

1. 提供 `GET /analytics/summary` 路由 
2. 支持时间范围参数 `start`、`end` 
3. 支持筛选参数 `endpoint`、`model_version`、`status_code_family` 
4. 支持返回当前周期、上一周期和差值结果 
5. 当时间参数非法时，应返回 `400 Bad Request` 

### 5.3 时间序列接口支持 

1. 提供 `GET /analytics/timeseries` 路由 
2. 支持时间粒度参数 `interval` 
3. 支持将原始日志按时间桶聚合 
4. 返回字段必须与前端图表字段一致 
5. 当 `interval` 非法时，应返回 `400 Bad Request` 

### 5.4 数据定义要求 

后端返回的数据结构必须稳定，前端直接依赖以下字段进行渲染： 

**Summary 接口必须返回：** 

- `source` 
- `last_updated` 
- `start` 
- `end` 
- `filters` 
- `current` 
- `previous` 
- `delta` 

**Timeseries 接口必须返回：** 

- `source` 
- `last_updated` 
- `start` 
- `end` 
- `interval` 
- `data` 

**Timeseries 中每条数据必须包含：** 

- `timestamp` 
- `requests` 
- `avg_response_time_ms` 
- `error_rate` 
- `avg_probability` 

---

## 6. 验收标准 (Acceptance Criteria) 

1. 打开 `Analytics Dashboard` 页面后，能够看到页面标题 
2. 页面进入后无需额外点击，即可自动拉取数据 
3. 顶部能够正确显示 `Data Source`、`Last Updated` 
4. 页面能够正确展示 4 个 KPI 指标卡片 
5. 页面能够正确展示 4 个趋势图表 
6. 图表与原始数据表中的数值逻辑一致 
7. 当时间范围内没有数据时，页面显示空状态提示，而不是空白或报错 
8. 当 analytics 接口失败时，页面能显示错误信息 
9. 当错误率、响应时间或概率变化超过阈值时，页面能够显示对应告警 
10. 原始聚合数据能够在 `Raw Data` 区域展开查看 

