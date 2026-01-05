#!/usr/bin/env python3
"""
CRM Platform - Service Runner with Live Logs Panel

A flexible service runner for local development with full control over
services, ports, and execution modes. Includes a browser-based log viewer.

Usage:
    python run_all_services.py                    # Run all services (default)
    python run_all_services.py --sales-only       # Run only sales-module
    python run_all_services.py --ui-only          # Run only unified-ui
    python run_all_services.py --video-only       # Run only video-critique
    python run_all_services.py --background       # Run in background (no logs)
    python run_all_services.py --foreground       # Run with interleaved logs
    python run_all_services.py --env production   # Set environment
    python run_all_services.py --sales-port 9000  # Custom port
    python run_all_services.py --no-logs-panel    # Disable browser logs panel

Options:
    --env          Environment: development, production, local (default: development)
    --sales-port   Sales module port (default: 8000)
    --ui-port      Unified UI port (default: 3005)
    --video-port   Video critique port (default: 8003)
    --sales-only   Run only the sales module
    --ui-only      Run only the unified UI
    --video-only   Run only the video critique service
    --background   Run services in background (daemonize)
    --foreground   Run with interleaved stdout/stderr (default: separate output)
    --no-banner    Skip the startup banner
    --no-logs-panel  Disable the browser-based logs panel
    --health-check Wait for health checks before reporting success
    --timeout      Startup timeout in seconds (default: 30)
    --log-dir      Directory for log files in background mode

Press Ctrl+C to stop all services gracefully.
"""

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

# =============================================================================
# Configuration
# =============================================================================

ROOT_DIR = Path(__file__).parent.resolve()

# Load .env so all services get shared environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass  # dotenv not installed, services will load their own .env

# ANSI color codes
COLORS = {
    "blue": "\033[34m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "reset": "\033[0m",
    "bold": "\033[1m",
}

# Service configurations
# Note: Services are independent and can run standalone.
# When running together, unified-ui can proxy to proposal-bot.
SERVICES = {
    "proposal-bot": {
        "name": "proposal-bot",
        "display_name": "Sales Module (proposal-bot)",
        "directory": "src/sales-module",
        "default_port": 8000,
        "color": "cyan",
        "health_endpoint": "/health",
        "depends_on": [],  # No dependencies - can run standalone
    },
    "unified-ui": {
        "name": "unified-ui",
        "display_name": "Unified UI",
        "directory": "src/unified-ui",
        "default_port": 3005,
        "color": "magenta",
        "health_endpoint": "/health",
        "depends_on": [],  # No hard dependencies - can run standalone
    },
    "asset-management": {
        "name": "asset-management",
        "display_name": "Asset Management",
        "directory": "src/asset-management",
        "default_port": 8001,
        "color": "green",
        "health_endpoint": "/health",
        "depends_on": [],  # No dependencies - can run standalone
    },
    "security-service": {
        "name": "security-service",
        "display_name": "Security Service",
        "directory": "src/security-service",
        "default_port": 8002,
        "color": "yellow",
        "health_endpoint": "/health",
        "depends_on": [],  # No dependencies - can run standalone
    },
    "video-critique": {
        "name": "video-critique",
        "display_name": "Video Critique",
        "directory": "src/video-critique",
        "default_port": 8003,
        "color": "blue",
        "health_endpoint": "/health",
        "depends_on": [],  # No dependencies - can run standalone
    },
}

# WebSocket server port for logs panel
LOGS_WS_PORT = 9000
LOGS_BUFFER_SIZE = 500  # Lines per service


# =============================================================================
# Log Aggregator & WebSocket Server
# =============================================================================


@dataclass
class LogEntry:
    """A single log entry."""
    service: str
    timestamp: str
    level: str
    message: str
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "log",
            "service": self.service,
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }


