"""
Test script to verify that the JediServer class works correctly with direct Jedi API usage
without relying on the external jedi-language-server process.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer


class TestLogger(MultilspyLogger):
    """Simple logger implementation for testing."""
    
    def __init__(self):
        self.logs = []
    
    def log(self, message, level=logging.INFO):
        print(f"[{logging.getLevelName(level)}] {message}")
        self.logs.append((level, message))


async def test_jedi_direct():
    """Test the JediServer class with direct Jedi API usage."""
    
    # Create a logger
    logger = TestLogger()
    logger.log("Starting JediServer direct API test", logging.INFO)
    
    # Create a config
    config = MultilspyConfig(code_language=Language.PYTHON)
    
    # Get the repository root path (current directory)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger.log(f"Repository root: {repo_root}", logging.INFO)
    
    # Create a JediServer instance
    server = JediServer(config, logger, repo_root)
    logger.log("Created JediServer instance", logging.INFO)
    
    # Test file path (this file)
    test_file_path = os.path.relpath(__file__, repo_root)
    logger.log(f"Test file path: {test_file_path}", logging.INFO)
    
    # Start the server
    async with server.start_server():
        logger.log("Server started", logging.INFO)
        
        # Test document symbols
        logger.log("\n--- Testing document symbols ---", logging.INFO)
        symbols, tree = await server.request_document_symbols(test_file_path)
        logger.log(f"Found {len(symbols)} symbols", logging.INFO)
        for symbol in symbols[:5]:  # Show first 5 symbols
            logger.log(f"Symbol: {symbol['name']}, kind: {symbol['kind']}", logging.INFO)
        
        # Test definition
        logger.log("\n--- Testing definition ---", logging.INFO)
        # Find the line and column of the JediServer class reference
        with open(__file__, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if "from multilspy.language_servers.jedi_language_server.jedi_server import JediServer" in line:
                    definition_line = i
                    definition_column = line.index("JediServer")
                    break
        
        locations = await server.request_definition(test_file_path, definition_line, definition_column)
        logger.log(f"Found {len(locations)} definition locations", logging.INFO)
        for location in locations:
            logger.log(f"Definition at: {location['relativePath']}:{location['range']['start']['line']+1}", logging.INFO)
        
        # Test completions
        logger.log("\n--- Testing completions ---", logging.INFO)
        # Find a good spot for completions (after "server.")
        for i, line in enumerate(lines):
            if "server." in line:
                completion_line = i
                completion_column = line.index("server.") + 7  # After "server."
                break
        
        completions = await server.request_completions(test_file_path, completion_line, completion_column)
        logger.log(f"Found {len(completions)} completions", logging.INFO)
        for completion in completions[:5]:  # Show first 5 completions
            logger.log(f"Completion: {completion['completionText']}, kind: {completion['kind']}", logging.INFO)
        
        # Test hover
        logger.log("\n--- Testing hover ---", logging.INFO)
        hover = await server.request_hover(test_file_path, definition_line, definition_column)
        if hover:
            logger.log("Hover information found", logging.INFO)
            if isinstance(hover['contents'], dict):
                logger.log(f"Hover content: {hover['contents']['value'][:100]}...", logging.INFO)
            else:
                logger.log(f"Hover content: {str(hover['contents'])[:100]}...", logging.INFO)
        else:
            logger.log("No hover information found", logging.INFO)
    
    logger.log("\nAll tests completed successfully!", logging.INFO)


if __name__ == "__main__":
    asyncio.run(test_jedi_direct())
