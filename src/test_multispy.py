# from multilspy import SyncLanguageServer
# from multilspy.multilspy_config import MultilspyConfig
# from multilspy.multilspy_logger import MultilspyLogger
# import os
# import logging

# # Configure the language server with debug logging
# config = MultilspyConfig.from_dict({"code_language": "python"})
# logger = MultilspyLogger()
# # The logger is already set to INFO level by default

# # Path to the repository and file to analyze
# repo_path = "/Users/dsounthi/Developer/repos/marshmallow"
# file_path = "src/marshmallow/decorators.py"

# print(f"Analyzing repository: {repo_path}")
# print(f"File to analyze: {file_path}")

# # Create and start the language server
# lsp = SyncLanguageServer.create(config, logger, repo_path)

# with lsp.start_server():
#     # Access the JediServer instance to print the paths
#     jedi_server = lsp.language_server
#     print("\nPython paths added to Jedi:")
#     if hasattr(jedi_server, 'project') and hasattr(jedi_server.project, 'sys_path'):
#         for path in jedi_server.project.sys_path:
#             print(f"  - {path}")
#     else:
#         print("  Project or sys_path not available")
#     print()
#     print(f"Analyzing symbols in {file_path}...")
    
#     # Request document symbols
#     symbols, tree_repr = lsp.request_document_symbols(file_path)
    
#     print(f"Found {len(symbols)} symbols in the document\n")
    
#     # For each symbol, get its definition
#     for i, symbol in enumerate(symbols):
#         print(f"Symbol {i+1}/{len(symbols)}:")
#         print(f"  Name: {symbol['name']}")
#         print(f"  Kind: {symbol['kind']}")
        
#         # Get the position from the selection range
#         line = symbol['selectionRange']['start']['line']
#         column = symbol['selectionRange']['start']['character']
#         print(f"  Position: Line {line} Character {column}")
        
#         # Look up the definition
#         print("  Looking up definition...")
#         print("============David Request Definition =====")
#         definitions = lsp.request_definition(file_path, line, column)
        
#         if definitions:
#             print(f"  Found {len(definitions)} definition(s):")
#             for j, definition in enumerate(definitions):
#                 print(f"    Definition {j+1}:")
#                 print(f"      File: {definition['relativePath']}")
#                 print(f"      Position: Line {definition['range']['start']['line']} Character {definition['range']['start']['character']}")
#         else:
#             print("  No definitions found")
        
#         print()  # Empty line for readability


#!/usr/bin/env python3
"""
Simple test script for Jedi Language Server.
"""

import os
import sys
import json
import logging
import asyncio
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("jedi_test")

# Import multilspy modules
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer

async def main():
    # Path to the marshmallow repository
    repo_path = os.path.abspath("./marshmallow")
    logger.info(f"Using repository path: {repo_path}")
    
    # Create a logger
    multilspy_logger = MultilspyLogger()
    multilspy_logger.logger.setLevel(logging.DEBUG)
    
    # Create a config for Python
    config = MultilspyConfig(
        code_language=Language.PYTHON,
        # trace_lsp_communication=True  # Enable LSP communication tracing
    )
    
    # Create the JediServer instance
    jedi_server = JediServer(config, multilspy_logger, repo_path)
    
    # Get the initialize params
    init_params = jedi_server._get_initialize_params(repo_path)
    logger.info(f"Initialize params: {json.dumps(init_params, indent=2)}")
    
    # Start the server
    async with jedi_server.start_server():
        logger.info("Server started successfully")
        
        # Test with a test file
        test_file = "tests/test_schema.py"
        test_path = os.path.join(repo_path, test_file)
        
        if os.path.exists(test_path):
            logger.info(f"Examining test file: {test_file}")
            
            # Read the file to find a reference to Schema
            with open(test_path, 'r') as f:
                test_lines = f.readlines()
            
            schema_ref_line = None
            schema_ref_col = None
            for i, line in enumerate(test_lines):
                if "Schema" in line:
                    schema_ref_line = i
                    schema_ref_col = line.index("Schema") + 1  # Position at "c" in "Schema"
                    break
            
            if schema_ref_line is not None:
                logger.info(f"Found Schema reference at line {schema_ref_line}, column {schema_ref_col}")
                
                with jedi_server.open_file(test_file):
                    # Try to get definition from the test file reference
                    definitions = await jedi_server.request_definition(test_file, schema_ref_line, schema_ref_col)
                    
                    if definitions:
                        logger.info(f"Found {len(definitions)} definitions:")
                        for i, definition in enumerate(definitions):
                            logger.info(f"Definition {i+1}: {definition}")
                        
                        # Use the first definition to find references
                        def_file = definitions[0]["relativePath"]
                        def_line = definitions[0]["range"]["start"]["line"]
                        def_col = definitions[0]["range"]["start"]["character"]
                        
                        logger.info(f"Finding references to definition at {def_file}:{def_line}:{def_col}")
                        
                        # Find all references
                        references = await jedi_server.request_references(def_file, def_line, def_col)
                        
                        # Log all references
                        logger.info(f"Found {len(references)} references:")
                        
                        # Group references by directory
                        refs_by_dir = {}
                        for ref in references:
                            path = ref["relativePath"]
                            dir_name = os.path.dirname(path).split("/")[0] if "/" in path else path
                            if dir_name not in refs_by_dir:
                                refs_by_dir[dir_name] = []
                            refs_by_dir[dir_name].append(ref)
                        
                        # Log references by directory
                        for dir_name, refs in refs_by_dir.items():
                            logger.info(f"Directory '{dir_name}': {len(refs)} references")
                            for ref in refs:
                                logger.info(f"  {ref['relativePath']}:{ref['range']['start']['line']}:{ref['range']['start']['character']}")
                    else:
                        logger.warning("No definitions found for Schema class")
            else:
                logger.warning(f"No Schema reference found in {test_file}")

if __name__ == "__main__":
    asyncio.run(main())
