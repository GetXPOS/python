import argparse
import os
import signal
import sys
import time

from .tunnel import XposTunnel
from .utils import resolve_token, format_expiry, should_filter_line, parse_error


def _get_version():
    try:
        from importlib.metadata import version
        return version("getxpos")
    except Exception:
        return "0.1.0"


# ── Color helpers ──────────────────────────────────────────────────────

def _setup_colors():
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    no_color = os.environ.get("NO_COLOR")
    use_color = is_tty and not no_color

    # Enable VT100 escape codes on Windows 10+
    if use_color and sys.platform == "win32":
        os.system("")

    if use_color:
        return {
            "cyan": lambda s: "\x1b[36m{}\x1b[0m".format(s),
            "green": lambda s: "\x1b[32m{}\x1b[0m".format(s),
            "yellow": lambda s: "\x1b[33m{}\x1b[0m".format(s),
            "red": lambda s: "\x1b[31m{}\x1b[0m".format(s),
            "gray": lambda s: "\x1b[90m{}\x1b[0m".format(s),
            "bold": lambda s: "\x1b[1m{}\x1b[0m".format(s),
        }
    else:
        noop = lambda s: s
        return {
            "cyan": noop, "green": noop, "yellow": noop,
            "red": noop, "gray": noop, "bold": noop,
        }


# ── Display helpers ────────────────────────────────────────────────────

def _show_help(c, version):
    print("""
  {title} {ver}
  {desc}

  {usage}
    {xpos} --port <port> [options]
    {pip} --port <port> [options]

  {options}
    --port <port>        Local port to expose {req}
    --host <host>        Local host {def_host}
    --token <token>      Auth token {def_token}
    --subdomain <name>   Reserved subdomain {def_sub}
    --domain <domain>    Custom domain {def_dom}
    --mode <mode>        Tunnel mode: http or tcp {def_mode}
    --server <host>      SSH server {def_srv}
    -h, --help           Show this help
    -v, --version        Show version

  {examples}
    {c_anon}
    {xpos} --port 3000

    {c_auth}
    {xpos} --port 3000 --token tk_xxx --subdomain myapp

    {c_tcp}
    {xpos} --port 5432 --token tk_xxx --mode tcp

    {c_dom}
    {xpos} --port 8000 --token tk_xxx --domain tunnel.example.com

  {link}
""".format(
        title=c["cyan"]("XPOS Tunnel"),
        ver=c["gray"]("v" + version),
        desc=c["gray"]("Instant public URLs via SSH tunnels"),
        usage=c["bold"]("USAGE"),
        xpos=c["green"]("xpos"),
        pip=c["green"]("python -m getxpos"),
        options=c["bold"]("OPTIONS"),
        req=c["red"]("(required)"),
        def_host=c["gray"]("(default: localhost)"),
        def_token=c["gray"]("(or set XPOS_TOKEN env)"),
        def_sub=c["gray"]("(Pro+, requires token)"),
        def_dom=c["gray"]("(Business, requires token)"),
        def_mode=c["gray"]("(default: http)"),
        def_srv=c["gray"]("(default: go.xpos.dev)"),
        examples=c["bold"]("EXAMPLES"),
        c_anon=c["gray"]("# Anonymous tunnel"),
        c_auth=c["gray"]("# Authenticated with reserved subdomain"),
        c_tcp=c["gray"]("# Port-based TCP tunnel (Pro+)"),
        c_dom=c["gray"]("# Custom domain (Business)"),
        link=c["gray"]("https://xpos.dev"),
    ))


def _display_banner(c, opts):
    token = resolve_token(opts.get("token"))
    mode = "Authenticated" if token else "Anonymous"

    print()
    print("  " + c["cyan"]("XPOS Tunnel"))
    print("  " + c["gray"]("\u2500" * 41))
    print("  {}       {}".format(c["gray"]("Mode:"), mode))

    if opts.get("subdomain"):
        print("  {}  {}".format(c["gray"]("Subdomain:"), opts["subdomain"]))
    elif opts.get("domain"):
        print("  {}     {}".format(c["gray"]("Domain:"), opts["domain"]))

    if opts.get("mode") == "tcp":
        print("  {}       TCP".format(c["gray"]("Type:")))

    print()
    print("  " + c["gray"]("Creating tunnel to XPOS..."))
    print()


def _display_url(c, url, expires_at):
    inner = "   {}   ".format(url)
    width = max(len(inner), 40)
    padded = inner.ljust(width)

    print("  " + c["green"]("\u250c" + "\u2500" * width + "\u2510"))
    print("  " + c["green"]("\u2502") + c["bold"](padded) + c["green"]("\u2502"))
    print("  " + c["green"]("\u2514" + "\u2500" * width + "\u2518"))
    print()

    if expires_at:
        print("  " + c["yellow"](format_expiry(expires_at)))

    print("  " + c["gray"]("Tunnel active. Press Ctrl+C to stop."))
    print()


