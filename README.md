# getxpos

[![PyPI](https://img.shields.io/pypi/v/getxpos)](https://pypi.org/project/getxpos/)
[![Python](https://img.shields.io/pypi/pyversions/getxpos)](https://pypi.org/project/getxpos/)
[![License](https://img.shields.io/pypi/l/getxpos)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/getxpos)](https://pypi.org/project/getxpos/)

Python SDK for [XPOS](https://xpos.dev) — instant public URLs via SSH tunnels. Zero dependencies.

## Features

- **Zero dependencies** — uses only Python standard library
- **CLI + programmatic API** — use from terminal or embed in your tooling
- **HTTP & TCP tunnels** — expose web apps or any TCP service
- **Anonymous or authenticated** — works instantly, tokens unlock more features
- **Reserved subdomains & custom domains** — with Pro/Business plans

## Quick Start

```bash
# Install and run
pip install getxpos
xpos --port 3000

# Or run without installing
pipx run getxpos --port 3000
```

## Installation

```bash
# Global (recommended for CLI usage)
pip install getxpos

# Or with pipx (isolated environment)
pipx install getxpos
```

## Authentication

Get a token from [xpos.dev/dashboard/tokens](https://xpos.dev/dashboard/tokens), then either:

```bash
# Pass directly
xpos --port 3000 --token tk_xxx

# Or set environment variable
export XPOS_TOKEN=tk_xxx
xpos --port 3000
```

## CLI Usage

```bash
# Anonymous tunnel (random subdomain, 3hr expiry)
xpos --port 3000

# Authenticated (random subdomain, 10hr expiry)
xpos --port 3000 --token tk_xxx

# Reserved subdomain (Pro+)
xpos --port 3000 --token tk_xxx --subdomain myapp

# Custom domain (Business)
xpos --port 8000 --token tk_xxx --domain tunnel.example.com

# Port-based TCP tunnel (Pro+)
xpos --port 5432 --token tk_xxx --mode tcp
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--port <port>` | Local port to expose | **(required)** |
| `--host <host>` | Local host to forward | `localhost` |
| `--token <token>` | Auth token (or `XPOS_TOKEN` env) | — |
| `--subdomain <name>` | Reserved subdomain (requires token) | — |
| `--domain <domain>` | Custom domain (requires token) | — |
| `--mode <mode>` | `http` or `tcp` | `http` |
| `--server <host>` | SSH server hostname | `go.xpos.dev` |
| `-h, --help` | Show help | — |
| `-v, --version` | Show version | — |

## Programmatic API

```python
from getxpos import xpos

# HTTP tunnel
tunnel = xpos.connect(port=3000, token="tk_xxx")
print(tunnel.url)         # https://abc.xpos.to
print(tunnel.expires_at)  # 2026-03-28T10:30:45Z
tunnel.close()

# Port-based TCP tunnel
tcp = xpos.connect(port=5432, token="tk_xxx", mode="tcp")
print(tcp.url)            # 1.2.3.4:54321
tcp.close()
```

### Named imports

```python
from getxpos import connect, XposTunnel

tunnel = connect(port=3000)
print(tunnel.url)
tunnel.close()
```

### Callbacks

```python
from getxpos import XposTunnel

tunnel = XposTunnel(
    port=3000,
    on_connect=lambda data: print(f"Connected: {data['url']}"),
    on_output=lambda text: print(text, end=""),  # Raw SSH output
    on_close=lambda code: print("Tunnel closed"),
)

tunnel.start()
```

### Options

| Option | Type | Description |
|--------|------|-------------|
| `port` | `int` | Local port to expose **(required)** |
| `host` | `str` | Local host (default: `"localhost"`) |
| `token` | `str` | Auth token (or reads `XPOS_TOKEN` env) |
| `subdomain` | `str` | Reserved subdomain |
| `domain` | `str` | Custom domain |
| `mode` | `str` | `"http"` or `"tcp"` (default: `"http"`) |
| `server` | `str` | SSH server (default: `"go.xpos.dev"`) |
| `on_connect` | `callable` | Called with `{"url", "expires_at"}` on connect |
| `on_output` | `callable` | Called with raw SSH output text |
| `on_close` | `callable` | Called with exit code on disconnect |

## Requirements

- **Python >= 3.8**
- **SSH client** in PATH (`ssh` command — comes pre-installed on macOS, Linux, and Windows 10+)

## Troubleshooting

**"SSH not found"** — Install OpenSSH. On Windows: `Settings > Apps > Optional Features > OpenSSH Client`.

**Connection timeout** — Check your firewall allows outbound connections on port 443.

**"subdomain requires a token"** — Reserved subdomains need a Pro plan. Get a token from your [dashboard](https://xpos.dev/dashboard/tokens).

## Links

- [Website](https://xpos.dev)
- [Dashboard](https://xpos.dev/dashboard)
- [GitHub](https://github.com/getxpos/python)

## License

[MIT](LICENSE)
