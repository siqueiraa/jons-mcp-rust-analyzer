#!/usr/bin/env python3
"""Simple test script to verify the MCP server works."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from rust_analyzer_mcp import mcp, rust_analyzer


async def test_server():
    """Test the server with a simple Rust project."""
    print("Testing rust-analyzer MCP server...")
    
    # Check if we're in a Rust project
    if not (Path.cwd() / "Cargo.toml").exists():
        print("Warning: No Cargo.toml found. Please run from a Rust project directory.")
        return
    
    # The lifespan will handle initialization
    print("\nMCP Server Info:")
    print(f"Name: {mcp.name}")
    print(f"Tools: {len(await mcp.get_tools())} tools available")
    
    # List all tools
    print("\nAvailable tools:")
    tools = await mcp.get_tools()
    for name, tool in sorted(tools.items()):
        print(f"  - {name}: {tool.description}")
    
    # Test a simple tool if rust-analyzer is initialized
    if rust_analyzer and rust_analyzer._initialized:
        print("\nrust-analyzer is initialized!")
        print(f"Project root: {rust_analyzer.project_root}")
        
        # Try to get analyzer status
        try:
            from fastmcp import Context
            ctx = Context()
            status = await mcp.get_tool("analyzer_status")
            result = await status.fn(ctx)
            print(f"\nAnalyzer status: {result[:100]}..." if len(result) > 100 else f"\nAnalyzer status: {result}")
        except Exception as e:
            print(f"\nError getting analyzer status: {e}")
    else:
        print("\nrust-analyzer not initialized yet.")


async def main():
    """Run the test within the MCP server lifespan."""
    # Use the lifespan context
    from rust_analyzer_mcp import lifespan
    async with lifespan(mcp):
        await test_server()


if __name__ == "__main__":
    asyncio.run(main())