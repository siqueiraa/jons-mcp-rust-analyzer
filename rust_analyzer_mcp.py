#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp>=0.3.0",
# ]
# ///

"""
FastMCP server that exposes rust-analyzer LSP features through MCP tools.

This server manages rust-analyzer as a subprocess and translates between MCP and LSP protocols.
It assumes it's launched from a Rust project's root directory and analyzes that specific project.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass
from enum import Enum

from contextlib import asynccontextmanager
from fastmcp import FastMCP, Context

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global rust-analyzer client instance
rust_analyzer: Optional['RustAnalyzerClient'] = None

# Store diagnostics from rust-analyzer
current_diagnostics: Dict[str, List[Dict[str, Any]]] = {}


async def handle_diagnostics(params: Dict[str, Any]):
    """Handle diagnostics notification from rust-analyzer"""
    uri = params.get("uri", "")
    diagnostics = params.get("diagnostics", [])
    current_diagnostics[uri] = diagnostics
    logger.info(f"Received {len(diagnostics)} diagnostics for {uri}")


@asynccontextmanager
async def lifespan(mcp: FastMCP):
    """Manage the lifecycle of the rust-analyzer client"""
    global rust_analyzer
    
    # Startup
    project_root = Path.cwd()
    logger.info(f"Starting MCP server in project: {project_root}")
    
    # Check if this is a Rust project
    if not (project_root / "Cargo.toml").exists():
        logger.warning("No Cargo.toml found in current directory. rust-analyzer may not work correctly.")
    
    rust_analyzer = RustAnalyzerClient(project_root)
    rust_analyzer.on_notification("textDocument/publishDiagnostics", handle_diagnostics)
    
    try:
        await rust_analyzer.start()
    except Exception as e:
        logger.error(f"Failed to start rust-analyzer: {e}")
        raise
    
    yield
    
    # Shutdown
    if rust_analyzer:
        await rust_analyzer.shutdown()
        rust_analyzer = None


# Create FastMCP server instance with lifespan
mcp = FastMCP(
    name="rust-analyzer-mcp",
    lifespan=lifespan
)


class LSPRequestError(Exception):
    """Raised when an LSP request fails"""
    pass


@dataclass
class Position:
    """LSP position in a text document"""
    line: int
    character: int
    
    def to_dict(self) -> Dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass
class Range:
    """LSP range in a text document"""
    start: Position
    end: Position
    
    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


class RustAnalyzerClient:
    """AsyncIO-based LSP client for rust-analyzer"""
    
    def __init__(self, project_root: Path, rust_analyzer_path: Optional[str] = None):
        self.project_root = project_root
        self.rust_analyzer_path = rust_analyzer_path or self._find_rust_analyzer()
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.notification_handlers: Dict[str, Callable] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._shutting_down = False
        
    def _find_rust_analyzer(self) -> str:
        """Find rust-analyzer executable"""
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
            
        raise RuntimeError(
            "rust-analyzer not found. Please install it or set RUST_ANALYZER_PATH"
        )
        
    async def start(self):
        """Start rust-analyzer subprocess"""
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
                cwd=str(self.project_root)
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start rust-analyzer: {e}")
            
        # Start background tasks
        self._reader_task = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._stderr_reader())
        
        # Initialize LSP connection
        await self._initialize()
        
    async def _initialize(self):
        """Send LSP initialize request"""
        response = await self.request("initialize", {
            "processId": os.getpid(),
            "clientInfo": {
                "name": "rust-analyzer-mcp",
                "version": "0.1.0"
            },
            "rootUri": f"file://{self.project_root.absolute()}",
            "capabilities": {
                "textDocument": {
                    "hover": {
                        "contentFormat": ["plaintext", "markdown"]
                    },
                    "completion": {
                        "completionItem": {
                            "snippetSupport": True,
                            "resolveSupport": {
                                "properties": ["documentation", "detail", "additionalTextEdits"]
                            }
                        }
                    },
                    "definition": {"linkSupport": True},
                    "typeDefinition": {"linkSupport": True},
                    "implementation": {"linkSupport": True},
                    "references": {},
                    "documentHighlight": {},
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True
                    },
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
                                    "source.organizeImports"
                                ]
                            }
                        },
                        "resolveSupport": {
                            "properties": ["edit"]
                        }
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True
                    },
                    "callHierarchy": {},
                    "semanticTokens": {
                        "requests": {
                            "full": True,
                            "range": True
                        },
                        "tokenTypes": [],
                        "tokenModifiers": [],
                        "formats": ["relative"]
                    }
                },
                "workspace": {
                    "applyEdit": True,
                    "symbol": {},
                    "executeCommand": {},
                    "workspaceFolders": True,
                    "configuration": True
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
                            "rust-analyzer.ssr"
                        ]
                    }
                }
            },
            "initializationOptions": {
                "cargo": {
                    "features": "all"
                },
                "procMacro": {
                    "enable": True
                },
                "checkOnSave": {
                    "enable": True,
                    "command": "clippy"
                }
            }
        })
        
        logger.info("rust-analyzer initialized successfully")
        self._initialized = True
        
        # Send initialized notification
        await self.notify("initialized", {})
        
        return response
        
    async def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send request and wait for response"""
        if self._shutting_down:
            raise LSPRequestError("Client is shutting down")
            
        self.request_id += 1
        request_id = self.request_id
        
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        # Send request
        await self._send_message(message)
        
        # Wait for response
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise LSPRequestError(f"Request {method} timed out")
            
    async def notify(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send notification (no response expected)"""
        if self._shutting_down:
            return
            
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        await self._send_message(message)
        
    async def _send_message(self, message: Dict[str, Any]):
        """Send LSP message with proper headers"""
        if not self.process or not self.process.stdin:
            raise LSPRequestError("Process not started")
            
        content = json.dumps(message, separators=(',', ':'))
        content_bytes = content.encode('utf-8')
        
        header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
        
        self.process.stdin.write(header.encode('utf-8'))
        self.process.stdin.write(content_bytes)
        await self.process.stdin.drain()
        
        logger.debug(f"Sent: {message}")
        
    async def _read_loop(self):
        """Read messages from rust-analyzer"""
        buffer = b""
        
        while self.process and self.process.stdout and not self._shutting_down:
            try:
                # Read data
                chunk = await self.process.stdout.read(4096)
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
                    
            except Exception as e:
                logger.error(f"Error in read loop: {e}", exc_info=True)
                break
                
    def _parse_message(self, buffer: bytes) -> tuple[Optional[Dict], bytes]:
        """Parse LSP message from buffer"""
        # Look for Content-Length header
        header_end = buffer.find(b"\r\n\r\n")
        if header_end == -1:
            return None, buffer
            
        header = buffer[:header_end].decode('utf-8')
        content_start = header_end + 4
        
        # Extract content length
        content_length = None
        for line in header.split('\r\n'):
            if line.startswith('Content-Length: '):
                content_length = int(line[16:])
                break
                
        if content_length is None:
            return None, buffer
            
        # Check if we have complete content
        if len(buffer) < content_start + content_length:
            return None, buffer
            
        # Extract and parse content
        content = buffer[content_start:content_start + content_length]
        try:
            message = json.loads(content.decode('utf-8'))
            remaining = buffer[content_start + content_length:]
            return message, remaining
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return None, buffer[content_start + content_length:]
            
    async def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming LSP message"""
        logger.debug(f"Received: {message}")
        
        if 'id' in message:
            # Response to our request
            request_id = message['id']
            future = self.pending_requests.pop(request_id, None)
            
            if future and not future.done():
                if 'error' in message:
                    error = message['error']
                    future.set_exception(
                        LSPRequestError(f"{error.get('message', 'Unknown error')} (code: {error.get('code')})")
                    )
                else:
                    future.set_result(message.get('result'))
        else:
            # Server notification
            method = message.get('method', '')
            params = message.get('params', {})
            
            handler = self.notification_handlers.get(method)
            if handler:
                try:
                    await handler(params)
                except Exception as e:
                    logger.error(f"Error in notification handler for {method}: {e}")
            else:
                logger.debug(f"Unhandled notification: {method}")
                
    async def _stderr_reader(self):
        """Read stderr output from rust-analyzer"""
        while self.process and self.process.stderr and not self._shutting_down:
            try:
                line = await self.process.stderr.readline()
                if line:
                    decoded = line.decode().strip()
                    # Log at INFO level so we can see errors during testing
                    if "error" in decoded.lower() or "panic" in decoded.lower():
                        logger.error(f"rust-analyzer stderr: {decoded}")
                    else:
                        logger.info(f"rust-analyzer stderr: {decoded}")
                else:
                    break
            except Exception:
                break
                
    def on_notification(self, method: str, handler: Callable):
        """Register notification handler"""
        self.notification_handlers[method] = handler
        
    async def shutdown(self):
        """Properly shutdown rust-analyzer"""
        if not self.process or self._shutting_down:
            return
            
        self._shutting_down = True
        
        try:
            # Send shutdown request
            await self.request("shutdown")
            
            # Send exit notification
            await self.notify("exit")
            
            # Wait for process to exit
            await asyncio.wait_for(self.process.wait(), timeout=5.0)
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            if self.process:
                self.process.terminate()
                await self.process.wait()
                
        finally:
            # Cancel reader task
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass
                    
            self.process = None
            self._initialized = False
            self._shutting_down = False




def ensure_file_uri(file_path: str) -> str:
    """Convert file path to proper file URI"""
    if file_path.startswith("file://"):
        return file_path
    
    path = Path(file_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    
    return f"file://{path.absolute()}"


def ensure_rust_analyzer() -> RustAnalyzerClient:
    """Ensure rust-analyzer is initialized"""
    if not rust_analyzer or not rust_analyzer._initialized:
        raise RuntimeError("rust-analyzer is not initialized")
    return rust_analyzer


# MCP Tools - Core Language Features

@mcp.tool
async def hover(file_path: str, line: int, character: int, ctx: Context) -> Dict[str, Any]:
    """Get hover information at the specified position in a Rust file.
    
    Args:
        file_path: Path to the Rust file (absolute or relative)
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        Hover information including type info, documentation, etc.
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Getting hover info at {file_path}:{line}:{character}")
    
    response = await client.request("textDocument/hover", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    if not response:
        return {"contents": "No hover information available"}
        
    return response


@mcp.tool
async def completion(file_path: str, line: int, character: int, ctx: Context) -> List[Dict[str, Any]]:
    """Get code completions at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        List of completion items with labels, kinds, and documentation
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Getting completions at {file_path}:{line}:{character}")
    
    response = await client.request("textDocument/completion", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    # Handle both array and CompletionList responses
    if isinstance(response, list):
        return response
    elif isinstance(response, dict) and "items" in response:
        return response["items"]
    else:
        return []


@mcp.tool
async def definition(file_path: str, line: int, character: int, ctx: Context) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Go to definition of the symbol at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        Location(s) of the definition
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Finding definition at {file_path}:{line}:{character}")
    
    response = await client.request("textDocument/definition", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    return response or {"message": "No definition found"}


@mcp.tool
async def type_definition(file_path: str, line: int, character: int, ctx: Context) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Go to type definition of the symbol at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        Location(s) of the type definition
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Finding type definition at {file_path}:{line}:{character}")
    
    response = await client.request("textDocument/typeDefinition", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    return response or {"message": "No type definition found"}


@mcp.tool
async def implementation(file_path: str, line: int, character: int, ctx: Context) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Find implementations of the trait/type at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        Location(s) of implementations
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Finding implementations at {file_path}:{line}:{character}")
    
    response = await client.request("textDocument/implementation", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    return response or {"message": "No implementations found"}


@mcp.tool
async def references(file_path: str, line: int, character: int, include_declaration: bool = True, ctx: Context = None) -> List[Dict[str, Any]]:
    """Find all references to the symbol at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        include_declaration: Whether to include the declaration itself
        
    Returns:
        List of reference locations
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    if ctx:
        await ctx.info(f"Finding references at {file_path}:{line}:{character}")
    
    response = await client.request("textDocument/references", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character},
        "context": {"includeDeclaration": include_declaration}
    })
    
    return response or []


@mcp.tool
async def document_symbols(file_path: str, ctx: Context) -> List[Dict[str, Any]]:
    """Get all symbols in a document (functions, structs, traits, etc.).
    
    Args:
        file_path: Path to the Rust file
        
    Returns:
        Hierarchical list of symbols in the document
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Getting document symbols for {file_path}")
    
    response = await client.request("textDocument/documentSymbol", {
        "textDocument": {"uri": file_uri}
    })
    
    return response or []


@mcp.tool
async def workspace_symbols(query: str, ctx: Context) -> List[Dict[str, Any]]:
    """Search for symbols across the entire workspace.
    
    Args:
        query: Search query (can be partial name)
        
    Returns:
        List of matching symbols with their locations
    """
    client = ensure_rust_analyzer()
    
    await ctx.info(f"Searching workspace symbols: {query}")
    
    response = await client.request("workspace/symbol", {
        "query": query
    })
    
    return response or []


# MCP Tools - Code Intelligence

@mcp.tool
async def diagnostics(file_path: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Get current diagnostics (errors, warnings) for file(s).
    
    Args:
        file_path: Optional path to specific file. If None, returns all diagnostics.
        
    Returns:
        Dictionary mapping file URIs to their diagnostics
    """
    if file_path:
        file_uri = ensure_file_uri(file_path)
        return {file_uri: current_diagnostics.get(file_uri, [])}
    else:
        return current_diagnostics


@mcp.tool
async def code_actions(file_path: str, start_line: int, start_char: int, end_line: int, end_char: int, ctx: Context) -> List[Dict[str, Any]]:
    """Get available code actions (fixes, refactorings) for a range.
    
    Args:
        file_path: Path to the Rust file
        start_line: Start line (zero-based)
        start_char: Start character (zero-based)
        end_line: End line (zero-based)
        end_char: End character (zero-based)
        
    Returns:
        List of available code actions
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Getting code actions for {file_path}")
    
    # Get diagnostics for this range
    file_diagnostics = current_diagnostics.get(file_uri, [])
    
    response = await client.request("textDocument/codeAction", {
        "textDocument": {"uri": file_uri},
        "range": {
            "start": {"line": start_line, "character": start_char},
            "end": {"line": end_line, "character": end_char}
        },
        "context": {
            "diagnostics": file_diagnostics
        }
    })
    
    return response or []


@mcp.tool
async def rename(file_path: str, line: int, character: int, new_name: str, ctx: Context) -> Dict[str, Any]:
    """Rename a symbol and all its references.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        new_name: New name for the symbol
        
    Returns:
        WorkspaceEdit with all changes needed
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Renaming symbol at {file_path}:{line}:{character} to '{new_name}'")
    
    # First check if rename is valid
    try:
        prepare_result = await client.request("textDocument/prepareRename", {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character}
        })
        
        if not prepare_result:
            return {"error": "Cannot rename at this position"}
            
    except LSPRequestError:
        return {"error": "Cannot rename at this position"}
    
    # Perform rename
    response = await client.request("textDocument/rename", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character},
        "newName": new_name
    })
    
    return response or {"changes": {}}


@mcp.tool
async def semantic_tokens(file_path: str, ctx: Context) -> Dict[str, Any]:
    """Get semantic tokens for syntax highlighting.
    
    Args:
        file_path: Path to the Rust file
        
    Returns:
        Semantic tokens data
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Getting semantic tokens for {file_path}")
    
    response = await client.request("textDocument/semanticTokens/full", {
        "textDocument": {"uri": file_uri}
    })
    
    return response or {"data": []}


# MCP Tools - Formatting

@mcp.tool
async def format_document(file_path: str, tab_size: int = 4, insert_spaces: bool = True, ctx: Context = None) -> List[Dict[str, Any]]:
    """Format an entire Rust document.
    
    Args:
        file_path: Path to the Rust file
        tab_size: Size of a tab in spaces
        insert_spaces: Use spaces instead of tabs
        
    Returns:
        List of text edits to apply
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    if ctx:
        await ctx.info(f"Formatting {file_path}")
    
    response = await client.request("textDocument/formatting", {
        "textDocument": {"uri": file_uri},
        "options": {
            "tabSize": tab_size,
            "insertSpaces": insert_spaces
        }
    })
    
    return response or []


@mcp.tool
async def format_range(file_path: str, start_line: int, start_char: int, end_line: int, end_char: int, 
                      tab_size: int = 4, insert_spaces: bool = True, ctx: Context = None) -> List[Dict[str, Any]]:
    """Format a range in a Rust document.
    
    Args:
        file_path: Path to the Rust file
        start_line: Start line (zero-based)
        start_char: Start character (zero-based)
        end_line: End line (zero-based)
        end_char: End character (zero-based)
        tab_size: Size of a tab in spaces
        insert_spaces: Use spaces instead of tabs
        
    Returns:
        List of text edits to apply
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    if ctx:
        await ctx.info(f"Formatting range in {file_path}")
    
    response = await client.request("textDocument/rangeFormatting", {
        "textDocument": {"uri": file_uri},
        "range": {
            "start": {"line": start_line, "character": start_char},
            "end": {"line": end_line, "character": end_char}
        },
        "options": {
            "tabSize": tab_size,
            "insertSpaces": insert_spaces
        }
    })
    
    return response or []


# MCP Tools - rust-analyzer Extensions

@mcp.tool
async def expand_macro(file_path: str, line: int, character: int, ctx: Context) -> Dict[str, Any]:
    """Expand a Rust macro at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        Expanded macro code
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Expanding macro at {file_path}:{line}:{character}")
    
    response = await client.request("rust-analyzer/expandMacro", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    return response or {"expansion": "No macro found at this position"}


@mcp.tool
async def syntax_tree(file_path: str, start_line: Optional[int] = None, start_char: Optional[int] = None,
                     end_line: Optional[int] = None, end_char: Optional[int] = None, ctx: Context = None) -> str:
    """Get the syntax tree for a file or range.
    
    Args:
        file_path: Path to the Rust file
        start_line: Optional start line for range
        start_char: Optional start character for range
        end_line: Optional end line for range
        end_char: Optional end character for range
        
    Returns:
        Syntax tree as a string
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    if ctx:
        await ctx.info(f"Getting syntax tree for {file_path}")
    
    params = {"textDocument": {"uri": file_uri}}
    
    # Add range if specified
    if all(x is not None for x in [start_line, start_char, end_line, end_char]):
        params["range"] = {
            "start": {"line": start_line, "character": start_char},
            "end": {"line": end_line, "character": end_char}
        }
    
    response = await client.request("rust-analyzer/syntaxTree", params)
    
    return response if isinstance(response, str) else "No syntax tree available"


@mcp.tool
async def analyzer_status(ctx: Context) -> str:
    """Get the current status of rust-analyzer.
    
    Returns:
        Status information as a string
    """
    client = ensure_rust_analyzer()
    
    await ctx.info("Getting rust-analyzer status")
    
    response = await client.request("rust-analyzer/analyzerStatus", {})
    
    return response if isinstance(response, str) else "Status unavailable"


@mcp.tool
async def view_crate_graph(ctx: Context) -> str:
    """Get the crate dependency graph.
    
    Returns:
        Crate graph in Graphviz DOT format
    """
    client = ensure_rust_analyzer()
    
    await ctx.info("Getting crate graph")
    
    response = await client.request("rust-analyzer/viewCrateGraph", {})
    
    return response if isinstance(response, str) else "Crate graph unavailable"


@mcp.tool
async def related_tests(file_path: str, line: int, character: int, ctx: Context) -> List[Dict[str, Any]]:
    """Find tests related to the code at the specified position.
    
    Args:
        file_path: Path to the Rust file
        line: Zero-based line number
        character: Zero-based character offset in the line
        
    Returns:
        List of related test locations
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    await ctx.info(f"Finding related tests at {file_path}:{line}:{character}")
    
    response = await client.request("rust-analyzer/relatedTests", {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    })
    
    return response or []


@mcp.tool
async def runnables(file_path: str, line: Optional[int] = None, character: Optional[int] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """Get runnable items (tests, binaries, examples) in a file.
    
    Args:
        file_path: Path to the Rust file
        line: Optional line number to find runnable at specific position
        character: Optional character offset
        
    Returns:
        List of runnable items with their configurations
    """
    client = ensure_rust_analyzer()
    file_uri = ensure_file_uri(file_path)
    
    if ctx:
        await ctx.info(f"Getting runnables for {file_path}")
    
    params = {"textDocument": {"uri": file_uri}}
    
    if line is not None and character is not None:
        params["position"] = {"line": line, "character": character}
    
    response = await client.request("rust-analyzer/runnables", params)
    
    return response or []


@mcp.tool
async def ssr(pattern: str, template: str, ctx: Context) -> Dict[str, Any]:
    """Perform structural search and replace across the workspace.
    
    Args:
        pattern: Search pattern using rust-analyzer SSR syntax
        template: Replacement template
        
    Returns:
        WorkspaceEdit with all replacements
    """
    client = ensure_rust_analyzer()
    
    await ctx.info(f"Performing SSR: {pattern} -> {template}")
    
    response = await client.request("experimental/ssr", {
        "query": pattern,
        "template": template
    })
    
    return response or {"changes": {}}


# Signal handling for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


# Main entry point
if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the MCP server
    mcp.run()