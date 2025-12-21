#!/usr/bin/env python3
"""
CRM Platform - Service Runner

A flexible service runner for local development with full control over
services, ports, and execution modes.

Usage:
    python run_all_services.py                    # Run all services (default)
    python run_all_services.py --sales-only       # Run only sales-module
    python run_all_services.py --ui-only          # Run only unified-ui
    python run_all_services.py --background       # Run in background (no logs)
    python run_all_services.py --foreground       # Run with interleaved logs
    python run_all_services.py --env production   # Set environment
    python run_all_services.py --sales-port 9000  # Custom port

Options:
    --env          Environment: development, production, local (default: development)
    --sales-port   Sales module port (default: 8000)
    --ui-port      Unified UI port (default: 3005)
    --sales-only   Run only the sales module
    --ui-only      Run only the unified UI
    --background   Run services in background (daemonize)
    --foreground   Run with interleaved stdout/stderr (default: separate output)
    --no-banner    Skip the startup banner
    --health-check Wait for health checks before reporting success
    --timeout      Startup timeout in seconds (default: 30)
    --log-dir      Directory for log files in background mode

Press Ctrl+C to stop all services gracefully.
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# =============================================================================
# Configuration
# =============================================================================

ROOT_DIR = Path(__file__).parent.resolve()

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
}


# =============================================================================
# Utilities
# =============================================================================


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
    ):
        self.name = name
        self.directory = ROOT_DIR / directory
        self.port = port
        self.env = env
        self.foreground = foreground
        self.log_file = log_file
        self.extra_env = extra_env or {}
        self.process: Optional[subprocess.Popen] = None
        self._output_thread: Optional[threading.Thread] = None
        self._log_handle = None

    def start(self) -> bool:
        """Start the service process."""
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env["ENVIRONMENT"] = self.env
        env.update(self.extra_env)

        log(self.name, f"Starting on port {self.port} (env: {self.env})...")

        # Prepare stdout/stderr handling
        if self.foreground:
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
                bufsize=1,
            )

            # Start output streaming for foreground mode
            if self.foreground:
                self._output_thread = threading.Thread(
                    target=self._stream_output,
                    daemon=True,
                )
                self._output_thread.start()

            return True
        except Exception as e:
            log(self.name, f"Failed to start: {e}", level="error")
            return False

    def _stream_output(self):
        """Stream process output to console."""
        if not self.process or not self.process.stdout:
            return

        service_color = SERVICES.get(self.name, {}).get("color", "blue")
        prefix = color(f"[{self.name}]", service_color)

        for line in iter(self.process.stdout.readline, b""):
            try:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    print(f"{prefix} {text}")
            except Exception:
                pass

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
        else:
            return ["proposal-bot", "unified-ui", "asset-management", "security-service"]

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


def print_access_points(args: argparse.Namespace, services: list[str]):
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
    print_access_points(args, services_started)

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
