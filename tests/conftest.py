"""
Pytest configuration and fixtures for rust-analyzer-mcp tests.
"""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, Any
import pytest

# Add parent directory to path to import rust_analyzer_mcp
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.jons_mcp_rust_analyzer import RustAnalyzerClient


@pytest.fixture
def temp_rust_project(tmp_path: Path) -> Path:
    """Create a temporary Rust project for testing."""
    # Create Cargo.toml
    cargo_toml = tmp_path / "Cargo.toml"
    cargo_toml.write_text("""[package]
name = "test_project"
version = "0.1.0"
edition = "2021"

[dependencies]
""")
    
    # Create src directory
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    # Create main.rs
    main_rs = src_dir / "main.rs"
    main_rs.write_text("""fn main() {
    println!("Hello, world!");
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 2), 4);
    }
}
""")
    
    # Create lib.rs
    lib_rs = src_dir / "lib.rs"
    lib_rs.write_text("""//! Test library

pub struct Calculator {
    value: i32,
}

impl Calculator {
    pub fn new() -> Self {
        Self { value: 0 }
    }
    
    pub fn add(&mut self, x: i32) {
        self.value += x;
    }
    
    pub fn get_value(&self) -> i32 {
        self.value
    }
}

pub trait Compute {
    fn compute(&self, x: i32, y: i32) -> i32;
}

pub struct Adder;

impl Compute for Adder {
    fn compute(&self, x: i32, y: i32) -> i32 {
        x + y
    }
}
""")
    
    return tmp_path


@pytest.fixture
async def rust_analyzer_client(temp_rust_project: Path) -> AsyncGenerator[RustAnalyzerClient, None]:
    """Create and start a rust-analyzer client for testing."""
    # Check if rust-analyzer is available
    if not shutil.which("rust-analyzer") and not (Path.home() / ".cargo" / "bin" / "rust-analyzer").exists():
        pytest.skip("rust-analyzer not found")
    
    client = RustAnalyzerClient(temp_rust_project)
    
    try:
        await client.start()
        yield client
    finally:
        await client.shutdown()


@pytest.fixture
def mock_lsp_messages() -> Dict[str, Any]:
    """Mock LSP messages for testing."""
    return {
        "initialize_response": {
            "capabilities": {
                "textDocumentSync": 2,
                "hoverProvider": True,
                "completionProvider": {
                    "resolveProvider": True,
                    "triggerCharacters": [".", ":", "::", "->"]
                },
                "definitionProvider": True,
                "typeDefinitionProvider": True,
                "implementationProvider": True,
                "referencesProvider": True,
                "documentSymbolProvider": True,
                "workspaceSymbolProvider": True,
                "codeActionProvider": {
                    "codeActionKinds": ["quickfix", "refactor"]
                },
                "renameProvider": {
                    "prepareProvider": True
                },
                "documentFormattingProvider": True,
                "documentRangeFormattingProvider": True,
                "semanticTokensProvider": {
                    "legend": {
                        "tokenTypes": [],
                        "tokenModifiers": []
                    },
                    "full": True,
                    "range": True
                }
            }
        },
        "hover_response": {
            "contents": {
                "kind": "markdown",
                "value": "```rust\nfn add(a: i32, b: i32) -> i32\n```\n\nAdds two integers"
            },
            "range": {
                "start": {"line": 4, "character": 3},
                "end": {"line": 4, "character": 6}
            }
        },
        "completion_response": {
            "items": [
                {
                    "label": "println!",
                    "kind": 15,  # Snippet
                    "detail": "macro_rules! println",
                    "documentation": {
                        "kind": "markdown",
                        "value": "Prints to the standard output, with a newline."
                    },
                    "insertText": "println!(\"$1\")$0",
                    "insertTextFormat": 2  # Snippet
                },
                {
                    "label": "print!",
                    "kind": 15,
                    "detail": "macro_rules! print",
                    "insertText": "print!(\"$1\")$0",
                    "insertTextFormat": 2
                }
            ]
        },
        "definition_response": {
            "uri": "file:///test/src/main.rs",
            "range": {
                "start": {"line": 4, "character": 0},
                "end": {"line": 6, "character": 1}
            }
        },
        "diagnostics_notification": {
            "uri": "file:///test/src/main.rs",
            "diagnostics": [
                {
                    "range": {
                        "start": {"line": 10, "character": 4},
                        "end": {"line": 10, "character": 10}
                    },
                    "severity": 1,  # Error
                    "code": "E0425",
                    "source": "rust-analyzer",
                    "message": "cannot find value `unknown` in this scope"
                }
            ]
        }
    }


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()