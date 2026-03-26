# Apple Calendar Multi-Account MCP

這個專案是 Linux 可部署版本的 Apple Calendar MCP，後端不是 macOS `EventKit`，而是 iCloud 的 CalDAV。

它的目標是沿用 `garmin_mcp/project` 的使用模式：

- 預先配置多個帳號
- 每次 tool 明確指定 `account_id`
- 用 secret file 管理 Apple ID 與 app-specific password
- 提供獨立帳號驗證 CLI
- 可選擇用標準 OIDC / OAuth 保護 MCP HTTP 入口
- 可先跑 `stdio`，也可切成遠端 HTTP / SSE

## 為什麼不是另外兩個 Apple MCP

你提供的另外兩個現成方案：

- `apple-calendar-mcp`
- `apple-events-mcp`

都直接依賴 macOS `EventKit` / Swift，因此只能在 Mac 上跑，不適合目前這台 Linux NAS。

這個專案改走：

- iCloud Calendar over CalDAV
- Apple ID + app-specific password

所以可以跑在 Linux，但能力模型會和 Mac 原生 Apple Calendar 略有差異。

## 目前提供的工具

- `list_accounts`
- `get_account_status`
- `list_calendars`
- `list_events`
- `create_event`
- `update_event`
- `delete_event`

每個 tool 都要求 `account_id`，避免操作到錯的 Apple ID。

若啟用 OAuth，tool 另外還會檢查：

- access token scopes
- authenticated principal 可使用的 `account_id`

## 專案結構

```text
project/
├── config/
│   └── accounts.example.yaml
├── src/
│   └── apple_calendar_multi_mcp/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## 安裝

在 `project/` 目錄中執行：

```bash
pip install -e .
```

## 建立帳號設定檔

先複製範例：

```bash
cp config/accounts.example.yaml config/accounts.yaml
```

範例：

```yaml
default_account_id: family

auth:
  mode: oauth_required
  issuer: https://your-project.customers.stytch.dev
  discovery_url: https://your-project.customers.stytch.dev/.well-known/oauth-authorization-server
  audience: project-live-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  resource_url: https://apple-mcp.example.com
  accounts_read_scope: accounts.read
  calendar_read_scope: calendar.read
  calendar_write_scope: calendar.write
  access_rules:
    - emails:
        - owner@example.com
      account_ids:
        - family
        - work
      default_account_id: family

accounts:
  - account_id: family
    label: Family iCloud
    apple_id_file: /run/secrets/icloud_family_apple_id
    app_password_file: /run/secrets/icloud_family_app_password
    default_calendar_name: AI
    readonly: false

  - account_id: work
    label: Work iCloud
    apple_id_file: /run/secrets/icloud_work_apple_id
    app_password_file: /run/secrets/icloud_work_app_password
    default_calendar_name: Calendar
    readonly: true
```

## 帳號欄位說明

- `account_id`: MCP 內使用的帳號代號
- `label`: 顯示名稱
- `apple_id` 或 `apple_id_file`: iCloud / Apple ID
- `app_password` 或 `app_password_file`: Apple app-specific password
- `default_calendar_name`: 預設寫入 calendar 名稱
- `default_calendar_url`: 若名稱不穩定，可改用 calendar URL 鎖定
- `readonly`: 若為 `true`，禁止 create / update / delete

建議優先使用 `*_file`，不要把多組 Apple 密碼直接寫進 YAML。

## OAuth / OIDC 設定

這個專案現在支援用標準 OIDC provider 保護 `MCP` HTTP 入口。

重點是：

- OAuth 保護的是 `apple-mcp.chengyi.homes/mcp`
- 不是拿來取代 iCloud CalDAV 登入
- upstream Apple 仍然使用 Apple ID + app-specific password

### `auth.mode`

- `disabled`: 不啟用 OAuth
- `mixed`: 允許匿名連線到 MCP，但 tools 會在需要時回 OAuth challenge
- `oauth_required`: 整個 `/mcp` 都要求 bearer token

### 建議 provider

- Stytch Connected Apps
- Keycloak
- Auth0
- Okta
- Cognito
- 任何支援 OIDC discovery、`registration_endpoint`、JWKS、PKCE、JWT access token 的標準 IdP

### `access_rules`

`access_rules` 決定登入後的 principal 可以用哪些 `account_id`。

可用條件：

- `subjects`
- `emails`
- `groups`

可授權結果：

- `account_ids`
- optional `default_account_id`

若 OAuth 啟用但沒有任何規則命中，該使用者即使登入成功也不能操作任何 Apple 帳號。

## 先準備 Apple app-specific password

每個 Apple ID 都需要自己的 app-specific password。

建立方式：

1. 前往 [account.apple.com](https://account.apple.com/)
2. 登入對應的 Apple ID
3. 建立 `App-Specific Password`
4. 把 Apple ID 與 app password 分別寫入 secret file

沒有 app-specific password，這個 MCP 無法在 Linux 上無互動登入 iCloud CalDAV。

## 驗證單一帳號

先測試指定帳號是否能登入並讀出 calendars：

```bash
apple-calendar-multi-mcp-auth --accounts-file config/accounts.yaml --account-id family
apple-calendar-multi-mcp-auth --accounts-file config/accounts.yaml --account-id work --json
```

這會驗證：

- Apple ID / app password 是否有效
- calendars 是否能讀出
- default calendar 是否可解析

## 啟動 MCP Server

### 本機 `stdio`

```bash
export APPLE_CALENDAR_ACCOUNTS_FILE=config/accounts.yaml
apple-calendar-multi-mcp
```

### 遠端 HTTP

```bash
export APPLE_CALENDAR_ACCOUNTS_FILE=config/accounts.yaml
export APPLE_CALENDAR_AUTH_MODE=oauth_required
export APPLE_CALENDAR_RESOURCE_URL=https://apple-mcp.example.com
export APPLE_CALENDAR_OIDC_ISSUER=https://your-project.customers.stytch.dev
export APPLE_CALENDAR_OIDC_DISCOVERY_URL=https://your-project.customers.stytch.dev/.well-known/oauth-authorization-server
export APPLE_CALENDAR_OIDC_AUDIENCE=project-live-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
export MCP_TRANSPORT=http
export MCP_HOST=0.0.0.0
export PORT=38082
export MCP_ALLOWED_HOSTS="127.0.0.1:*,localhost:*,calendar.example.com:*"
export MCP_ALLOWED_ORIGINS="https://chatgpt.com,https://chat.openai.com,https://calendar.example.com"
apple-calendar-multi-mcp
```

若 provider 使用 `Stytch Connected Apps`，`APPLE_CALENDAR_OIDC_AUDIENCE` 應填 `Stytch Project ID`，不是 `resource_url`。

預設遠端 MCP 入口：

```text
http://localhost:38082/mcp
```

### Docker Compose

先準備：

```bash
cp config/accounts.example.yaml config/accounts.yaml
docker compose up --build -d
```

## ChatGPT 前端 OAuth 體驗

如果你在 ChatGPT Apps / Connectors 裡選 `OAuth`：

1. 使用者第一次觸發受保護工具時，ChatGPT 會顯示 `Connect / Sign in`
2. ChatGPT 會導向你設定的 OIDC provider 登入頁
3. 完成登入與授權後，ChatGPT 取得 access token
4. 後續呼叫 MCP tools 時會帶 bearer token
5. 若 token 過期、scope 不足、或 server 回 `401` challenge，ChatGPT 會重新要求授權

若 `auth.mode = oauth_required`：

- 整個 `/mcp` 一開始就要求 bearer token

## ChatGPT / OIDC Provider 必備設定

在 OIDC provider 端，至少需要 allowlist 這些 redirect URIs：

- `https://chatgpt.com/connector/oauth/{callback_id}`
- `https://platform.openai.com/apps-manage/oauth`

