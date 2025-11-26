"""
Integration tests for MCP tools that interact with rust-analyzer.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.jons_mcp_rust_analyzer import server as server_module
from src.jons_mcp_rust_analyzer import tools
from src.jons_mcp_rust_analyzer.exceptions import (
    LSPRequestError,
    RustAnalyzerNotInitializedError,
)
from src.jons_mcp_rust_analyzer.utils import ensure_file_uri


class TestHelperFunctions:
    """Test helper functions."""

    def test_ensure_file_uri_already_uri(self) -> None:
        """Test ensure_file_uri with existing URI."""
        uri = "file:///home/user/project/src/main.rs"
        assert ensure_file_uri(uri) == uri

    def test_ensure_file_uri_absolute_path(self) -> None:
        """Test ensure_file_uri with absolute path."""
        path = "/home/user/project/src/main.rs"
        result = ensure_file_uri(path)
        assert result == f"file://{path}"

    def test_ensure_file_uri_relative_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test ensure_file_uri with relative path."""
        monkeypatch.chdir(tmp_path)

        result = ensure_file_uri("src/main.rs")
        expected = f"file://{tmp_path}/src/main.rs"
        assert result == expected

    def test_ensure_rust_analyzer_not_initialized(self) -> None:
        """Test ensure_rust_analyzer when not initialized."""
        # Clear global client
        server_module.rust_analyzer = None

        with pytest.raises(
            RustAnalyzerNotInitializedError, match="rust-analyzer"
        ):
            server_module.ensure_rust_analyzer()

    def test_ensure_rust_analyzer_initialized(self) -> None:
        """Test ensure_rust_analyzer when initialized."""
        # Mock global client
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        server_module.rust_analyzer = mock_client

        result = server_module.ensure_rust_analyzer()
        assert result == mock_client


