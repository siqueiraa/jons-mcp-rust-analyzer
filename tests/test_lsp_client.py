"""
Unit tests for the RustAnalyzerClient class.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from rust_analyzer_mcp import RustAnalyzerClient, LSPRequestError, Position, Range


class TestRustAnalyzerClient:
    """Test the RustAnalyzerClient class."""
    
    def test_find_rust_analyzer_env_var(self, tmp_path: Path, monkeypatch):
        """Test finding rust-analyzer via environment variable."""
        fake_path = str(tmp_path / "rust-analyzer")
        monkeypatch.setenv("RUST_ANALYZER_PATH", fake_path)
        
        client = RustAnalyzerClient(tmp_path)
        assert client.rust_analyzer_path == fake_path
    
    def test_find_rust_analyzer_on_path(self, tmp_path: Path, monkeypatch):
        """Test finding rust-analyzer on PATH."""
        monkeypatch.delenv("RUST_ANALYZER_PATH", raising=False)
        
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rust-analyzer"
            client = RustAnalyzerClient(tmp_path)
            assert client.rust_analyzer_path == "/usr/bin/rust-analyzer"
    
    def test_find_rust_analyzer_cargo_bin(self, tmp_path: Path, monkeypatch):
        """Test finding rust-analyzer in cargo bin."""
        monkeypatch.delenv("RUST_ANALYZER_PATH", raising=False)
        
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = True
                client = RustAnalyzerClient(tmp_path)
                assert "cargo/bin/rust-analyzer" in client.rust_analyzer_path
    
    def test_find_rust_analyzer_not_found(self, tmp_path: Path, monkeypatch):
        """Test error when rust-analyzer is not found."""
        monkeypatch.delenv("RUST_ANALYZER_PATH", raising=False)
        
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = False
                with pytest.raises(RuntimeError, match="rust-analyzer not found"):
                    RustAnalyzerClient(tmp_path)
    
    @pytest.mark.asyncio
    async def test_start_process(self, tmp_path: Path):
        """Test starting the rust-analyzer process."""
        client = RustAnalyzerClient(tmp_path, rust_analyzer_path="echo")
        
        # Mock the subprocess
        mock_process = AsyncMock()
        mock_process.stdin = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            # Mock the initialization
            with patch.object(client, "_initialize", new_callable=AsyncMock):
                with patch.object(client, "_read_loop", new_callable=AsyncMock):
                    with patch.object(client, "_stderr_reader", new_callable=AsyncMock):
                        await client.start()
        
        mock_exec.assert_called_once_with(
            "echo",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(tmp_path)
        )
        assert client.process == mock_process
    
    @pytest.mark.asyncio
    async def test_send_message(self, tmp_path: Path):
        """Test sending LSP messages."""
        client = RustAnalyzerClient(tmp_path)
        
        # Mock process with stdin
        mock_stdin = AsyncMock()
        client.process = MagicMock()
        client.process.stdin = mock_stdin
        
        message = {"jsonrpc": "2.0", "method": "test", "params": {}}
        await client._send_message(message)
        
        # Check that proper LSP format was written
        calls = mock_stdin.write.call_args_list
        assert len(calls) == 2  # header + content
        
        # Check header
        header = calls[0][0][0].decode('utf-8')
        assert header.startswith("Content-Length: ")
        assert header.endswith("\r\n\r\n")
        
        # Check content
        content = calls[1][0][0].decode('utf-8')
        assert json.loads(content) == message
    
    def test_parse_message_complete(self, tmp_path: Path):
        """Test parsing a complete LSP message."""
        client = RustAnalyzerClient(tmp_path)
        
        message = {"jsonrpc": "2.0", "id": 1, "result": {"test": "value"}}
        content = json.dumps(message)
        content_bytes = content.encode('utf-8')
        
        buffer = f"Content-Length: {len(content_bytes)}\r\n\r\n".encode('utf-8') + content_bytes
        
        parsed, remaining = client._parse_message(buffer)
        assert parsed == message
        assert remaining == b""
    
    def test_parse_message_incomplete_header(self, tmp_path: Path):
        """Test parsing with incomplete header."""
        client = RustAnalyzerClient(tmp_path)
        
        buffer = b"Content-Length: 42\r\n"  # Missing \r\n
        
        parsed, remaining = client._parse_message(buffer)
        assert parsed is None
        assert remaining == buffer
    
    def test_parse_message_incomplete_content(self, tmp_path: Path):
        """Test parsing with incomplete content."""
        client = RustAnalyzerClient(tmp_path)
        
        buffer = b"Content-Length: 100\r\n\r\n{\"test\": "  # Content too short
        
        parsed, remaining = client._parse_message(buffer)
        assert parsed is None
        assert remaining == buffer
    
    def test_parse_message_multiple(self, tmp_path: Path):
        """Test parsing multiple messages in buffer."""
        client = RustAnalyzerClient(tmp_path)
        
        message1 = {"jsonrpc": "2.0", "id": 1, "result": {}}
        content1 = json.dumps(message1).encode('utf-8')
        
        message2 = {"jsonrpc": "2.0", "method": "test"}
        content2 = json.dumps(message2).encode('utf-8')
        
        buffer = (
            f"Content-Length: {len(content1)}\r\n\r\n".encode('utf-8') + content1 +
            f"Content-Length: {len(content2)}\r\n\r\n".encode('utf-8') + content2
        )
        
        # Parse first message
        parsed1, remaining1 = client._parse_message(buffer)
        assert parsed1 == message1
        
        # Parse second message
        parsed2, remaining2 = client._parse_message(remaining1)
        assert parsed2 == message2
        assert remaining2 == b""
    
    @pytest.mark.asyncio
    async def test_handle_response(self, tmp_path: Path):
        """Test handling response messages."""
        client = RustAnalyzerClient(tmp_path)
        
        # Create a pending request
        future = asyncio.Future()
        client.pending_requests[42] = future
        
        # Handle response
        response = {"jsonrpc": "2.0", "id": 42, "result": {"data": "test"}}
        await client._handle_message(response)
        
        assert future.done()
        assert future.result() == {"data": "test"}
        assert 42 not in client.pending_requests
    
    @pytest.mark.asyncio
    async def test_handle_error_response(self, tmp_path: Path):
        """Test handling error responses."""
        client = RustAnalyzerClient(tmp_path)
        
        # Create a pending request
        future = asyncio.Future()
        client.pending_requests[42] = future
        
        # Handle error response
        response = {
            "jsonrpc": "2.0",
            "id": 42,
            "error": {"code": -32601, "message": "Method not found"}
        }
        await client._handle_message(response)
        
        assert future.done()
        with pytest.raises(LSPRequestError, match="Method not found"):
            future.result()
    
    @pytest.mark.asyncio
    async def test_handle_notification(self, tmp_path: Path):
        """Test handling notification messages."""
        client = RustAnalyzerClient(tmp_path)
        
        # Register notification handler
        handler_called = False
        async def handler(params):
            nonlocal handler_called
            handler_called = True
            assert params == {"uri": "file:///test.rs"}
        
        client.on_notification("textDocument/publishDiagnostics", handler)
        
        # Handle notification
        notification = {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": "file:///test.rs"}
        }
        await client._handle_message(notification)
        
        assert handler_called
    
    @pytest.mark.asyncio
    async def test_request_timeout(self, tmp_path: Path):
        """Test request timeout handling."""
        client = RustAnalyzerClient(tmp_path)
        client.process = MagicMock()
        client.process.stdin = AsyncMock()
        
        # Make a request that will timeout (override internal timeout)
        original_timeout = 30.0
        with patch("rust_analyzer_mcp.asyncio.wait_for") as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()
            with pytest.raises(LSPRequestError, match="timed out"):
                await client.request("test")
        
        # Ensure request is cleaned up
        assert len(client.pending_requests) == 0
    
    @pytest.mark.asyncio
    async def test_shutdown(self, tmp_path: Path):
        """Test proper shutdown sequence."""
        client = RustAnalyzerClient(tmp_path)
        
        # Mock process and methods
        mock_process = AsyncMock()
        mock_process.wait = AsyncMock()
        client.process = mock_process
        
        # Mock reader task as an actual asyncio task
        async def dummy_reader():
            await asyncio.sleep(100)  # Never completes
        
        reader_task = asyncio.create_task(dummy_reader())
        client._reader_task = reader_task
        
        # Mock request and notify methods
        with patch.object(client, "request", new_callable=AsyncMock) as mock_request:
            with patch.object(client, "notify", new_callable=AsyncMock) as mock_notify:
                await client.shutdown()
        
        # Verify shutdown sequence
        mock_request.assert_called_once_with("shutdown")
        mock_notify.assert_called_once_with("exit")
        mock_process.wait.assert_called_once()
        assert reader_task.cancelled()  # Task should be cancelled
        assert client.process is None
        assert client._initialized is False
    
    @pytest.mark.asyncio
    async def test_shutdown_with_error(self, tmp_path: Path):
        """Test shutdown with errors."""
        client = RustAnalyzerClient(tmp_path)
        
        # Mock process
        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock()
        client.process = mock_process
        
        # Mock request to raise error
        with patch.object(client, "request", side_effect=Exception("Shutdown failed")):
            await client.shutdown()
        
        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()


class TestPositionAndRange:
    """Test Position and Range dataclasses."""
    
    def test_position_to_dict(self):
        """Test Position.to_dict()."""
        pos = Position(line=10, character=5)
        assert pos.to_dict() == {"line": 10, "character": 5}
    
    def test_range_to_dict(self):
        """Test Range.to_dict()."""
        start = Position(line=10, character=5)
        end = Position(line=10, character=10)
        range_obj = Range(start=start, end=end)
        
        assert range_obj.to_dict() == {
            "start": {"line": 10, "character": 5},
            "end": {"line": 10, "character": 10}
        }