另外 provider 需支援：

- OIDC discovery
- `registration_endpoint`
- JWKS
- PKCE `S256`
- access token audience 驗證

你的 MCP server 會自動提供：

- `/.well-known/oauth-protected-resource`

## Tool 行為重點

### `list_events`

- 預設查未來 7 天
- 可指定 `days_back`
- 可指定 `calendar_name` 或 `calendar_url`
- 可用 `search` 對 summary / location / description 做簡單搜尋

### `create_event`

- 可指定 `calendar_name` 或 `calendar_url`
- 若未指定，會寫入帳號的 default calendar

### `update_event` / `delete_event`

- 目前以 VEVENT `UID` 作為目標識別
- 服務層會在 calendar 中搜尋對應事件後再執行更新或刪除

## 環境變數

- `APPLE_CALENDAR_ACCOUNTS_FILE`
- `APPLE_CALENDAR_DEFAULT_ACCOUNT_ID`
- `APPLE_CALENDAR_CALDAV_URL`
- `APPLE_CALENDAR_AUTH_MODE`
- `APPLE_CALENDAR_RESOURCE_URL`
- `APPLE_CALENDAR_OIDC_ISSUER`
- `APPLE_CALENDAR_OIDC_DISCOVERY_URL`
- `APPLE_CALENDAR_OIDC_JWKS_URL`
- `APPLE_CALENDAR_OIDC_AUDIENCE`
- `APPLE_CALENDAR_OIDC_ACCOUNTS_READ_SCOPE`
- `APPLE_CALENDAR_OIDC_CALENDAR_READ_SCOPE`
- `APPLE_CALENDAR_OIDC_CALENDAR_WRITE_SCOPE`
- `MCP_TRANSPORT`
- `MCP_HOST`
- `PORT`
- `MCP_PATH`
- `MCP_ALLOWED_HOSTS`
- `MCP_ALLOWED_ORIGINS`

## 限制與風險

- 這不是 macOS 原生 `EventKit`，而是 CalDAV，所以能力與行為不會完全相同
- recurrence、all-day event、timezone 行為取決於 CalDAV / ICS 表示方式
- `update_event` / `delete_event` 目前依賴 VEVENT `UID` 搜尋；若 iCloud 資料量很大，搜尋成本會較高
- app-specific password 若失效，該帳號會無法登入
- `readonly: true` 的帳號會被硬性禁止寫入
- 啟用 OAuth 後，仍需正確設定 `access_rules`，否則登入成功也可能沒有任何帳號可用
- MCP OAuth 最敏感的是 discovery、JWKS、scope、`WWW-Authenticate` challenge 與 resource URL 對齊

## 建議使用方式

- 先呼叫 `list_accounts`
- 再用 `get_account_status` 確認 default calendar 與 credential 正常
- 寫入前先 `list_calendars`
- `list_events` 取得 event 的 `uid` 後，再執行 `update_event` / `delete_event`
