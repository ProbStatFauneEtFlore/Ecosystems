import argparse
import sys
import importlib
from pathlib import Path

# Add parent directory to path to import tools
sys.path.insert(0, str(Path(__file__).parent))

def discover_tools():
    """Discover and list all available tools from the tools folder."""
    tools_dir = Path(__file__).parent / "tools"
    tools = {}
    
    for tool_file in tools_dir.glob("*.py"):
        # Skip __init__.py and utils.py
        if tool_file.name.startswith("_") or tool_file.name == "utils.py":
            continue
        
        # Skip shell scripts
        if tool_file.suffix != ".py":
            continue
        
        tool_name = tool_file.stem
        tools[tool_name] = tool_file
    
    return tools

def main():
    tools = discover_tools()
    tool_choices = list(tools.keys())
    
    # Parse only the tool name and pass remaining args to the tool
    parser = argparse.ArgumentParser(description="Ecosystems main application")
    parser.add_argument("tool", choices=tool_choices, help="Tool to run")
    
    # Parse just the tool name, everything else goes to the tool
    args, tool_args = parser.parse_known_args()
    
    # Dynamically import and run the selected tool
    tool_module = importlib.import_module(f"tools.{args.tool}")
    
    # Try to call main() if it exists, otherwise run the module
    if hasattr(tool_module, "main"):
        # Pass remaining arguments directly to the tool's main function
        import sys
        original_argv = sys.argv
        try:
            # Replace sys.argv with the tool's arguments for its argparse
            sys.argv = [sys.argv[0]] + tool_args
            tool_module.main()
        finally:
            # Restore original argv
            sys.argv = original_argv
    else:
        print(f"Warning: Tool '{args.tool}' does not have a main() function.")

if __name__ == "__main__":
    main()