@pytest.mark.asyncio
class TestLanguageFeatureTools:
    """Test core language feature MCP tools."""

    async def test_hover_tool(self) -> None:
        """Test hover tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value={
                "contents": {"kind": "markdown", "value": "```rust\nfn test()\n```"}
            }
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.hover("src/main.rs", 10, 5, ctx)

        assert "contents" in result
        # Check that the request was made with an absolute path
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "textDocument/hover"
        assert call_args[0][1]["textDocument"]["uri"].endswith("/src/main.rs")
        assert call_args[0][1]["position"] == {"line": 10, "character": 5}

    async def test_completion_tool(self) -> None:
        """Test completion tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {"label": "println!", "kind": 15, "documentation": "Large docs"},
                {"label": "print!", "kind": 15, "detail": "macro_rules! print"},
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.completion(
                "src/main.rs",
                5,
                10,
                limit=50,
                offset=0,
                include_detail=False,
                include_documentation=False,
                ctx=ctx,
            )

        assert isinstance(result, dict)
        assert len(result["items"]) == 2
        assert result["items"][0]["label"] == "print!"  # Sorted alphabetically
        assert result["items"][1]["label"] == "println!"
        assert result["items"][0]["kind"] == 15
        assert result["items"][0]["offset"] == 0
        assert result["items"][1]["offset"] == 1
        assert "documentation" not in result["items"][0]  # Should not be included
        assert "detail" not in result["items"][1]  # Should not be included
        assert result["totalItems"] == 2
        assert not result["hasMore"]
        assert result["offset"] == 0

    async def test_completion_tool_with_completion_list(self) -> None:
        """Test completion tool with CompletionList response."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        # Simulate a large completion list that would be limited
        items = [
            {"label": f"test_{i}", "kind": 6, "documentation": f"Docs for test_{i}"}
            for i in range(100)
        ]
        mock_client.request = AsyncMock(
            return_value={"isIncomplete": True, "items": items}
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            # Test first page with detail but no documentation
            result = await tools.completion(
                "src/main.rs",
                5,
                10,
                limit=20,
                offset=0,
                include_detail=True,
                include_documentation=False,
                ctx=ctx,
            )

        assert isinstance(result, dict)
        assert len(result["items"]) == 20  # Limited to 20
        assert result["items"][0]["label"] == "test_0"
        assert result["items"][0]["offset"] == 0
        assert "documentation" not in result["items"][0]  # Not included
        assert result["totalItems"] == 100
        assert result["hasMore"]
        assert result["nextOffset"] == 20

        # Test getting specific item using offset
        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            # Get single item at offset 42
            result_single = await tools.completion(
                "src/main.rs",
                5,
                10,
                limit=1,
                offset=42,
                include_detail=True,
                include_documentation=True,
                ctx=ctx,
            )

        assert len(result_single["items"]) == 1
        # Items are sorted, so we get whatever is at position 42 after sorting
        assert result_single["items"][0]["label"].startswith("test_")
        assert result_single["items"][0]["offset"] == 42
        assert "documentation" in result_single["items"][0]  # Included
        assert result_single["offset"] == 42
        assert result_single["hasMore"]  # More items after this one

    async def test_definition_tool(self) -> None:
        """Test definition tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value={
                "uri": "file:///src/lib.rs",
                "range": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 15, "character": 1},
                },
            }
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.definition("src/main.rs", 20, 15, ctx)

        assert result["uri"] == "file:///src/lib.rs"

    async def test_references_tool(self) -> None:
        """Test references tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {
                    "uri": "file:///src/main.rs",
                    "range": {"start": {"line": 10, "character": 5}},
                },
                {
                    "uri": "file:///src/lib.rs",
                    "range": {"start": {"line": 20, "character": 10}},
                },
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.references(
                "src/main.rs",
                10,
                5,
                include_declaration=True,
                limit=50,
                offset=0,
                ctx=ctx,
            )

        assert isinstance(result, dict)
        assert len(result["items"]) == 2
        assert result["items"][0]["offset"] == 0
        assert result["items"][1]["offset"] == 1
        assert result["totalItems"] == 2
        assert not result["hasMore"]
        # Check that the request was made with correct parameters
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "textDocument/references"
        assert call_args[0][1]["textDocument"]["uri"].endswith("/src/main.rs")
        assert call_args[0][1]["position"] == {"line": 10, "character": 5}
        assert call_args[0][1]["context"] == {"includeDeclaration": True}

    async def test_document_symbols_tool(self) -> None:
        """Test document symbols tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {
                    "name": "main",
                    "kind": 12,  # Function
                    "range": {"start": {"line": 0, "character": 0}},
                    "selectionRange": {"start": {"line": 0, "character": 3}},
                }
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.document_symbols(
                "src/main.rs", limit=50, offset=0, ctx=ctx
            )

        assert isinstance(result, dict)
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "main"
        assert result["items"][0]["fullName"] == "main"
        assert result["items"][0]["offset"] == 0
        assert result["totalItems"] == 1
        assert not result["hasMore"]

    async def test_workspace_symbols_tool(self) -> None:
        """Test workspace symbols tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {
                    "name": "Calculator",
                    "kind": 5,  # Class
                    "location": {
                        "uri": "file:///src/lib.rs",
                        "range": {"start": {"line": 10, "character": 0}},
                    },
                }
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.workspace_symbols("Calc", limit=50, offset=0, ctx=ctx)

        assert isinstance(result, dict)
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "Calculator"
        assert result["items"][0]["offset"] == 0
        assert result["totalItems"] == 1
        assert not result["hasMore"]


@pytest.mark.asyncio
class TestCodeIntelligenceTools:
    """Test code intelligence MCP tools."""

    async def test_diagnostics_tool_all_files(self) -> None:
        """Test diagnostics tool for all files."""
        server_module.current_diagnostics.clear()
        server_module.current_diagnostics["file:///src/main.rs"] = [
            {
                "severity": 1,
                "message": "Error 1",
                "range": {"start": {"line": 5, "character": 0}},
            }
        ]
        server_module.current_diagnostics["file:///src/lib.rs"] = [
            {
                "severity": 2,
                "message": "Warning 1",
                "range": {"start": {"line": 10, "character": 0}},
            }
        ]

        result = await tools.diagnostics(limit=50, offset=0)
        assert isinstance(result, dict)
        assert len(result["items"]) == 2
        # Error comes first due to severity sorting
        assert result["items"][0]["severity"] == 1
        assert result["items"][0]["uri"] == "file:///src/main.rs"
        assert result["items"][0]["offset"] == 0
        assert result["items"][1]["severity"] == 2
        assert result["items"][1]["offset"] == 1
        assert result["totalItems"] == 2
        assert not result["hasMore"]

    async def test_diagnostics_tool_specific_file(self) -> None:
        """Test diagnostics tool for specific file."""
        # Use absolute path for test
        test_file = "/test/src/main.rs"
        server_module.current_diagnostics.clear()
        server_module.current_diagnostics[f"file://{test_file}"] = [
            {
                "severity": 1,
                "message": "Error 1",
                "range": {"start": {"line": 0, "character": 0}},
            }
        ]
        server_module.current_diagnostics["file:///test/src/lib.rs"] = []

        # Mock ensure_file_uri to return the expected URI
        with patch(
            "src.jons_mcp_rust_analyzer.tools.intelligence.ensure_file_uri",
            return_value=f"file://{test_file}",
        ):
            result = await tools.diagnostics(test_file, limit=50, offset=0)

        assert isinstance(result, dict)
        assert len(result["items"]) == 1
        assert result["items"][0]["message"] == "Error 1"
        assert result["items"][0]["uri"] == f"file://{test_file}"
        assert result["items"][0]["offset"] == 0
        assert result["totalItems"] == 1
        assert not result["hasMore"]

    async def test_code_actions_tool(self) -> None:
        """Test code actions tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {"title": "Import `std::io`", "kind": "quickfix", "edit": {"changes": {}}}
            ]
        )

        server_module.current_diagnostics.clear()
        server_module.current_diagnostics["file:///src/main.rs"] = [{"severity": 1}]

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.code_actions("src/main.rs", 10, 0, 10, 20, ctx)

        assert len(result) == 1
        assert result[0]["title"] == "Import `std::io`"

    async def test_rename_tool(self) -> None:
        """Test rename tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True

        # Mock prepare rename
        mock_client.request = AsyncMock()
        mock_client.request.side_effect = [
            {"range": {"start": {"line": 10, "character": 5}}},  # prepareRename
            {"changes": {"file:///src/main.rs": []}},  # rename
        ]

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.rename("src/main.rs", 10, 5, "new_name", ctx)

        assert "changes" in result
        assert mock_client.request.call_count == 2

    async def test_rename_tool_invalid_position(self) -> None:
        """Test rename tool at invalid position."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(side_effect=LSPRequestError("Cannot rename"))

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.rename("src/main.rs", 10, 5, "new_name", ctx)

        assert result == {"error": "Cannot rename at this position"}


