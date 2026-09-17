# Render 免费试用部署

使用同一地区的两个 Free Docker Web Service 和一个 Free PostgreSQL：

## 当前试用实例（2026-09-08）

- 网站：<https://connact-ai.onrender.com>
- 后端：<https://connact-ai-api.onrender.com>；健康检查 `/api/health`。
- 地区：Singapore。前端、后端、PostgreSQL 均为 Free。
- 数据库：`connact-ai-db`，Render 显示到期日为 2026-10-08。
- 两个 Web Service 使用账号已连接的 GitHub `TYNBUM/Connact.ai`，跟踪 `main`，分别以 `frontend`、`backend` 为根目录自动部署。
- 已验证：网站 HTTP 200；后端和前端代理健康检查返回 PostgreSQL 正常；工作区需要登录；未登录访问配置返回 401，未允许的 Origin 返回 403。
- 提供商 API Key 尚待授权导入；不能视为 AI/查人端到端验收通过。

| 服务 | Root Directory | Dockerfile | 环境配置 |
| --- | --- | --- | --- |
| Connact.ai 前端 | `frontend` | `./Dockerfile` | `BACKEND_URL` 指向后端 HTTPS 地址，`PORT=10000` |
| Connact.ai 后端 | `backend` | `./Dockerfile` | 见下方列表 |
| PostgreSQL | 无 | 无 | Free，连接串仅保存在 Render 环境变量中 |

后端环境变量：

- `DATABASE_URL`：Render PostgreSQL 的内部连接串。应用自动将 `postgres://` / `postgresql://` 转为已安装的 `postgresql+psycopg://` 驱动。
- `AUTH_MODE=open`，`PUBLIC_ORIGIN` 必须为实际前端 HTTPS 地址。
- `PORT=10000`，`UPLOAD_DIR=/app/data/uploads`。Render 自带的 `RENDER_EXTERNAL_HOSTNAME` 自动加入后端 Host 白名单。
- `AI_MODE=live`、`PEOPLE_MODE=live`、`PUBLIC_SEARCH_MODE=live`。
- `AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、`AI_PROVIDER=bailian`、`AI_MODEL=qwen-plus`、`AI_MODELS=qwen-plus,qwen-turbo,qwen-max`。
- `AI_API_KEY`、`SERPAPI_API_KEY`、`APIFY_API_KEY`、可选 `APOLLO_API_KEY`，仅导入服务端 Environment，不能进入仓库或前端。

前端在未显式配置 `PUBLIC_ORIGIN` 时使用 Render 的 `RENDER_EXTERNAL_URL` 校验 Origin。
后端 Docker 启动时先迁移数据库，再创建管理员（若有配置），最后启动单 API 进程和后台 worker。

## 开放注册与管理员

`AUTH_MODE=open` 允许任意邮箱注册，不再校验邀请码或限制四人名额。注册成功即建立独立工作区。注册页告知用户管理员可查看其保存的信息和文件。

首次管理员通过 `BOOTSTRAP_ADMIN_PASSWORD_HASH` 配置：在本地产生 scrypt 密码哈希，仅把哈希写入 Render 后端 Environment。启动时创建保留账号 `admin` 和管理员角色；重启不重置已有密码。普通注册接口不能使用 `admin` 作为邮箱或自行取得管理员角色。管理员创建完成后可删除该初始化变量。

管理员后台：<https://connact-ai.onrender.com/admin>。支持账号搜索、分页、注册/最后登录时间、各类保存数据计数，逐项查看画像、历史版本、联系人、详细档案、来源、匹配、草稿、查人与写作任务及上传文件。文件可下载原件并查看保存的文本和解析结果。后台为只读；不展示密码哈希、会话令牌或提供商密钥。

部署不导入本地工作区数据。旧邀请码配置在开放注册模式下不再执行。

## 免费试用限制

Free Web Service 会在 15 分钟无流量后休眠，冷启动约需一分钟；两个 Web Service 共享工作区每月 750 小时额度。
新上传原件与联系人、草稿、解析结果一起存入 PostgreSQL，应用重启不会丢失数据库内的文件。旧版本已随临时磁盘丢失的原件无法恢复，后台会显示不可下载。所有数据和文件仍受免费数据库容量及到期时间约束。
Free PostgreSQL 30 天后到期，不能用于长期保存真实客户数据。模型与搜索提供商仍按各自用量计费。

## 冷启动时页面无法加载

若首页能显示，但登录卡片出现 `The string did not match the expected pattern.`（Safari）或 `Unexpected token '<' ... is not valid JSON`（Chrome），先检查 `/api/auth/session` 和 `/api/health` 的 HTTP 状态与 Content-Type。这类解析错误可能来自 Render 在后端启动期间返回的 HTML 错误页，不能直接判定为用户输入或网址格式错误。

2026-09-09 实测前端代理返回 HTTP 502、`text/html`，后端直连等待超时；Render 后端日志随后记录启动完成。恢复后，前端代理和后端直连的会话与健康检查均返回 HTTP 200 JSON，健康检查确认 PostgreSQL 正常，已有登录会话可重新进入工作区。

排查顺序：确认前端页面与静态资源可达 → 检查前端代理的会话和健康接口 → 检查后端 `/api/health` → 查看 Render 启动日志。不要只重启前端或清除用户账户数据。免费实例仍有休眠与冷启动延迟；客户端恢复逻辑不能保证服务器始终在线。

若在其他账号使用 Public Git Repository 方式连接，普通公开仓库部署不保证自动随 push 更新，需要从 Render 手动部署最新提交。当前实例使用已有 GitHub 连接。

参考：[Render 免费实例](https://render.com/docs/free)、[Docker 部署](https://render.com/docs/docker)、[默认环境变量](https://render.com/docs/environment-variables)。
