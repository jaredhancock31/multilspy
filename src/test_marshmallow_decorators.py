"""
Test script to verify that the JediServer class works correctly with direct Jedi API usage
on the marshmallow/tests/test_decorators.py file.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer


class FunctionNode:
    """Represents a function node in the dependency graph."""
    
    def __init__(self, name: str, file_path: str, node_type: str, range_info: dict, name_range: dict):
        self.name = name
        self.file_path = file_path
        self.node_type = node_type
        self.range = range_info
        self.name_range = name_range
        self.incoming: List[str] = []  # Functions that call this function
        self.outgoing: List[str] = []  # Functions that this function calls


class TestLogger(MultilspyLogger):
    """Simple logger implementation for testing."""
    
    def __init__(self):
        self.logs = []
    
    def log(self, message, level=logging.INFO):
        print(f"[{logging.getLevelName(level)}] {message}")
        self.logs.append((level, message))


class LanguageHandler:
    """Base class for language-specific handlers."""
    
    def process_definition(self, defs, target_node, ref_file, ref_line):
        """Process definition to verify if it's a call to the target function."""
        # Default implementation - always return True
        return True


async def test_marshmallow_decorators():
    """Test the JediServer class with direct Jedi API usage on marshmallow/tests/test_decorators.py."""
    
    # Create a logger
    logger = TestLogger()
    logger.log("Starting JediServer direct API test on marshmallow/tests/test_decorators.py", logging.INFO)
    
    # Create a config
    config = MultilspyConfig(code_language=Language.PYTHON)
    
    # Get the repository root path (current directory)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger.log(f"Repository root: {repo_root}", logging.INFO)
    
    # Create a JediServer instance
    server = JediServer(config, logger, repo_root)
    logger.log("Created JediServer instance", logging.INFO)
    
    # Test file path (marshmallow/tests/test_decorators.py)
    test_file_path = "marshmallow/tests/test_decorators.py"
    logger.log(f"Test file path: {test_file_path}", logging.INFO)
    
    # Start the server
    async with server.start_server():
        logger.log("Server started", logging.INFO)
        
        # Test document symbols
        logger.log("\n--- Testing document symbols ---", logging.INFO)
        symbols, tree = await server.request_document_symbols(test_file_path)
        logger.log(f"Found {len(symbols)} symbols", logging.INFO)
        for symbol in symbols[:10]:  # Show first 10 symbols
            logger.log(f"Symbol: {symbol['name']}, kind: {symbol['kind']}", logging.INFO)
        
        # Import SymbolKind to filter symbols
        from multilspy.multilspy_types import SymbolKind
        
        # Filter symbols to include only classes and functions
        class_and_function_symbols = [
            symbol for symbol in symbols 
            if symbol['kind'] in (SymbolKind.Class, SymbolKind.Function, SymbolKind.Method)
        ]
        
        logger.log(f"\nFound {len(class_and_function_symbols)} class and function symbols", logging.INFO)
        
        # Test definitions and references for selected symbols
        for i, symbol in enumerate(class_and_function_symbols):
            symbol_name = symbol['name']
            symbol_kind = "Class" if symbol['kind'] == SymbolKind.Class else "Function/Method"
            definition_line = symbol['selectionRange']['start']['line']
            definition_column = symbol['selectionRange']['start']['character']
            
            logger.log(f"\n--- Testing symbol {i+1}: {symbol_name} ({symbol_kind}) ---", logging.INFO)
            logger.log(f"Symbol location: line {definition_line}, column {definition_column}", logging.INFO)
            
            # Test definition
            logger.log(f"--- Testing definition for {symbol_name} ---", logging.INFO)
            try:
                locations = await server.request_definition(test_file_path, definition_line, definition_column)
                logger.log(f"Found {len(locations)} definition locations", logging.INFO)
                for location in locations:
                    logger.log(f"Definition at: {location['relativePath']}:{location['range']['start']['line']+1}", logging.INFO)
            except Exception as e:
                logger.log(f"Error in request_definition for {symbol_name}: {str(e)}", logging.ERROR)
            
            # Test references
            logger.log(f"--- Testing references for {symbol_name} ---", logging.INFO)
            try:
                references = await server.request_references(test_file_path, definition_line, definition_column)
                logger.log(f"Found {len(references)} reference locations", logging.INFO)
                for reference in references[:5]:  # Show first 5 references
                    logger.log(f"Reference at: {reference['relativePath']}:{reference['range']['start']['line']+1}", logging.INFO)
            except Exception as e:
                logger.log(f"Error in request_references for {symbol_name}: {str(e)}", logging.ERROR)
        
        # Build dependency graph
        logger.log("\n--- Building dependency graph ---", logging.INFO)
        
        # Create a dictionary to store function nodes
        function_nodes: Dict[str, FunctionNode] = {}
        
        # Create a language handler
        handler = LanguageHandler()
        
        # Create function nodes from symbols
        for symbol in class_and_function_symbols:
            if symbol['kind'] in (SymbolKind.Function, SymbolKind.Method):
                func_name = symbol['name']
                node = FunctionNode(
                    name=func_name,
                    file_path=test_file_path,
                    node_type="function",
                    range_info=symbol['range'],
                    name_range=symbol['selectionRange']
                )
                function_nodes[func_name] = node
                logger.log(f"Added function node: {func_name}", logging.INFO)
        
        # Build the dependency graph
        logger.log("Building dependency graph...", logging.INFO)
        for func_name, node in function_nodes.items():
            # ValidationError (Struct) is actually on line 15, start_line is saying 14
            logger.log(f"Analyzing references for {func_name}, {node.node_type} {node.file_path}", logging.DEBUG)
            try:
                with server.open_file(node.file_path):
                    # Find all references to this function
                    refs = await server.request_references(
                        node.file_path,
                        node.name_range['start']['line'],
                        node.name_range['end']['character']
                    )

                    if refs:
                        logger.log(f"Found {len(refs)} references to {func_name}", logging.DEBUG)

                        # Process each reference
                        for ref in refs:
                            ref_file = ref['relativePath']
                            ref_line = ref['range']['start']['line']
                            ref_col = ref['range']['start']['character']
                            ref_end = ref['range']['end']['character']

                            # Find which function contains this reference
                            for caller_name, caller in function_nodes.items():
                                if (caller.file_path == ref_file and
                                    caller.range['start']['line'] <= ref_line <= caller.range['end']['line']):
                                    logger.log(f"ref_file: {ref_file}, ref_line: {ref_line}, ref_col: {ref_col}, ref_end: {ref_end}", logging.DEBUG)
                                    # Verify it's actually a call using definition
                                    try:
                                        # list of locations
                                        defs = await server.request_definition(
                                            ref_file,
                                            ref_line,
                                            ref_end
                                        )
                                        logger.log(f"defs: {defs}", logging.DEBUG)

                                        # Use language-specific handler to process definition
                                        if handler.process_definition(defs, node, ref_file, ref_line):
                                            logger.log(f"  Called by: {caller_name}", logging.DEBUG)
                                            # Use unique keys for tracking references
                                            caller_unique_key = f"{caller.file_path}::{caller_name}"
                                            func_unique_key = f"{node.file_path}::{func_name}"

                                            if caller_unique_key not in node.incoming:
                                                logger.log(f"  Adding {caller_unique_key} to incoming calls", logging.DEBUG)
                                                node.incoming.append(caller_unique_key)
                                            if func_unique_key not in caller.outgoing:
                                                logger.log(f"  Adding {func_unique_key} to outgoing calls", logging.DEBUG)
                                                caller.outgoing.append(func_unique_key)

                                    except Exception as e:
                                        logger.log(f"Error verifying call from {caller_name}: {e}", logging.WARNING)
                                        print(f"David Error verifying call from {caller_name}: {e}", logging.WARNING)
                                    break
            except Exception as e:
                # this will typically happen for 'main' functions
                logger.log(f"Could not analyze references for {func_name}: {e}", logging.WARNING)
        
        # Display the dependency graph
        logger.log("\n--- Dependency Graph Results ---", logging.INFO)
        for func_name, node in function_nodes.items():
            logger.log(f"Function: {func_name}", logging.INFO)
            if node.incoming:
                logger.log(f"  Called by: {', '.join(node.incoming)}", logging.INFO)
            if node.outgoing:
                logger.log(f"  Calls: {', '.join(node.outgoing)}", logging.INFO)
    
    logger.log("\nAll tests completed successfully!", logging.INFO)


