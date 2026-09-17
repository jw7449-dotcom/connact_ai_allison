# 创建 Google 登录 Client ID 和 Client Secret

这两项是 **OAuth 客户端凭据**，不是普通 Google API Key。本项目已在 2026-09-09 完成本地配置与真实 Google 登录验证；下面保留新环境的创建与配置步骤。

## 1. 新建开发项目

打开 [Google Auth Platform](https://console.cloud.google.com/auth/overview)，在顶部选择项目或新建 **Connact.ai Development**。第一次使用时点击 **Get started**。

- App name：`Connact.ai`
- User support email：选择你的邮箱
- Audience：`External`
- Contact information：填写能收到通知的邮箱

完成创建，开发项目保持 **Testing**。本项目只使用基本登录权限；Google 对这种情况不强制要求加入测试用户，也不适用通常的 7 天授权到期规则。

## 2. 设置基本登录权限

进入 **Data Access → Add or Remove Scopes**，只选择：

```text
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
```

这些权限用于获得 Google 身份、已验证邮箱和基本个人资料，不包含 Gmail 读信或发信。

## 3. 创建 Web application 客户端

进入 **Clients → Create client**：

| 配置项 | 本地开发填写内容 |
| --- | --- |
| Application type | Web application |
| Name | Connact.ai Local Web |
| Authorized JavaScript origins | 可以留空，本项目使用服务端授权码流程 |
| Authorized redirect URIs | `http://127.0.0.1:3100/api/auth/google/callback` |

回调使用前端 **3100** 端口，不是后端 8000。创建后，浏览器也使用 `http://127.0.0.1:3100` 打开项目。

如果偏好 `localhost`，则注册 `http://localhost:3100/api/auth/google/callback`，并把项目的 `PUBLIC_ORIGIN` 改为 `http://localhost:3100`。登录入口、环境变量和回调中的域名必须一致。

Docker Compose 会向前后端传入相同的 `PUBLIC_ORIGIN`。使用另一个本地域名访问同端口的页面时，会在登录前自动跳转到配置的域名，让 OAuth 状态 Cookie 和回调使用同一域名。前端若不通过 Compose 启动，也应在其环境变量中设置相同的 `PUBLIC_ORIGIN`（默认值为 `http://127.0.0.1:3100`）。API 的来源校验仍保持严格。

## 4. 保存凭据

点击 **Create** 后保存 **Client ID** 和 **Client secret**，若有 **Download JSON** 就当场下载。Client ID 通常以 `.apps.googleusercontent.com` 结尾。

Google 现在只在创建时显示和提供下载完整 secret；如果以后找不到，可以为该客户端创建新 secret，不必删除整个客户端。把 JSON 放在项目仓库外，不要把 secret 贴到聊天里或提交到 Git。配置时可以仅告知凭据文件的本地路径。

## 5. 配置项目并验证

在项目根目录的私有 `.env` 中配置真实值：

```dotenv
AUTH_MODE=open
AUTH_PROVIDER=google
PUBLIC_ORIGIN=http://127.0.0.1:3100
GOOGLE_CLIENT_ID=替换为真实ClientID
GOOGLE_CLIENT_SECRET=替换为真实ClientSecret
```

安装后端依赖、执行数据库迁移并重启前后端，可使用项目现有的 `./scripts/dev.sh`。打开配置的前端地址，点击 **Continue with Google / 使用 Google 登录**。登录后退出再登录，应回到同一个工作区。

`AUTH_MODE=local` 会直接进入私人开发工作区，跳过登录；测试 Google 登录时要改成 `open`。不能仅配置 ID/secret 而继续使用 `local`。

## 线上 Render 配置

正式上线另建生产 Google 项目和 Web 客户端。现有前端域名对应的回调地址是：

```text
https://connact-ai.onrender.com/api/auth/google/callback
```

在 **Render 后端服务**中设置 OAuth 凭据、`AUTH_PROVIDER=google`、`AUTH_MODE=open`、`PUBLIC_ORIGIN=https://connact-ai.onrender.com`，前端的 `PUBLIC_ORIGIN` 也保持一致。不要把 secret 配置到前端服务。生产项目按 Google 的 Audience 发布和品牌验证要求完成真实首页、隐私政策等配置，不加入 localhost 回调。

公开介绍页位于 `/about`，隐私政策位于 `/privacy`，均无需登录。在 Render **前端**设置 `PUBLIC_SUPPORT_EMAIL` 为确认公开的支持邮箱。网站验证文件放在 `frontend/public/` 中，验证后也应保留。

保留管理员的切换顺序：先部署 `e318ca421010` 迁移并配置生产 OAuth 凭据，暂时保留 `AUTH_PROVIDER=password`。用原 `admin` 登录，打开 `/admin`，在“管理员 Google 登录”中填写确认的 Google 邮箱并完成真实 Google 验证。页面及服务端确认已绑定后，再改为 `AUTH_PROVIDER=google` 并部署；退出后重新使用 Google 登录，核对原工作区和管理员权限。

绑定会保留原管理员的用户名 `admin`、用户 ID、工作区、数据和角色，不创建第二个管理员。回调同时核验 Google 身份、选定邮箱以及发起时管理员会话仍然有效，拒绝与已有账号或身份冲突的绑定，并撤销旧管理员会话。普通 Google 注册不会自动取得管理权限。已有普通账号会按经过验证的 Google 身份关联原工作区；部分使用第三方邮箱的旧账号需要先建立旧账号会话再绑定。

2026-09-09 已将 `Connact.ai Local Web` 凭据写入本地私有 `.env`，启用 Google 登录，重建前后端 Docker 容器，并把数据库迁移到 `d247ab731009`。Chrome 已完成真实 Google 登录并进入独立工作区。原 `local-personal` 工作区及其中的一份草稿保留；新 Google 账号使用独立工作区，没有管理员权限。这次完成的是本地启用，尚未把 Google 登录配置部署到 Render。

详细实现与迁移说明见 [English setup guide](google-sign-in.md)。官方参考：[初始配置](https://developers.google.com/workspace/guides/configure-oauth-consent)、[客户端与 secret 管理](https://support.google.com/cloud/answer/15549257?hl=en)、[Audience 规则](https://support.google.com/cloud/answer/15549945?hl=en)、[生产准备](https://developers.google.com/identity/verification/authentication-policy-compliance)。