class LogAggregator:
    """
    Aggregates logs from all services and broadcasts via WebSocket.

    Features:
    - Buffers last N lines per service
    - Parses log levels from output
    - Broadcasts to connected WebSocket clients
    - Thread-safe
    """

    def __init__(self, buffer_size: int = LOGS_BUFFER_SIZE):
        self.buffer_size = buffer_size
        self.buffers: dict[str, deque[LogEntry]] = {}
        self.service_status: dict[str, str] = {}  # running, stopped, error
        self.clients: set = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def init_service(self, service: str):
        """Initialize buffer for a service."""
        with self._lock:
            if service not in self.buffers:
                self.buffers[service] = deque(maxlen=self.buffer_size)
            self.service_status[service] = "starting"

    def set_service_status(self, service: str, status: str):
        """Update service status and broadcast."""
        with self._lock:
            self.service_status[service] = status
        self._broadcast_status()

    def add_log(self, service: str, line: str):
        """Add a log line from a service."""
        entry = self._parse_log_line(service, line)

        with self._lock:
            if service not in self.buffers:
                self.buffers[service] = deque(maxlen=self.buffer_size)
            self.buffers[service].append(entry)

        # Broadcast to clients
        self._broadcast_log(entry)

    def _parse_log_line(self, service: str, line: str) -> LogEntry:
        """Parse a log line to extract level and timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        level = "INFO"
        message = line

        # Strip ANSI codes for level detection and cleaner display
        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        message = clean_line  # Use cleaned message for display

        # Try to detect log level from common patterns
        # Order matters: check more severe/specific levels first
        level_patterns = [
            (r"\b(CRITICAL|FATAL)\b", "ERROR"),
            (r"\b(ERROR)\b", "ERROR"),
            # Python exceptions and tracebacks
            (r"Traceback \(most recent call last\)", "ERROR"),
            (r"\b(AttributeError|TypeError|ValueError|KeyError|ImportError|ModuleNotFoundError|RuntimeError|Exception|FileNotFoundError|PermissionError|OSError)\b:", "ERROR"),
            (r"^\s*File \".*\", line \d+", "ERROR"),  # Traceback file lines
            (r"^\s+\^+", "ERROR"),  # Caret indicators (^^^)
            (r"^<frozen ", "ERROR"),  # Frozen module lines
            (r"^\s{4,}(self\.|return |raise |await |from .+ import)", "ERROR"),  # Traceback code lines
            (r"^\s{4,}\S+\(", "ERROR"),  # Indented function calls
            (r"^\s{4,}\w+\s*=\s*\S", "ERROR"),  # Indented assignments (var = value)
            (r"\b(WARN(?:ING)?)\b", "WARN"),
            (r"DeprecationWarning:", "WARN"),
            (r"\b(DEBUG)\b", "DEBUG"),
            (r"\b(INFO)\b", "INFO"),
        ]

        for pattern, lvl in level_patterns:
            if re.search(pattern, clean_line, re.IGNORECASE):
                level = lvl
                break

        # Try to extract timestamp from line (common formats)
        ts_patterns = [
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})",
            r"(\d{2}:\d{2}:\d{2})",
        ]
        for pattern in ts_patterns:
            match = re.search(pattern, clean_line)
            if match:
                # Keep our timestamp for consistency but could use theirs
                break

        return LogEntry(
            service=service,
            timestamp=timestamp,
            level=level,
            message=message,
            raw=line,
        )

    def get_buffer(self, service: Optional[str] = None) -> list[dict]:
        """Get buffered logs as dicts."""
        with self._lock:
            if service:
                entries = list(self.buffers.get(service, []))
            else:
                # Combine all buffers, sorted by timestamp
                entries = []
                for buf in self.buffers.values():
                    entries.extend(buf)
                entries.sort(key=lambda e: e.timestamp)
            return [e.to_dict() for e in entries]

    def get_status(self) -> dict:
        """Get current service status."""
        with self._lock:
            return {
                "type": "status",
                "services": dict(self.service_status),
            }

    def clear_all(self):
        """Clear all log buffers."""
        with self._lock:
            for service in self.buffers:
                self.buffers[service].clear()
        # Broadcast clear command to all clients
        self._broadcast_clear()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the asyncio event loop for broadcasting."""
        self._loop = loop

    def _broadcast_log(self, entry: LogEntry):
        """Broadcast a log entry to all connected clients."""
        if not self._loop or not self.clients:
            return

        message = json.dumps(entry.to_dict())

        async def send_to_all():
            disconnected = set()
            for client in self.clients.copy():
                try:
                    await client.send(message)
                except Exception:
                    disconnected.add(client)
            self.clients -= disconnected

        try:
            asyncio.run_coroutine_threadsafe(send_to_all(), self._loop)
        except Exception:
            pass

    def _broadcast_status(self):
        """Broadcast status update to all clients."""
        if not self._loop or not self.clients:
            return

        message = json.dumps(self.get_status())

        async def send_to_all():
            disconnected = set()
            for client in self.clients.copy():
                try:
                    await client.send(message)
                except Exception:
                    disconnected.add(client)
            self.clients -= disconnected

        try:
            asyncio.run_coroutine_threadsafe(send_to_all(), self._loop)
        except Exception:
            pass

    def _broadcast_clear(self):
        """Broadcast clear command to all clients."""
        if not self._loop or not self.clients:
            return

        message = json.dumps({"type": "clear"})

        async def send_to_all():
            disconnected = set()
            for client in self.clients.copy():
                try:
                    await client.send(message)
                except Exception:
                    disconnected.add(client)
            self.clients -= disconnected

        try:
            asyncio.run_coroutine_threadsafe(send_to_all(), self._loop)
        except Exception:
            pass