@pytest.mark.asyncio
class TestFormattingTools:
    """Test formatting MCP tools."""

    async def test_format_document_tool(self) -> None:
        """Test format document tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 10},
                    },
                    "newText": "formatted code",
                }
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.format_document(
                "src/main.rs", tab_size=4, insert_spaces=True, ctx=ctx
            )

        assert len(result) == 1
        assert result[0]["newText"] == "formatted code"

    async def test_format_range_tool(self) -> None:
        """Test format range tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(return_value=[])

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.format_range("src/main.rs", 10, 0, 20, 0, ctx=ctx)

        assert result == []
        mock_client.request.assert_called_once()


@pytest.mark.asyncio
class TestRustAnalyzerExtensions:
    """Test rust-analyzer specific extension tools."""

    async def test_expand_macro_tool(self) -> None:
        """Test expand macro tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value={"name": "println", "expansion": 'std::io::println("Hello")'}
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.expand_macro("src/main.rs", 10, 5, ctx)

        assert "expansion" in result

    async def test_analyzer_status_tool(self) -> None:
        """Test analyzer status tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(return_value="Analyzer: ready\nMemory: 100MB")
        mock_client.get_indexing_status.return_value = {
            "indexing": False,
            "complete": True,
            "percentage": 100,
            "message": None,
        }

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.analyzer_status(ctx)

        assert "Analyzer: ready" in result["internalStatus"]
        assert result["indexing"]["complete"] is True

    async def test_related_tests_tool(self) -> None:
        """Test related tests tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {
                    "uri": "file:///src/main.rs",
                    "range": {"start": {"line": 50, "character": 0}},
                }
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.related_tests("src/main.rs", 10, 5, ctx)

        assert len(result) == 1

    async def test_runnables_tool(self) -> None:
        """Test runnables tool."""
        mock_client = MagicMock()
        mock_client.is_initialized.return_value = True
        mock_client.request = AsyncMock(
            return_value=[
                {
                    "label": "test test_add",
                    "kind": "test",
                    "args": {"cargoArgs": ["test", "test_add"], "executableArgs": []},
                }
            ]
        )

        with patch.object(server_module, "rust_analyzer", mock_client):
            ctx = AsyncMock()
            result = await tools.runnables("src/main.rs", ctx=ctx)

        assert len(result) == 1
        assert result[0]["label"] == "test test_add"


@pytest.mark.asyncio
class TestServerLifecycle:
    """Test MCP server lifecycle."""

    async def test_lifespan_with_cargo_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test lifespan with Cargo.toml present."""
        monkeypatch.chdir(tmp_path)

        # Create a Cargo.toml
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        mock_client_class = MagicMock()
        mock_client = AsyncMock()
        mock_client.start = AsyncMock()
        mock_client.shutdown = AsyncMock()
        mock_client.on_notification = MagicMock()
        mock_client_class.return_value = mock_client

        with patch(
            "src.jons_mcp_rust_analyzer.server.RustAnalyzerClient", mock_client_class
        ):
            # Use the lifespan context manager
            async with server_module.lifespan(None):
                assert server_module.rust_analyzer == mock_client
                mock_client.start.assert_called_once()

            # After exiting, should be shutdown
            mock_client.shutdown.assert_called_once()
            assert server_module.rust_analyzer is None

    async def test_lifespan_no_cargo_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test lifespan without Cargo.toml."""
        monkeypatch.chdir(tmp_path)

        mock_client_class = MagicMock()
        mock_client = AsyncMock()
        mock_client.start = AsyncMock()
        mock_client.shutdown = AsyncMock()
        mock_client.on_notification = MagicMock()
        mock_client_class.return_value = mock_client

        with patch(
            "src.jons_mcp_rust_analyzer.server.RustAnalyzerClient", mock_client_class
        ):
            with patch.object(server_module, "logger") as mock_logger:
                async with server_module.lifespan(None):
                    # Should log warning
                    mock_logger.warning.assert_called_once()

    async def test_lifespan_start_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test lifespan when rust-analyzer fails to start."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        mock_client_class = MagicMock()
        mock_client = AsyncMock()
        mock_client.start = AsyncMock(side_effect=Exception("Failed to start"))
        mock_client.on_notification = MagicMock()
        mock_client_class.return_value = mock_client

        with patch(
            "src.jons_mcp_rust_analyzer.server.RustAnalyzerClient", mock_client_class
        ):
            with pytest.raises(Exception, match="Failed to start"):
                async with server_module.lifespan(None):
                    pass


class TestNotificationHandlers:
    """Test notification handlers."""

    @pytest.mark.asyncio
    async def test_handle_diagnostics(self) -> None:
        """Test diagnostics notification handler."""
        server_module.current_diagnostics.clear()

        params = {
            "uri": "file:///src/main.rs",
            "diagnostics": [
                {"severity": 1, "message": "Error"},
                {"severity": 2, "message": "Warning"},
            ],
        }

        await server_module.handle_diagnostics(params)

        assert "file:///src/main.rs" in server_module.current_diagnostics
        assert len(server_module.current_diagnostics["file:///src/main.rs"]) == 2
