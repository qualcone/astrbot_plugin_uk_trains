# astrbot_plugin_uk_trains

英国火车查询插件 for [AstrBot](https://github.com/AstrBotDevs/AstrBot)。作者：qualcone

用户在聊天里直接问就行，**不需要记任何指令**，大模型会自己调用插件里的工具：

- 「明天早上 8 点之后曼彻斯特 Piccadilly 到伦敦 Euston 的车」
- 「现在从 Reading 到 Paddington 的下一班几点？晚点吗？」

## 重要：RTT 旧版 API 已关闭

最初的设计用 `api.rtt.io`（用户名 + 密码 Basic 认证），但 Realtime Trains 已于 2026 年下线它，
替换为新版 API（`https://data.rtt.io`，**Bearer Token** 认证）。所以本插件配置的是 **Token**，不是用户名密码。

## 功能（LLM 工具）

| 工具 | 作用 |
| --- | --- |
| `search_trains(origin, destination, travel_date?, travel_time?)` | 查两站之间的直达班次（最多默认 8 班）：计划/预计发车、到达时间、站台、运营公司、晚点/取消及原因 |
| `get_train_detail(train_id, travel_date?)` | 查某一趟车的停靠站、各站站台、实际/预计时间、晚点原因（`train_id` 用 `search_trains` 结果里的 `ref`） |

- 站名可用城市/车站名、中文常用名或 CRS 三字母代码（`PAD`、`RDG`）。内置约 150 个常用车站，未收录的会再用 RTT 的车站列表补查。
- `London`、`Manchester`、`Birmingham` 等多站城市，工具会返回候选车站，**让模型追问用户**，不会擅自选择。
- 全部请求异步、带超时；任何失败（Token 错误、限流、断网）都以可读文字返回给模型，不会抛异常。
- 时区固定 `Europe/London`；相同查询默认缓存 60 秒。

## 注册 RTT 账号并获取 Token

1. 打开 <https://api-portal.rtt.io>，用 RTT 统一登录账号登录（没有就在 realtimetrains.co.uk 先注册一个）。
2. 在 API Portal 申请 Token。你拿到的可能是：
   - **长期 access token**：直接用；
   - **refresh token**：也可以直接填，插件遇到 401 会自动调用 `/api/get_access_token` 换取并缓存。
3. 默认只有 `gb-nr`（英国国铁）命名空间、无额外权限，足够本插件使用。

> 新版 API 限额很低（以 RTT 公告为准，2026-10 起为 **每分钟 10 次 / 每小时 100 次 / 每天 1000 次**）。
> 一次 `search_trains` 会消耗 1 次 + 为前 N 班车查到达时间的 N 次请求（默认 N=4）。
> 如果配额吃紧，把 `arrival_lookup_count` 调成 0，到达时间改由 `get_train_detail` 单独查。

## 安装与配置

1. 在 AstrBot WebUI 的插件市场用仓库地址安装，或：
   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/qualcone/astrbot_plugin_uk_trains
   ```
2. WebUI → 插件 → UK Trains → 配置：

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `rtt_token` | 空 | RTT API Token（必填） |
| `default_count` | 8 | 默认返回班次数（1–15） |
| `timeout` | 10 | 请求超时秒数 |
| `cache_ttl` | 60 | 相同查询缓存秒数 |
| `time_window_minutes` | 180 | 从出发时间起向后搜索的窗口（分钟） |
| `arrival_lookup_count` | 4 | 为前 N 班车额外查询到达时间，0 为不查 |

3. 确认当前对话所用的模型支持函数调用，并在 AstrBot 中开启了 LLM 工具调用。

## 关于票价

**读不到。** RTT 和 National Rail Darwin 都只提供时刻表与实时运行信息，不含票价，本插件也不会编造价格
（工具返回里会注明没有价格数据，模型被告知不要猜）。若要做票价，需要另接数据源（例如 Rail Delivery Group 的票价数据集，
需单独申请并自行解析），属于后续扩展。

## 已知限制

- 目前只实现 RTT；Darwin / Huxley2 备选源未做。
- 站名映射表不是全量；冷门车站依赖 RTT 的 `/data/stops` 接口回退。
- 作者开发时没有 RTT Token，字段结构按官方 OpenAPI 规范编写并用模拟数据做了离线测试
  （`python tests/test_offline.py`），**尚未用真实 Token 联调**；遇到字段对不上请提 issue。

## 致谢 / 许可

数据来自 [Realtime Trains](https://www.realtimetrains.co.uk)，请遵守其 API 使用条款（不要把 Token 放进可分发的客户端）。
本插件以 MIT 协议发布。
