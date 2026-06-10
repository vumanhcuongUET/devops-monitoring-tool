# DevOps AI Monitoring Assistant

Config-driven monitoring assistant for Claude CLI. Ask natural language questions about system status — Claude queries ELK, Prometheus, and APM automatically using Python scripts.

---

## Project structure

```
devops_ai_assistant/
├── CLAUDE.md                        # AI spec — Claude reads this first
├── requirements.txt                 # Python dependencies
├── config/
│   └── global.yaml                  # Default endpoints & settings
├── templates/
│   └── system-status.yaml           # Report sections & display order
├── queries/
│   └── common/
│       ├── alerts.yaml              # Machine-readable query definition
│       ├── alerts.md                # Human-readable docs + display format
│       ├── errors.yaml / .md
│       ├── slow_endpoints.yaml / .md
│       ├── disk_usage.yaml / .md
│       └── pod_status.yaml / .md
├── tools/
│   ├── run_query.py                 # Cross-platform Python query executor
│   └── http-client.md               # Tool usage docs
└── projects/
    ├── _template/                   # Copy this for a new project
    │   └── config.yaml
    └── meinvoice/
        ├── config.yaml
        └── queries/
            └── errors.yaml          # Project-specific query override
```

---

## Prerequisites

- **Python 3.9+**
- **Node.js 18+** (required by Claude CLI)
- Network access to ELK / Prometheus endpoints
- **API key** from CSO/SRE Team

---

## Setup

### 1. Install Claude CLI

**Linux / macOS:**
```bash
npm install -g @anthropic-ai/claude-code
```

**Windows (PowerShell as Administrator):**
```powershell
npm install -g @anthropic-ai/claude-code
```

Verify:
```bash
claude --version
```

### 2. Configure the API key

Get your key from the **CSO/SRE Team** (shared via team password manager).

**Linux / macOS** — add to `~/.bashrc` or `~/.zshrc`:
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

**Windows PowerShell** — add to your profile (`$PROFILE`):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
```

Or set via Claude CLI (stored in `~/.claude/config.json`):
```bash
claude config set apiKey sk-ant-api03-...
```

> **Note:** Do not commit the API key to git. It is personal and tied to your CSO/SRE account.

### 3. Install Python dependencies

```bash
cd devops_ai_assistant
pip install -r requirements.txt
```

> On some systems use `pip3` or `python -m pip`.

### 4. Configure monitoring credentials

Credentials are passed as environment variables (never stored in config files).

Credentials are provided by the **SRE Team** alongside the API key.

| Env var | Dùng cho |
|---|---|
| `ELK_AUTH` | ELK / Elasticsearch (tất cả index) |
| `ELK_PROJECT_AUTH` | ELK riêng của project (nếu có) |
| `PROM_AUTH` | Tất cả Prometheus sub-servers (dùng chung 1 credential) |

> Nếu các sub-server Prometheus có credential khác nhau, tạo thêm biến riêng (vd `PROM_K8S_AUTH`) và cập nhật `auth_env` trong `config/global.yaml`.

**Linux / macOS** — thêm vào `~/.bashrc` hoặc `~/.zshrc`:
```bash
export ELK_AUTH=$(echo -n "elastic:your-elk-password" | base64)
export PROM_AUTH=$(echo -n "admin:your-prometheus-password" | base64)

# Optional: per-project ELK
export ELK_PROJECT_AUTH=$(echo -n "project_user:password" | base64)
```

**Windows PowerShell** — thêm vào `$PROFILE`:
```powershell
$env:ELK_AUTH = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes("elastic:your-elk-password"))
$env:PROM_AUTH = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes("admin:your-prometheus-password"))
```

### 5. (Optional) Verify Python tool works

```bash
# Should print JSON with "unreachable" status since this is test endpoints
python tools/run_query.py --project meinvoice --section errors --output pretty
```

---

## Running the assistant

```bash
cd devops_ai_assistant
claude
```

Example questions:
```
Tình trạng hệ thống meinvoice
Tình trạng hệ thống meinvoice 30 phút qua
Show active alerts for meinvoice
Top slow endpoints meinvoice
Disk usage trên các server meinvoice
```

---

## Add a new project

1. Copy the template folder:
   ```bash
   cp -r projects/_template projects/your-project
   ```

2. Edit `projects/your-project/config.yaml`:
   - Set `project`, `namespace`, `node_job`
   - Configure source arrays (`elk_error`, `elk_apm`, etc.)
   - Set `project_filter` to scope ELK queries (e.g. `{"term": {"app.keyword": "your-project"}}`)

3. (Optional) Add project-specific query overrides:
   ```
   projects/your-project/queries/errors.yaml
   ```

4. Ask Claude: `"Tình trạng hệ thống your-project"`

---

## Query override logic

For each section, `run_query.py` resolves the query definition in this order:

```
projects/<project>/queries/<section>.yaml   ← project override (wins if exists)
queries/common/<section>.yaml               ← global fallback
```

## Source merging

In project `config.yaml`, each source type supports:

```yaml
sources:
  elk_error:
    inherit: true   # true = add to global sources, false = replace global
    extra:
      - name: My-Extra-ELK
        url: "http://..."
        index: "my-index-*"
        auth_env: ELK_AUTH
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ANTHROPIC_API_KEY not set` | Export the env var or run `claude config set apiKey ...` |
| `Missing dependency: requests` | Run `pip install -r requirements.txt` |
| All sources `unreachable` | Check VPN / network access to ELK/Prometheus; verify `url` in `config/global.yaml` |
| `http_401` from ELK/Prometheus | Check credential env vars (`ELK_AUTH`, `PROM_AUTH`) are set and correct |
| `template_error` | Query YAML body has a syntax issue — check `queries/common/<section>.yaml` |
| Project not found | Ensure `projects/<name>/config.yaml` exists |