# Global log aggregator instance
log_aggregator: Optional[LogAggregator] = None


async def websocket_handler(websocket):
    """Handle a WebSocket connection."""
    global log_aggregator
    if not log_aggregator:
        return

    # Register client
    log_aggregator.clients.add(websocket)

    try:
        # Send initial buffer
        buffer_msg = json.dumps({
            "type": "buffer",
            "logs": log_aggregator.get_buffer(),
        })
        await websocket.send(buffer_msg)

        # Send current status
        await websocket.send(json.dumps(log_aggregator.get_status()))

        # Keep connection alive, handle any incoming messages
        async for message in websocket:
            # Client can send commands like {"action": "clear"} or {"action": "ping"}
            try:
                data = json.loads(message)
                action = data.get("action")
                if action == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                elif action == "clear":
                    # Clear all log buffers server-side
                    log_aggregator.clear_all()
            except Exception:
                pass

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        log_aggregator.clients.discard(websocket)


async def start_websocket_server(port: int = LOGS_WS_PORT):
    """Start the WebSocket server for log streaming."""
    global log_aggregator
    if not log_aggregator:
        log_aggregator = LogAggregator()

    log_aggregator.set_event_loop(asyncio.get_event_loop())

    server = await websockets.serve(websocket_handler, "localhost", port)
    return server


def run_websocket_server_thread(port: int = LOGS_WS_PORT):
    """Run WebSocket server in a separate thread."""
    server_ready = threading.Event()

    def run():
        global log_aggregator

        try:
            # Create new event loop for this thread FIRST
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Set the loop on the aggregator
            if log_aggregator:
                log_aggregator.set_event_loop(loop)

            # Start the server
            async def start_server():
                server = await websockets.serve(websocket_handler, "localhost", port)
                server_ready.set()  # Signal that server is ready
                await asyncio.Future()  # Run forever

            loop.run_until_complete(start_server())
        except Exception as e:
            # Only print if it's not a normal shutdown or expected errors
            err_str = str(e)
            if "Event loop stopped" not in err_str and "no running event loop" not in err_str:
                log("runner", f"WebSocket server error: {e}", level="error")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    # Wait for server to be ready (up to 2 seconds)
    if server_ready.wait(timeout=2.0):
        return thread
    else:
        log("runner", "WebSocket server failed to start within timeout", level="warn")
        return thread


# =============================================================================
# Utilities
# =============================================================================


def kill_port(port: int) -> bool:
    """Kill any process using the specified port."""
    try:
        # Find process using the port (works on macOS/Linux)
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
        )
        pids = result.stdout.strip().split('\n')
        pids = [p for p in pids if p]  # Filter empty strings

        if not pids:
            return False

        for pid in pids:
            try:
                subprocess.run(["kill", "-9", pid], capture_output=True)
            except Exception:
                pass

        return True
    except Exception:
        return False


