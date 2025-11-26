"""AsyncIO-based LSP client for rust-analyzer."""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from .constants import (
    CONTENT_LENGTH_HEADER,
    HEADER_SEPARATOR,
    INDEXING_TIMEOUT,
    PROGRESS_TOKENS,
    READ_BUFFER_SIZE,
    REQUEST_TIMEOUT,
    SHUTDOWN_TIMEOUT,
    LSPMethods,
)
from .exceptions import (
    LSPRequestError,
    RustAnalyzerNotFoundError,
)

logger = logging.getLogger(__name__)


class RustAnalyzerClient:
    """AsyncIO-based LSP client for rust-analyzer.

    This client manages rust-analyzer as a subprocess and handles LSP
    protocol communication via stdio.
    """

    def __init__(
        self,
        project_root: Path,
        rust_analyzer_path: str | None = None,
    ) -> None:
        """Initialize the rust-analyzer client.

        Args:
            project_root: Path to the Rust project root
            rust_analyzer_path: Optional explicit path to rust-analyzer executable
        """
        self.project_root = project_root
        self.rust_analyzer_path = rust_analyzer_path or self._find_rust_analyzer()
        self.process: asyncio.subprocess.Process | None = None
        self.request_id = 0
        self.pending_requests: dict[int, asyncio.Future[Any]] = {}
        self.notification_handlers: dict[str, Callable[..., Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._shutting_down = False
        # Progress state tracking - track active progress tasks
        self._active_progress: set[str] = set()  # Currently active progress tokens
        self._any_progress_started = False  # True once any progress begins
        self._ready = asyncio.Event()  # Set when all progress completes
        self._progress_message: str | None = None

    def _find_rust_analyzer(self) -> str:
        """Find rust-analyzer executable.

        Returns:
            Path to rust-analyzer executable

        Raises:
            RustAnalyzerNotFoundError: If rust-analyzer cannot be found
        """
        # Check environment variable first
        if env_path := os.environ.get("RUST_ANALYZER_PATH"):
            return env_path

        # Check if it's on PATH
        if path := shutil.which("rust-analyzer"):
            return path

        # Check common installation location
        cargo_bin = Path.home() / ".cargo" / "bin" / "rust-analyzer"
        if cargo_bin.exists():
            return str(cargo_bin)

        raise RustAnalyzerNotFoundError(
            "rust-analyzer not found. Please install it or set RUST_ANALYZER_PATH"
        )

    async def start(self) -> None:
        """Start rust-analyzer subprocess.

        Raises:
            RuntimeError: If the process fails to start
        """
        if self.process:
            return

        logger.info(f"Starting rust-analyzer for project: {self.project_root}")
        logger.info(f"Using rust-analyzer at: {self.rust_analyzer_path}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                self.rust_analyzer_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),
            )
        except OSError as e:
            raise RuntimeError(f"Failed to start rust-analyzer: {e}") from e

        # Start background tasks
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_reader())

        # Initialize LSP connection
        await self._initialize()

    async def _initialize(self) -> dict[str, Any]:
        """Send LSP initialize request.

        Returns:
            The initialize response from rust-analyzer

        Raises:
            LSPRequestError: If initialization fails
        """
        response = await self.request(
            LSPMethods.INITIALIZE,
            {
                "processId": os.getpid(),
                "clientInfo": {"name": "rust-analyzer-mcp", "version": "0.1.0"},
                "rootUri": f"file://{self.project_root.absolute()}",
                "capabilities": {
                    "textDocument": {
                        "hover": {"contentFormat": ["plaintext", "markdown"]},
                        "completion": {
                            "completionItem": {
                                "snippetSupport": True,
                                "resolveSupport": {
                                    "properties": [
                                        "documentation",
                                        "detail",
                                        "additionalTextEdits",
                                    ]
                                },
                            }
                        },
                        "definition": {"linkSupport": True},
                        "typeDefinition": {"linkSupport": True},
                        "implementation": {"linkSupport": True},
                        "references": {},
                        "documentHighlight": {},
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                        "formatting": {},
                        "rangeFormatting": {},
                        "rename": {"prepareSupport": True},
                        "codeAction": {
                            "codeActionLiteralSupport": {
                                "codeActionKind": {
                                    "valueSet": [
                                        "quickfix",
                                        "refactor",
                                        "refactor.extract",
                                        "refactor.inline",
                                        "refactor.rewrite",
                                        "source",
                                        "source.organizeImports",
                                    ]
                                }
                            },
                            "resolveSupport": {"properties": ["edit"]},
                        },
                        "publishDiagnostics": {"relatedInformation": True},
                        "callHierarchy": {},
                        "semanticTokens": {
                            "requests": {"full": True, "range": True},
                            "tokenTypes": [],
                            "tokenModifiers": [],
                            "formats": ["relative"],
                        },
                    },
                    "workspace": {
                        "applyEdit": True,
                        "symbol": {},
                        "executeCommand": {},
                        "workspaceFolders": True,
                        "configuration": True,
                    },
                    "window": {
                        "workDoneProgress": True,
                    },
                    "experimental": {
                        "commands": {
                            "commands": [
                                "rust-analyzer.syntaxTree",
                                "rust-analyzer.expandMacro",
                                "rust-analyzer.analyzerStatus",
                                "rust-analyzer.viewCrateGraph",
                                "rust-analyzer.relatedTests",
                                "rust-analyzer.runnables",
                                "rust-analyzer.ssr",
                            ]
                        }
                    },
                },
                "initializationOptions": {
                    "cargo": {"features": "all"},
                    "procMacro": {"enable": True},
                    "checkOnSave": {"enable": True, "command": "clippy"},
                },
            },
        )

        # Validate response has capabilities
        if not isinstance(response, dict) or "capabilities" not in response:
            logger.warning("Initialize response missing capabilities")
            response = {"capabilities": {}}

        logger.info("rust-analyzer initialized successfully")
        self._initialized = True

        # Send initialized notification
        await self.notify(LSPMethods.INITIALIZED, {})

        return dict(response)

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> Any:
        """Send request and wait for response.

        Args:
            method: LSP method name
            params: Request parameters
            timeout: Request timeout in seconds

        Returns:
            The response result

        Raises:
            LSPRequestError: If the request fails or times out
        """
        if self._shutting_down:
            raise LSPRequestError("Client is shutting down")

        self.request_id += 1
        request_id = self.request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        # Create future for response
        future: asyncio.Future[Any] = asyncio.Future()
        self.pending_requests[request_id] = future

        # Send request
        await self._send_message(message)

        # Wait for response
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise LSPRequestError(
                f"Request {method} timed out after {timeout}s",
                is_retryable=True,
            )

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send notification (no response expected).

        Args:
            method: LSP method name
            params: Notification parameters
        """
        if self._shutting_down:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        await self._send_message(message)

    async def _send_message(self, message: dict[str, Any]) -> None:
        """Send LSP message with proper headers.

        Args:
            message: The message to send

        Raises:
            LSPRequestError: If the process is not started
        """
        if not self.process or not self.process.stdin:
            raise LSPRequestError("Process not started")

        content = json.dumps(message, separators=(",", ":"))
        content_bytes = content.encode("utf-8")

        header = f"{CONTENT_LENGTH_HEADER}{len(content_bytes)}\r\n\r\n"

        self.process.stdin.write(header.encode("utf-8"))
        self.process.stdin.write(content_bytes)
        await self.process.stdin.drain()

        logger.debug(f"Sent: {message}")

    async def _read_loop(self) -> None:
        """Read messages from rust-analyzer."""
        buffer = b""

        while self.process and self.process.stdout and not self._shutting_down:
            try:
                # Read data
                chunk = await self.process.stdout.read(READ_BUFFER_SIZE)
                if not chunk:
                    break

                buffer += chunk

                # Process complete messages
                while True:
                    message, remaining = self._parse_message(buffer)
                    if message is None:
                        buffer = remaining
                        break

                    buffer = remaining
                    await self._handle_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in read loop: {e}", exc_info=True)
                break

    def _parse_message(self, buffer: bytes) -> tuple[dict[str, Any] | None, bytes]:
        """Parse LSP message from buffer.

        Args:
            buffer: The buffer containing potential messages

        Returns:
            Tuple of (parsed_message or None, remaining_buffer)
        """
        # Look for Content-Length header
        header_end = buffer.find(HEADER_SEPARATOR)
        if header_end == -1:
            return None, buffer

        header = buffer[:header_end].decode("utf-8")
        content_start = header_end + len(HEADER_SEPARATOR)

        # Extract content length
        content_length: int | None = None
        for line in header.split("\r\n"):
            if line.startswith(CONTENT_LENGTH_HEADER):
                try:
                    content_length = int(line[len(CONTENT_LENGTH_HEADER) :])
                except ValueError:
                    logger.error(f"Invalid Content-Length value: {line}")
                    return None, buffer[content_start:]
                break

        if content_length is None:
            return None, buffer

        # Check if we have complete content
        if len(buffer) < content_start + content_length:
            return None, buffer

        # Extract and parse content
        content = buffer[content_start : content_start + content_length]
        try:
            message = json.loads(content.decode("utf-8"))
            remaining = buffer[content_start + content_length :]
            return message, remaining
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}", exc_info=True)
            # Skip this message and continue with remaining buffer
            return None, buffer[content_start + content_length :]

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming LSP message.

        Args:
            message: The parsed LSP message
        """
        logger.debug(f"Received: {message}")

        if "id" in message:
            # Response to our request
            request_id = message["id"]
            future = self.pending_requests.pop(request_id, None)

            if future and not future.done():
                if "error" in message:
                    error = message["error"]
                    code = error.get("code")
                    # Determine if error is retryable based on code
                    is_retryable = code in [-32603, -32000, -32001, -32002, -32099]
                    future.set_exception(
                        LSPRequestError(
                            error.get("message", "Unknown error"),
                            code=code,
                            is_retryable=is_retryable,
                        )
                    )
                else:
                    future.set_result(message.get("result"))
        else:
            # Server notification
            method = message.get("method", "")
            params = message.get("params", {})

            # Log all notifications for debugging
            logger.info(f"Notification received: method={method}")

            # Handle progress notifications internally
            if method == LSPMethods.PROGRESS:
                self._handle_progress(params)

            handler = self.notification_handlers.get(method)
            if handler:
                try:
                    await handler(params)
                except Exception as e:
                    logger.error(
                        f"Error in notification handler for {method}: {e}",
                        exc_info=True,
                    )
            elif method != LSPMethods.PROGRESS:
                logger.debug(f"Unhandled notification: {method}")

    async def _stderr_reader(self) -> None:
        """Read stderr output from rust-analyzer."""
        while self.process and self.process.stderr and not self._shutting_down:
            try:
                line = await self.process.stderr.readline()
                if line:
                    decoded = line.decode().strip()
                    # Log at appropriate level based on content
                    if "error" in decoded.lower() or "panic" in decoded.lower():
                        logger.error(f"rust-analyzer stderr: {decoded}")
                    else:
                        logger.info(f"rust-analyzer stderr: {decoded}")
                else:
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading stderr: {e}", exc_info=True)
                break

    def on_notification(self, method: str, handler: Callable[..., Any]) -> None:
        """Register notification handler.

        Args:
            method: LSP method name to handle
            handler: Async callback function
        """
        self.notification_handlers[method] = handler

    def is_initialized(self) -> bool:
        """Check if the client is initialized.

        Returns:
            True if initialized and not shutting down
        """
        return self._initialized and not self._shutting_down

    def is_busy(self) -> bool:
        """Check if rust-analyzer has active progress tasks."""
        return len(self._active_progress) > 0

    def is_ready(self) -> bool:
        """Check if rust-analyzer is ready (progress completed or never started)."""
        return self._ready.is_set()

    def get_progress_status(self) -> dict[str, Any]:
        """Get current progress status.

        Returns:
            Dictionary with progress state information
        """
        return {
            "busy": self.is_busy(),
            "ready": self.is_ready(),
            "activeTasks": list(self._active_progress),
            "message": self._progress_message,
        }

    async def wait_until_ready(self, timeout: float = INDEXING_TIMEOUT) -> bool:
        """Wait for rust-analyzer to be ready (all progress tasks complete).

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if ready, False if timed out
        """
        # If no progress has started yet, wait a bit for it to begin
        if not self._any_progress_started:
            # Give rust-analyzer a moment to start sending progress
            await asyncio.sleep(0.5)
            # If still no progress, assume ready (small project or cached)
            if not self._any_progress_started:
                logger.info("No progress notifications received, assuming ready")
                self._ready.set()
                return True

        if self._ready.is_set():
            return True

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Wait for ready timed out after {timeout}s")
            return False

    def _handle_progress(self, params: dict[str, Any]) -> None:
        """Handle $/progress notifications from rust-analyzer."""
        token = params.get("token", "")
        value = params.get("value", {})
        kind = value.get("kind")

        # Log ALL progress notifications for debugging
        logger.info(f"Progress notification: token={token!r}, kind={kind}")

        # Only track known progress tokens
        if token not in PROGRESS_TOKENS:
            return

        if kind == "begin":
            self._any_progress_started = True
            self._active_progress.add(token)
            self._ready.clear()
            self._progress_message = value.get("message")
            logger.info(f"Progress started: {token}")
        elif kind == "report":
            self._progress_message = value.get("message")
            logger.debug(f"Progress update: {token} - {self._progress_message}")
        elif kind == "end":
            self._active_progress.discard(token)
            logger.info(f"Progress ended: {token}")
            # If no more active progress, mark as ready
            if not self._active_progress:
                self._progress_message = None
                self._ready.set()
                logger.info("rust-analyzer is ready (all progress complete)")

    async def shutdown(self) -> None:
        """Properly shutdown rust-analyzer."""
        if not self.process or self._shutting_down:
            return

        self._shutting_down = True
        logger.info("Shutting down rust-analyzer...")

        # Cancel all pending requests
        for request_id, future in list(self.pending_requests.items()):
            if not future.done():
                future.set_exception(LSPRequestError("Client shutting down"))
        self.pending_requests.clear()

        try:
            # Send shutdown request
            await asyncio.wait_for(
                self.request(LSPMethods.SHUTDOWN, timeout=SHUTDOWN_TIMEOUT),
                timeout=SHUTDOWN_TIMEOUT,
            )

            # Send exit notification
            await self.notify(LSPMethods.EXIT)

            # Wait for process to exit
            await asyncio.wait_for(self.process.wait(), timeout=SHUTDOWN_TIMEOUT)

        except asyncio.TimeoutError:
            logger.warning("Graceful shutdown timed out, terminating process")
            if self.process:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Terminate timed out, killing process")
                    self.process.kill()
                    await self.process.wait()

        except LSPRequestError:
            # Expected if already shutting down
            pass

        except Exception as e:
            logger.error(f"Unexpected error during shutdown: {e}", exc_info=True)
            if self.process:
                self.process.kill()
                await self.process.wait()

        finally:
            # Cancel reader tasks
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass

            if self._stderr_task:
                self._stderr_task.cancel()
                try:
                    await self._stderr_task
                except asyncio.CancelledError:
                    pass

            # Close pipes explicitly
            if self.process:
                if self.process.stdin:
                    self.process.stdin.close()

            self.process = None
            self._initialized = False
            self._shutting_down = False
            logger.info("rust-analyzer shutdown complete")
