# astrbot_plugin_uk_trains

英国火车查询插件 for [AstrBot](https://github.com/AstrBotDevs/AstrBot)。作者：qualcone

用户直接用自然语言提问，大模型通过函数调用自动查询，无需记忆任何指令：

- 「明天早上 8 点之后曼彻斯特 Piccadilly 到伦敦 Euston 的车」
- 「现在从 Reading 到 Paddington 的下一班几点？晚点吗？」

## 功能（LLM 工具）

| 工具 | 作用 |
| --- | --- |
| `search_trains(origin, destination, travel_date?, travel_time?)` | 查两站之间的直达班次：计划/预计发车时间、到达时间、站台、运营公司、晚点/取消及原因 |
| `get_train_detail(train_id, travel_date?)` | 查单趟列车的停靠站、各站站台、实际/预计时间与晚点原因（`train_id` 取自 `search_trains` 返回的 `ref`） |

- 站名支持城市/车站名、常用中文名和 CRS 三字母代码（如 `PAD`、`RDG`）。内置约 150 个常用车站，未收录的站点回退到 RTT 车站列表查询。
- 多站城市（London、Manchester、Birmingham 等）返回候选车站，由模型向用户确认，不会擅自选择。
- 所有请求异步并带超时；认证失败、限流、网络异常均以可读文字返回，不抛出异常。
- 时区固定为 `Europe/London`，相同查询默认缓存 60 秒。

## 数据源

[Realtime Trains](https://www.realtimetrains.co.uk) 新版 API（`https://data.rtt.io`，Bearer Token 认证）。

## 获取 Token

1. 访问 <https://api-portal.rtt.io>，使用 RTT 账号登录（未注册请先在 realtimetrains.co.uk 注册）。
2. 申请 API Token。长期 access token 与 refresh token 均可，插件会在需要时自动换取并缓存 access token。
3. 默认授权的 `gb-nr`（英国国铁）命名空间即可满足本插件需求。

## 安装与配置

```bash
cd AstrBot/data/plugins
git clone https://github.com/qualcone/astrbot_plugin_uk_trains
```

也可在 AstrBot WebUI 的插件管理中通过仓库地址安装。安装后在 WebUI 的插件配置中填写：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `rtt_token` | 空 | RTT API Token（必填） |
| `default_count` | 8 | 默认返回班次数（1–15） |
| `timeout` | 10 | 请求超时（秒） |
| `cache_ttl` | 60 | 相同查询的缓存时间（秒） |
| `time_window_minutes` | 180 | 自指定出发时间起向后搜索的窗口（分钟） |
| `arrival_lookup_count` | 4 | 为前 N 班车查询到达时间（每班 1 次 API 请求，0 表示不查） |

请确保所用模型支持函数调用，并已在 AstrBot 中启用 LLM 工具调用。

## 开发

```bash
python tests/test_offline.py   # 使用模拟数据的离线测试
```

## 许可

MIT。数据版权归 Realtime Trains 所有，使用时请遵守其 API 条款。