def cleanup_ports(ports: list[int]) -> int:
    """Kill processes on all specified ports. Returns count of ports cleaned."""
    cleaned = 0
    for port in ports:
        if kill_port(port):
            cleaned += 1
    return cleaned


def color(text: str, color_name: str, bold: bool = False) -> str:
    """Apply ANSI color to text."""
    if not sys.stdout.isatty():
        return text
    prefix = COLORS.get("bold", "") if bold else ""
    return f"{prefix}{COLORS.get(color_name, '')}{text}{COLORS['reset']}"


def log(service: str, message: str, level: str = "info"):
    """Print a formatted log message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    service_color = SERVICES.get(service, {}).get("color", "blue")

    level_colors = {"info": "blue", "warn": "yellow", "error": "red"}
    level_col = level_colors.get(level, "blue")

    prefix = color(f"[{timestamp}]", level_col)
    svc = color(f"[{service}]", service_color, bold=True)

    print(f"{prefix} {svc} {message}")


def check_health(url: str, timeout: float = 5.0) -> bool:
    """Check if a service health endpoint responds."""
    if not HTTPX_AVAILABLE:
        return True  # Skip if httpx not available

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            return response.status_code == 200
    except Exception:
        return False


def wait_for_health(service: str, port: int, timeout: int = 30) -> bool:
    """Wait for a service to become healthy."""
    health_endpoint = SERVICES[service]["health_endpoint"]
    url = f"http://localhost:{port}{health_endpoint}"

    start = time.time()
    while time.time() - start < timeout:
        if check_health(url, timeout=2.0):
            return True
        time.sleep(0.5)
    return False


# =============================================================================
# Service Management
# =============================================================================


class ServiceProcess:
    """Wrapper for a service subprocess."""

    def __init__(
        self,
        name: str,
        directory: str,
        port: int,
        env: str,
        foreground: bool = False,
        log_file: Optional[Path] = None,
        extra_env: Optional[dict] = None,
        use_log_aggregator: bool = False,
    ):
        self.name = name
        self.directory = ROOT_DIR / directory
        self.port = port
        self.env = env
        self.foreground = foreground
        self.log_file = log_file
        self.extra_env = extra_env or {}
        self.use_log_aggregator = use_log_aggregator
        self.process: Optional[subprocess.Popen] = None
        self._output_thread: Optional[threading.Thread] = None
        self._log_handle = None

    def start(self) -> bool:
        """Start the service process."""
        global log_aggregator

        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env["ENVIRONMENT"] = self.env
        env["PYTHONUNBUFFERED"] = "1"  # Force unbuffered output for real-time logs
        # Always output DEBUG logs when using logs panel - frontend filters what to display
        # Override any LOG_LEVEL from .env so debug toggle works
        if self.use_log_aggregator:
            env["LOG_LEVEL"] = "DEBUG"
        env.update(self.extra_env)

        # Add shared modules to PYTHONPATH for local development
        # This allows importing crm_security, crm_cache, crm_channels, crm_llm without pip install
        shared_paths = [
            str(ROOT_DIR / "src" / "shared" / "crm-security"),
            str(ROOT_DIR / "src" / "shared" / "crm-cache"),
            str(ROOT_DIR / "src" / "shared" / "crm-channels"),
            str(ROOT_DIR / "src" / "shared" / "crm-llm"),
        ]
        existing_pythonpath = env.get("PYTHONPATH", "")
        if existing_pythonpath:
            shared_paths.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(shared_paths)

        log(self.name, f"Starting on port {self.port} (env: {self.env})...")

        # Initialize log aggregator for this service
        if self.use_log_aggregator and log_aggregator:
            log_aggregator.init_service(self.name)

        # Prepare stdout/stderr handling
        # When using log aggregator, always capture output
        if self.use_log_aggregator or self.foreground:
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
        elif self.log_file:
            self._log_handle = open(self.log_file, "w")
            stdout = self._log_handle
            stderr = subprocess.STDOUT
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

        try:
            self.process = subprocess.Popen(
                [sys.executable, "run_service.py"],
                cwd=self.directory,
                env=env,
                stdout=stdout,
                stderr=stderr,
                # Use default buffering for binary mode (line buffering only works with text mode)
            )

            # Start output streaming
            if self.use_log_aggregator or self.foreground:
                self._output_thread = threading.Thread(
                    target=self._stream_output,
                    daemon=True,
                )
                self._output_thread.start()

            # Update status
            if self.use_log_aggregator and log_aggregator:
                log_aggregator.set_service_status(self.name, "running")

            return True
        except Exception as e:
            log(self.name, f"Failed to start: {e}", level="error")
            if self.use_log_aggregator and log_aggregator:
                log_aggregator.set_service_status(self.name, "error")
            return False

    def _stream_output(self):
        """Stream process output to console and/or log aggregator."""
        global log_aggregator

        if not self.process or not self.process.stdout:
            return

        service_color = SERVICES.get(self.name, {}).get("color", "blue")
        prefix = color(f"[{self.name}]", service_color)

        for line in iter(self.process.stdout.readline, b""):
            try:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    # Send to log aggregator
                    if self.use_log_aggregator and log_aggregator:
                        log_aggregator.add_log(self.name, text)

                    # Also print to console in foreground mode
                    if self.foreground:
                        print(f"{prefix} {text}")
            except Exception:
                pass

        # Process ended - update status
        if self.use_log_aggregator and log_aggregator:
            ret = self.process.poll()
            status = "stopped" if ret == 0 else "error"
            log_aggregator.set_service_status(self.name, status)

    def stop(self, timeout: int = 5):
        """Stop the service gracefully."""
        if not self.process:
            return

        log(self.name, "Stopping...")
        self.process.terminate()

        try:
            self.process.wait(timeout=timeout)
            log(self.name, "Stopped", level="info")
        except subprocess.TimeoutExpired:
            log(self.name, "Force killing...", level="warn")
            self.process.kill()
            self.process.wait()

        if self._log_handle:
            self._log_handle.close()

    def is_running(self) -> bool:
        """Check if process is still running."""
        if not self.process:
            return False
        return self.process.poll() is None

    def return_code(self) -> Optional[int]:
        """Get process return code if exited."""
        if not self.process:
            return None
        return self.process.poll()


class ServiceManager:
    """Manage multiple services."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.services: dict[str, ServiceProcess] = {}
        self._shutdown_requested = False
        self._ws_thread: Optional[threading.Thread] = None
        self.use_logs_panel = (
            not args.background
            and not args.no_logs_panel
            and WEBSOCKETS_AVAILABLE
        )

    def start_logs_panel(self) -> bool:
        """Start the WebSocket server for the logs panel."""
        global log_aggregator

        if not self.use_logs_panel:
            return True

        if not WEBSOCKETS_AVAILABLE:
            print(color("websockets not installed. Install with: pip install websockets", "yellow"))
            return True

        # Initialize global log aggregator
        log_aggregator = LogAggregator()

        # Start WebSocket server in background thread
        self._ws_thread = run_websocket_server_thread(LOGS_WS_PORT)
        time.sleep(0.3)  # Brief pause to let server start

        log("runner", f"Logs panel WebSocket server started on ws://localhost:{LOGS_WS_PORT}")
        return True

    def start_services(self) -> bool:
        """Start all requested services."""
        services_to_start = self._get_services_to_start()

        if not services_to_start:
            print(color("No services to start!", "red"))
            return False

        # Start services in dependency order
        for service_name in services_to_start:
            config = SERVICES[service_name]

            # Wait for dependencies
            for dep in config["depends_on"]:
                if dep in self.services:
                    if self.args.health_check:
                        dep_port = self._get_port(dep)
                        log(service_name, f"Waiting for {dep} to be healthy...")
                        if not wait_for_health(dep, dep_port, self.args.timeout):
                            log(service_name, f"Dependency {dep} not healthy", level="error")
                            return False
                    else:
                        time.sleep(2)  # Brief pause for dependency startup

            # Prepare extra environment
            extra_env = {}
            if service_name == "unified-ui" and "proposal-bot" in services_to_start:
                # Only set SALES_BOT_URL if running both services together
                extra_env["SALES_BOT_URL"] = f"http://localhost:{self.args.sales_port}"

            # Prepare log file for background mode
            log_file = None
            if self.args.background and self.args.log_dir:
                log_dir = Path(self.args.log_dir)
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / f"{service_name}.log"

            # Create and start service
            service = ServiceProcess(
                name=service_name,
                directory=config["directory"],
                port=self._get_port(service_name),
                env=self.args.env,
                foreground=self.args.foreground,
                log_file=log_file,
                extra_env=extra_env,
                use_log_aggregator=self.use_logs_panel,
            )

            if not service.start():
                return False

            self.services[service_name] = service

        return True

    def _get_services_to_start(self) -> list[str]:
        """Get list of services to start based on args."""
        if self.args.sales_only:
            return ["proposal-bot"]
        elif self.args.ui_only:
            return ["unified-ui"]
        elif self.args.assets_only:
            return ["asset-management"]
        elif self.args.security_only:
            return ["security-service"]
        elif self.args.video_only:
            return ["video-critique"]
        else:
            return ["proposal-bot", "unified-ui", "asset-management", "security-service", "video-critique"]

    def _get_port(self, service_name: str) -> int:
        """Get port for a service."""
        if service_name == "proposal-bot":
            return self.args.sales_port
        elif service_name == "unified-ui":
            return self.args.ui_port
        elif service_name == "asset-management":
            return self.args.assets_port
        elif service_name == "security-service":
            return self.args.security_port
        elif service_name == "video-critique":
            return self.args.video_port
        return SERVICES[service_name]["default_port"]

    def wait_for_healthy(self) -> bool:
        """Wait for all services to become healthy."""
        if not self.args.health_check:
            return True

        print()
        log("runner", "Waiting for services to become healthy...")

        for name in self.services:
            port = self._get_port(name)
            if wait_for_health(name, port, self.args.timeout):
                log(name, color("Healthy ✓", "green"))
            else:
                log(name, color("Not responding", "red"), level="error")
                return False

        return True

    def run(self):
        """Run services and wait for completion or interrupt."""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        try:
            while not self._shutdown_requested:
                # Check for crashed services
                for name, service in list(self.services.items()):
                    if not service.is_running():
                        ret = service.return_code()
                        log(name, f"Exited with code {ret}", level="error")
                        del self.services[name]

                if not self.services:
                    print(color("All services have stopped.", "yellow"))
                    break

                time.sleep(1)
        except KeyboardInterrupt:
            self._shutdown_handler(None, None)

    def _shutdown_handler(self, _signum, _frame):
        """Handle shutdown signal."""
        if self._shutdown_requested:
            return

        self._shutdown_requested = True
        print()
        print(color("Shutting down services...", "yellow"))

        # Stop in reverse order
        for name in reversed(list(self.services.keys())):
            self.services[name].stop()

        print(color("All services stopped.", "green"))

    def stop_all(self):
        """Stop all services."""
        for service in self.services.values():
            service.stop()


