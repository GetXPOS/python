import subprocess
import sys
import threading

from .utils import (
    resolve_token,
    build_ssh_user,
    build_remote_forward,
    parse_url,
    parse_port_url,
    parse_expiry,
    parse_error,
)

DEFAULT_SERVER = "go.xpos.dev"
CONNECT_TIMEOUT = 15
KILL_TIMEOUT = 3


class XposTunnel:
    """SSH tunnel to XPOS. Manages an SSH subprocess."""

    def __init__(self, port, host="127.0.0.1", token=None, subdomain=None,
                 domain=None, mode="http", server=DEFAULT_SERVER,
                 on_connect=None, on_close=None, on_output=None):
        if not port:
            raise ValueError("port is required")

        self.port = port
        self.host = host
        self.token = resolve_token(token)
        self.subdomain = subdomain
        self.domain = domain
        self.mode = mode
        self.server = server or DEFAULT_SERVER

        if self.subdomain and self.domain:
            raise ValueError("subdomain and domain are mutually exclusive")
        if self.mode not in ("http", "tcp"):
            raise ValueError('mode must be "http" or "tcp"')
        if (self.subdomain or self.domain) and not self.token:
            raise ValueError(
                "{} requires a token".format("domain" if self.domain else "subdomain")
            )

        self.url = None
        self.expires_at = None
        self.connected = False

        self.on_connect = on_connect
        self.on_close = on_close
        self.on_output = on_output

        self._process = None
        self._buffer = ""
        self._lock = threading.Lock()
        self._settled = threading.Event()
        self._error = None

    def _build_args(self):
        """Build SSH command arguments."""
        user = build_ssh_user(self.token, self.mode)
        remote_forward = build_remote_forward(
            port=self.port,
            host=self.host,
            subdomain=self.subdomain,
            domain=self.domain,
        )

        return [
            "ssh",
            "-p", "443",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=~/.ssh/xpos_known_hosts",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=10",
            "-R", remote_forward,
            "{}@{}".format(user, self.server),
        ]

    def _read_stream(self, stream):
        """Read from a stream in a thread, accumulate buffer."""
        try:
            while True:
                chunk = stream.read1(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")

                with self._lock:
                    self._buffer += text

                # Fire output callback
                if self.on_output:
                    try:
                        self.on_output(text)
                    except Exception:
                        pass

                # Check for errors
                for line in text.split("\n"):
                    line = line.replace("\r", "")
                    err = parse_error(line)
                    if err and not self._settled.is_set():
                        self._error = err
                        self._settled.set()
                        return

                # Try to parse URL
                with self._lock:
                    buf = self._buffer

                if self.mode == "tcp":
                    url = parse_port_url(buf)
                else:
                    url = parse_url(buf)

                if url and not self._settled.is_set():
                    self.url = url
                    self.expires_at = parse_expiry(buf)
                    self.connected = True
                    self._settled.set()
        except Exception:
            pass

    def start(self):
        """Spawn SSH process and connect the tunnel. Blocks until connected.
        Returns the tunnel URL. Raises RuntimeError on failure."""
        if self.connected:
            raise RuntimeError("Tunnel is already connected")

        self.url = None
        self.expires_at = None
        self._buffer = ""
        self._error = None
        self._settled = threading.Event()

        args = self._build_args()
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }

        # Windows: prevent console window flash
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(args, **kwargs)
        except FileNotFoundError:
            raise RuntimeError(
                "SSH not found. Install OpenSSH and ensure 'ssh' is in your PATH."
            )

        self._process = proc

        # Start reader threads (daemon so they don't block exit)
        stdout_thread = threading.Thread(
            target=self._read_stream, args=(proc.stdout,), daemon=True
        )
        stderr_thread = threading.Thread(
            target=self._read_stream, args=(proc.stderr,), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        # Also monitor for unexpected process exit
        def _wait_proc():
            proc.wait()
            if not self._settled.is_set():
                self._error = "SSH exited with code {}".format(proc.returncode)
                self._settled.set()

        exit_thread = threading.Thread(target=_wait_proc, daemon=True)
        exit_thread.start()

        # Wait for connection or failure
        self._settled.wait(timeout=CONNECT_TIMEOUT)

        if not self._settled.is_set():
            # Timeout
            self._kill_process()
            raise RuntimeError("Connection timed out after 15s")

        if self._error:
            self._kill_process()
            raise RuntimeError(self._error)

        # Fire connect callback
        if self.on_connect:
            try:
                self.on_connect({"url": self.url, "expires_at": self.expires_at})
            except Exception:
                pass

        # Background thread to detect tunnel close
        def _close_waiter():
            proc.wait()
            self.connected = False
            self._process = None
            if self.on_close:
                try:
                    self.on_close(proc.returncode)
                except Exception:
                    pass

        close_thread = threading.Thread(target=_close_waiter, daemon=True)
        close_thread.start()

        return self.url

    def _kill_process(self):
        """Terminate the SSH process."""
        if not self._process:
            return
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=KILL_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._process.kill()
        except Exception:
            pass
        self.connected = False
        self._process = None

    def close(self):
        """Close the tunnel gracefully."""
        if not self._process:
            return

        proc = self._process
        self.connected = False

        try:
            proc.terminate()
            try:
                proc.wait(timeout=KILL_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass

        self._process = None
        if self.on_close:
            try:
                self.on_close(None)
            except Exception:
                pass


def connect(**kwargs):
    """Create and start a tunnel. Convenience function.
    Returns an XposTunnel with an active connection."""
    tunnel = XposTunnel(**kwargs)
    tunnel.start()
    return tunnel