def get_function_definition_from_range(repo_path: Optional[str], code_dict: Optional[Dict[str, str]], file_path: str, range_info: dict) -> str:
    """
    Extract full function definition using the range information.

    This method works with both repository paths and code dictionaries.

    Args:
        repo_path: Path to the repository (or None if using code_dict)
        code_dict: Dictionary of code content by file path (or None if using repo_path)
        file_path: Path to the file containing the function
        range_info: Dictionary with start and end line/character information

    Returns:
        String containing the full function definition
    """
    try:
        content = None

        if repo_path:
            # Repository path mode
            abs_file_path = os.path.join(repo_path, file_path)
            if not os.path.isabs(abs_file_path):
                abs_file_path = os.path.abspath(abs_file_path)

            with open(abs_file_path, 'r') as f:
                content = f.read()
        else:
            # Code dictionary mode
            if file_path in code_dict:
                content = code_dict[file_path]
            else:
                print(f"[WARNING] File {file_path} not found in code dictionary")
                return ""

        if content:
            lines = content.split('\n')
            start_line = range_info['start']['line']
            end_line = range_info['end']['line']

            # Ensure indices are within bounds
            start_line = max(0, min(start_line, len(lines) - 1))
            end_line = max(0, min(end_line, len(lines) - 1))

            # Get the full function definition
            definition_lines = lines[start_line:end_line + 1]
            return '\n'.join(definition_lines)

        return ""
    except Exception as e:
        print(f"[WARNING] Could not read function definition from {file_path}: {e}")
        return ""


if __name__ == "__main__":
    asyncio.run(test_marshmallow_decorators())
