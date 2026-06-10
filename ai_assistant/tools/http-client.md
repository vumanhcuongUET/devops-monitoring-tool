# Tool: Python Query Runner

All monitoring queries are executed via `tools/run_query.py` — a cross-platform Python script that handles ELK and Prometheus HTTP requests.

## Usage

```
python tools/run_query.py --project <project> --section <section> [--time-range <range>] [--output pretty|json]
```

### Arguments

| Argument | Required | Example |
|---|---|---|
| `--project` | yes | `meinvoice` |
| `--section` | yes | `errors`, `alerts`, `slow_endpoints`, `disk_usage`, `pod_status` |
| `--time-range` | no | `now-30m`, `now-1h`, `now-2h` |
| `--output` | no | `pretty` (default) or `json` |

### Examples

```bash
python tools/run_query.py --project meinvoice --section errors
python tools/run_query.py --project meinvoice --section alerts --time-range now-30m
python tools/run_query.py --project meinvoice --section slow_endpoints --output pretty
```

## Return format

```json
{
  "section": "errors",
  "results": [
    {
      "status": "ok",
      "source": "ELK-Main",
      "data": { ... raw API response ... }
    },
    {
      "status": "unreachable",
      "source": "ELK-MeInvoice-App",
      "data": null
    }
  ]
}
```

### Status values

| Status | Meaning |
|---|---|
| `ok` | Request succeeded — `data` contains API response |
| `unreachable` | Connection refused or DNS failure |
| `timeout` | No response within `timeout_seconds` |
| `http_<code>` | HTTP error (e.g. `http_401`, `http_503`) |
| `template_error` | Query YAML body template has invalid JSON after render |

## Auth resolution

The script reads credentials from environment variables specified in source config (`auth_env` field):

```bash
# Linux / macOS
export ELK_AUTH=$(echo -n "elastic:password" | base64)
export PROM_AUTH=$(echo -n "admin:password" | base64)

# Windows PowerShell
$env:ELK_AUTH = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("elastic:password"))
$env:PROM_AUTH = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("admin:password"))
```

If an env var is unset, the request is made without auth (for internal unauthenticated endpoints).

## Dependencies

```
pip install -r requirements.txt
```

Requires: `requests>=2.31.0`, `pyyaml>=6.0.1`