# =============================================================================
# Banner & Output
# =============================================================================


def print_banner(args: argparse.Namespace):
    """Print startup banner."""
    if args.no_banner:
        return

    print()
    print(color("=" * 60, "blue"))
    print(color("CRM Platform - Service Runner", "blue", bold=True))
    print(color("=" * 60, "blue"))
    print()
    print(f"  Environment:  {color(args.env, 'cyan')}")
    print(f"  Mode:         {color('foreground' if args.foreground else 'background' if args.background else 'default', 'cyan')}")
    print()


def print_access_points(args: argparse.Namespace, services: list[str], logs_panel_enabled: bool = False):
    """Print access points after services start."""
    print()
    print(color("=" * 60, "green"))
    print(color("Services Started!", "green", bold=True))
    print(color("=" * 60, "green"))
    print()
    print(color("Access points:", "green"))

    if "unified-ui" in services:
        print(f"  • Unified UI:    {color(f'http://localhost:{args.ui_port}', 'cyan')}")
    if "proposal-bot" in services:
        print(f"  • Proposal Bot:  {color(f'http://localhost:{args.sales_port}', 'cyan')}")
        print(f"  • API Docs:      {color(f'http://localhost:{args.sales_port}/docs', 'cyan')}")
    if "asset-management" in services:
        print(f"  • Asset Mgmt:    {color(f'http://localhost:{args.assets_port}', 'cyan')}")
        print(f"  • Asset Docs:    {color(f'http://localhost:{args.assets_port}/docs', 'cyan')}")
    if "security-service" in services:
        print(f"  • Security:      {color(f'http://localhost:{args.security_port}', 'cyan')}")
        print(f"  • Security Docs: {color(f'http://localhost:{args.security_port}/docs', 'cyan')}")

    if logs_panel_enabled:
        print()
        print(color("Development Tools:", "green"))
        logs_url = f"http://localhost:{args.ui_port}/logs-panel.html"
        dev_panel_url = f"http://localhost:{args.ui_port}/dev-panel.html"
        print(f"  • Logs Panel:    {color(logs_url, 'cyan')}")
        print(f"  • Dev Panel:     {color(dev_panel_url, 'cyan')}")

    print()

    if args.background:
        print(color("Services running in background.", "yellow"))
        if args.log_dir:
            print(f"Logs: {args.log_dir}/")
        print("Use 'make stop' or kill processes to stop.")
    else:
        print("Press Ctrl+C to stop all services")

    print(color("=" * 60, "green"))
    print()