# ── Arg parsing ────────────────────────────────────────────────────────

def _parse_args(argv):
    args = {}
    raw = argv[1:]
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg in ("--help", "-h"):
            args["help"] = True
        elif arg in ("--version", "-v"):
            args["version"] = True
        elif arg.startswith("--"):
            eq_index = arg.find("=")
            if eq_index != -1:
                key = arg[2:eq_index]
                args[key] = arg[eq_index + 1:]
            else:
                key = arg[2:]
                if i + 1 < len(raw) and not raw[i + 1].startswith("--"):
                    args[key] = raw[i + 1]
                    i += 1
                else:
                    args[key] = True
        i += 1
    return args


# ── Main ───────────────────────────────────────────────────────────────

def main():
    c = _setup_colors()
    version = _get_version()
    args = _parse_args(sys.argv)

    if args.get("version"):
        print(version)
        sys.exit(0)

    if args.get("help"):
        _show_help(c, version)
        sys.exit(0)

    # Validate
    port_str = args.get("port")
    if port_str is None or port_str is True:
        print("\n  {} --port is required (1-65535)\n".format(c["red"]("Error:")),
              file=sys.stderr)
        print("  {} xpos --port 3000\n".format(c["gray"]("Usage:")),
              file=sys.stderr)
        sys.exit(1)

    try:
        port = int(port_str)
    except (ValueError, TypeError):
        port = 0

    if port < 1 or port > 65535:
        print("\n  {} --port is required (1-65535)\n".format(c["red"]("Error:")),
              file=sys.stderr)
        print("  {} xpos --port 3000\n".format(c["gray"]("Usage:")),
              file=sys.stderr)
        sys.exit(1)

    subdomain = args.get("subdomain")
    domain = args.get("domain")

    if subdomain and domain:
        print("\n  {} --subdomain and --domain are mutually exclusive\n".format(
            c["red"]("Error:")), file=sys.stderr)
        sys.exit(1)

    token = resolve_token(args.get("token") if args.get("token") is not True else None)

    if (subdomain or domain) and not token:
        flag = "subdomain" if subdomain else "domain"
        print("\n  {} --{} requires a token\n".format(c["red"]("Error:"), flag),
              file=sys.stderr)
        print("  {} --token tk_xxx {} XPOS_TOKEN=tk_xxx\n".format(
            c["gray"]("Set via:"), c["gray"]("or")), file=sys.stderr)
        sys.exit(1)

    mode = args.get("mode", "http")
    if mode is True:
        mode = "http"
    if mode not in ("http", "tcp"):
        print('\n  {} --mode must be "http" or "tcp"\n'.format(c["red"]("Error:")),
              file=sys.stderr)
        sys.exit(1)

    # Display banner
    _display_banner(c, {
        "token": args.get("token") if args.get("token") is not True else None,
        "subdomain": subdomain,
        "domain": domain,
        "mode": mode,
    })

    # Create tunnel
    tunnel = XposTunnel(
        port=port,
        host=args.get("host") if args.get("host") not in (None, True) else "localhost",
        token=args.get("token") if args.get("token") is not True else None,
        subdomain=subdomain if subdomain is not True else None,
        domain=domain if domain is not True else None,
        mode=mode,
        server=args.get("server") if args.get("server") not in (None, True) else None,
    )

    # Pass-through unfiltered output
    def on_output(text):
        for line in text.split("\n"):
            line = line.replace("\r", "")
            if should_filter_line(line):
                continue
            err = parse_error(line)
            if err:
                print("  {} {}".format(c["red"]("Error:"), err), file=sys.stderr)
            else:
                print("  " + c["gray"](line.strip()))

    tunnel.on_output = on_output

    # Graceful shutdown
    shutting_down = False

    def shutdown(signum=None, frame=None):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print("\n  " + c["gray"]("Closing tunnel..."))
        tunnel.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    # SIGTERM not available on Windows
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        tunnel.start()
        _display_url(c, tunnel.url, tunnel.expires_at)
    except RuntimeError as err:
        print("\n  {} {}\n".format(c["red"]("Error:"), err), file=sys.stderr)
        sys.exit(1)

    # Keep alive until SSH exits
    def on_close(code):
        print("\n  " + c["gray"]("Tunnel closed.") + "\n")
        os._exit(0)

    tunnel.on_close = on_close

    # Block main thread — use polling so signal handlers can run on Windows
    try:
        while tunnel._process and tunnel._process.poll() is None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
