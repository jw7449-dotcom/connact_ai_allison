# 多厂商 AI 模型配置

写作页按 **API 服务平台** 分组，模型作者单独体现在模型名称中。
同一个百炼 MaaS Key 可以调用平台托管的多个国产模型，不需要分别申请 DeepSeek、Kimi、GLM 或 MiniMax 的原厂 Key。
每次请求只发往所选服务平台；不会在失败时换平台或退回 Mock。

| API 服务平台 | 密钥变量 | 预置模型 ID 示例 |
| --- | --- | --- |
| 百炼 MaaS / 千问AI平台 | `DASHSCOPE_API_KEY`，或复用已有百炼 `AI_API_KEY` | `bailian/qwen3.8-flash`、`bailian/deepseek-v4-flash`、`bailian/kimi-k3`、`bailian/glm-5.2`、`bailian/MiniMax-M2.5` |
默认列表只保留百炼多厂商模型，以及已有 `qwen-plus`、`qwen-turbo`、`qwen-max`。
之前添加的 OpenAI、DeepSeek 原厂、Google Gemini、Anthropic Claude 和重复的 Qwen 直连预设已移除。
如以后需要其他平台，可以显式通过 `AI_PROVIDERS` 添加，不会自动出现在默认列表中。

已有 `AI_BASE_URL` 与百炼预设完全相同且属于受信任的官方百炼地址时，才会自动复用 `AI_API_KEY`。
仅将厂商名称写成 bailian，或者配置一个名字相似的域名，不会触发密钥复用。

预置列表是可修改的接入示例，不是账户权限或调用成功的承诺。可用模型以各厂商账户为准。
Live 模式下缺少密钥的选项显示「未配置」并禁用；已有草稿仍可保存。
Mock 模式下所有选项仅生成模拟内容，页面会明确提示。

## 启用与默认模型

在项目根目录 `.env` 中设置所需厂商的密钥，保持只在服务端保存。例如使用现有百炼密钥时：

```dotenv
AI_MODE=live
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_API_KEY=填写你已有的百炼密钥
AI_DEFAULT_MODEL=bailian/deepseek-v4-flash
```

重启后端使环境配置生效。本地用 `./scripts/dev.sh` 启动的服务可停止后重新运行；
Docker 使用 `docker compose up -d --force-recreate backend`。
刷新写作页，选择已配置的模型并生成一次邮件，确认任务成功及结果内容。
`GET /api/ai/models` 仅返回模型名称、厂商、默认项和配置/可用状态，不返回密钥或端点。
`configured` 只表示密钥存在，尚不等于账户权限、余额或网络已验证。

默认模型为空时沿用 `AI_MODEL`。旧的 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`
继续服务原有无前缀的模型 ID，例如 `qwen-plus`；不需要迁移旧草稿。
新增百炼选项优先使用 `DASHSCOPE_API_KEY`，未设置时按上述规则复用现有百炼 Key。
画像解析和匹配建议沿用工作区默认模型；写作任务可以单独选择模型。

## 自定义模型、国内厂商与网关

`AI_PROVIDERS` 是 JSON 数组。同 ID 覆盖该厂商预设，不同 ID 增加一个厂商。
修改预置厂商模型时，可使用已有的密钥变量；新增变量需要通过服务进程环境传入
（例如 shell `export`、Docker `env_file` 或部署平台的 secrets 配置）。
自定义变量仅写进本地 `.env` 不会自动成为 shell 环境；内置五个密钥变量由应用直接读取。

```dotenv
AI_PROVIDERS='[{"id":"gateway","label":"自定义模型服务","base_url":"https://your-gateway.example/v1","api_key_env":"CUSTOM_AI_KEY","models":["vendor/model-a","vendor/model-b"],"protocol":"compatible","token_parameter":"max_tokens","json_mode":true}]'
AI_DEFAULT_MODEL=gateway/vendor/model-a
```

`base_url` 填 `/chat/completions` 之前的地址；`models` 填服务商接受的实际 ID，
支持模型 ID 本身包含 `/`。实际请求只发送 `vendor/model-a`，不发送 `gateway/` 前缀。
支持提供 Chat Completions 兼容接口的其他厂商、聚合网关和本地服务。
需要无认证的本地兼容服务时，可给对应密钥环境变量设置非空占位值。

`protocol` 支持 `compatible` 和 `anthropic`。后者调用 `/messages`，使用独立的
`system` 字段、`x-api-key` 与 `anthropic-version` 请求头。
`token_parameter` 可为 `max_tokens` 或 `max_completion_tokens`；兼容接口不支持
JSON mode 时设置 `json_mode:false`。所有响应仍须通过服务端 JSON 和写作结果校验。
`thinking_mode` 默认 `auto`：仅对已验证支持关闭思考的百炼模型关闭思考；MiniMax 等强制思考模型保留服务默认值。
可用 `enabled` / `disabled` 显式设置百炼的 `enable_thinking`，或 `default` 完全不传该字段。
服务不自动重试其他厂商，避免意外重复计费和改变数据接收方。

## 官方接口参考与验证边界

- [百炼 OpenAI 兼容 Chat API：支持的多厂商模型与第三方开通要求](https://platform.qianwenai.com/docs/api-reference/chat/openai-chat)
- [OpenAI Chat API](https://developers.openai.com/api/reference/resources/chat)
- [DeepSeek API](https://api-docs.deepseek.com/)
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Anthropic Messages](https://platform.claude.com/docs/en/api/overview)

本次通过模拟 HTTP transport 验证路由、独立鉴权、厂商参数、Claude 响应解析、
配置状态、缺密钥拦截、任务模型持久化与浏览器选择流程。
2026-09-08 使用项目已有百炼 Key 完成真实验证：`GET /models` 返回 HTTP 200、249 个条目；
Qwen3.8-Flash、DeepSeek V4 Flash、Kimi K3、GLM 5.2、MiniMax-M2.5 均成功返回有效 JSON。
随后通过应用实际 `CompatibleAI.complete` 写作路径验证：DeepSeek、Kimi、GLM、MiniMax 均返回包含 `subject` 和 `body_html` 的有效邮件 JSON。
MiniMax 首次因 `enable_thinking:false` 返回 400，去除此字段后成功，代码已修正并加入回归测试。
模型列表包含图像、音视频和可能需要单独开通的第三方服务，不能将 249 个目录条目视为全部已开通或适用于邮件写作。
本次没有创建/重置密钥、开通第三方服务或更改套餐。OpenAI/DeepSeek 原厂、Google、Anthropic 直连仍只通过模拟 HTTP 合约测试。