def open_logs_panel(ui_port: int, max_wait: float = 10.0):
    """Open the logs panel in the default browser after unified-ui is ready."""
    global log_aggregator

    def _open():
        global log_aggregator

        # Check if there are already clients connected (existing browser tab)
        # If so, skip opening a new tab - they'll auto-reconnect
        if log_aggregator and log_aggregator.clients:
            log("runner", f"Logs panel already has {len(log_aggregator.clients)} client(s) connected, skipping browser open")
            return

        # Add cache-busting to prevent browser from showing cached main page
        cache_bust = int(time.time())
        url = f"http://localhost:{ui_port}/logs-panel.html?t={cache_bust}"
        health_url = f"http://localhost:{ui_port}/health"

        # Wait for unified-ui to be ready (up to max_wait seconds)
        start = time.time()
        while time.time() - start < max_wait:
            if check_health(health_url, timeout=1.0):
                # Service is ready, wait a tiny bit more for static files
                time.sleep(0.5)
                break
            time.sleep(0.5)

        # Check again after waiting - client may have connected during startup
        if log_aggregator and log_aggregator.clients:
            log("runner", f"Logs panel client connected during startup, skipping browser open")
            return

        log("runner", f"Opening browser: {url}")

        try:
            webbrowser.open_new_tab(url)
        except Exception as e:
            print(f"Could not open browser: {e}")

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def print_status(manager: ServiceManager):
    """Print current service status."""
    print()
    print(color("Service Status:", "blue", bold=True))
    for name, service in manager.services.items():
        status = color("running", "green") if service.is_running() else color("stopped", "red")
        print(f"  • {name}: {status}")
    print()


# =============================================================================
# Main
# =============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CRM Platform - Service Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           Run all services with defaults
  %(prog)s --sales-only              Run only sales module
  %(prog)s --ui-only                 Run only unified UI
  %(prog)s --foreground              Run with interleaved logs
  %(prog)s --background --log-dir logs  Run in background with log files
  %(prog)s --env production          Run in production mode
  %(prog)s --sales-port 9000         Custom sales port
  %(prog)s --health-check            Wait for health checks

Environment Variables:
  SALES_PORT      Override default sales port (8000)
  UI_PORT         Override default UI port (3005)
  ENVIRONMENT     Override default environment (development)
        """,
    )

    # Service selection
    service_group = parser.add_mutually_exclusive_group()
    service_group.add_argument(
        "--sales-only",
        action="store_true",
        help="Run only the sales module (proposal-bot)",
    )
    service_group.add_argument(
        "--ui-only",
        action="store_true",
        help="Run only the unified UI",
    )
    service_group.add_argument(
        "--assets-only",
        action="store_true",
        help="Run only the asset management service",
    )
    service_group.add_argument(
        "--security-only",
        action="store_true",
        help="Run only the security service",
    )
    service_group.add_argument(
        "--video-only",
        action="store_true",
        help="Run only the video critique service",
    )

    # Port configuration
    parser.add_argument(
        "--sales-port",
        type=int,
        default=int(os.environ.get("SALES_PORT", 8000)),
        help="Sales module port (default: 8000)",
    )
    parser.add_argument(
        "--ui-port",
        type=int,
        default=int(os.environ.get("UI_PORT", 3005)),
        help="Unified UI port (default: 3005)",
    )
    parser.add_argument(
        "--assets-port",
        type=int,
        default=int(os.environ.get("ASSETS_PORT", 8001)),
        help="Asset management port (default: 8001)",
    )
    parser.add_argument(
        "--security-port",
        type=int,
        default=int(os.environ.get("SECURITY_PORT", 8002)),
        help="Security service port (default: 8002)",
    )
    parser.add_argument(
        "--video-port",
        type=int,
        default=int(os.environ.get("VIDEO_PORT", 8003)),
        help="Video critique port (default: 8003)",
    )

    # Environment
    parser.add_argument(
        "--env", "-e",
        choices=["development", "production", "local"],
        default=os.environ.get("ENVIRONMENT", "development"),
        help="Environment mode (default: development)",
    )

    # Execution mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--background", "-b",
        action="store_true",
        help="Run services in background (daemonize)",
    )
    mode_group.add_argument(
        "--foreground", "-f",
        action="store_true",
        help="Run with interleaved stdout/stderr",
    )

    # Additional options
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Skip the startup banner",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Wait for health checks before reporting success",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Startup/health check timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        help="Directory for log files in background mode",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Just print service status and exit",
    )
    parser.add_argument(
        "--no-logs-panel",
        action="store_true",
        help="Disable the browser-based logs panel",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Quick status check
    if args.status:
        print(color("Checking service status...", "blue"))
        for name, config in SERVICES.items():
            if name == "proposal-bot":
                port = args.sales_port
            elif name == "unified-ui":
                port = args.ui_port
            elif name == "asset-management":
                port = args.assets_port
            elif name == "security-service":
                port = args.security_port
            else:
                port = config["default_port"]
            healthy = check_health(f"http://localhost:{port}/health")
            status = color("running ✓", "green") if healthy else color("not running", "red")
            print(f"  • {config['display_name']}: {status}")
        return 0

    # Print banner
    print_banner(args)

    # Create manager and start services
    manager = ServiceManager(args)

    # Clean up any ports that might be in use from previous runs
    ports_to_clean = [args.sales_port, args.ui_port, args.assets_port, args.security_port]
    if manager.use_logs_panel:
        ports_to_clean.append(LOGS_WS_PORT)

    cleaned = cleanup_ports(ports_to_clean)
    if cleaned > 0:
        log("runner", f"Cleaned up {cleaned} port(s) from previous runs")
        time.sleep(0.5)  # Brief pause after killing processes

    # Start logs panel WebSocket server first
    if manager.use_logs_panel:
        if not WEBSOCKETS_AVAILABLE:
            print(color("Note: Install 'websockets' package for logs panel: pip install websockets", "yellow"))
            print()
        else:
            manager.start_logs_panel()

    print(color("Starting services...", "blue"))
    print()

    if not manager.start_services():
        print(color("Failed to start services.", "red"))
        manager.stop_all()
        return 1

    # Wait for health if requested
    if not manager.wait_for_healthy():
        print(color("Services failed health check.", "red"))
        manager.stop_all()
        return 1

    # Print access points
    services_started = list(manager.services.keys())
    print_access_points(args, services_started, logs_panel_enabled=manager.use_logs_panel)

    # Open logs panel in browser (waits for unified-ui to be healthy)
    if manager.use_logs_panel and "unified-ui" in services_started:
        open_logs_panel(args.ui_port)

    # Background mode - detach and exit
    if args.background:
        # In a real daemon setup, we'd fork here
        # For simplicity, we just return and let services run
        # User can use `make ps` or `ps aux | grep run_service` to find them
        print(color("Note: Services are child processes. They will stop when this script exits.", "yellow"))
        print(color("For true background operation, use Docker or systemd.", "yellow"))
        return 0

    # Foreground mode - wait for services
    manager.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
