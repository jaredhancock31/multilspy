"""
This file contains tests for the direct Jedi API implementation of the Python Language Server
"""

import pytest
import os
from pathlib import PurePath
from multilspy import LanguageServer
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer
from tests.test_utils import create_test_context

pytest_plugins = ("pytest_asyncio",)

class TestLogger(MultilspyLogger):
    """Simple logger implementation for testing."""
    
    def __init__(self):
        self.logs = []
    
    def log(self, message, level=None):
        self.logs.append((level, message))


@pytest.mark.asyncio
async def test_jedi_direct_api_with_current_repo():
    """
    Test the direct Jedi API implementation using the current repository
    """
    # Create a logger
    logger = TestLogger()
    
    # Create a config
    config = MultilspyConfig(code_language=Language.PYTHON)
    
    # Get the repository root path (current directory)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Create a JediServer instance
    server = JediServer(config, logger, repo_root)
    
    # Test file path (this file)
    test_file_path = os.path.relpath(__file__, repo_root)
    
    # Start the server
    async with server.start_server():
        # Test document symbols
        symbols, tree = await server.request_document_symbols(test_file_path)
        assert len(symbols) > 0
        
        # Find the JediServer class import line
        with open(__file__, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if "from multilspy.language_servers.jedi_language_server.jedi_server import JediServer" in line:
                    definition_line = i
                    definition_column = line.index("JediServer")
                    break
        
        # Test definition
        locations = await server.request_definition(test_file_path, definition_line, definition_column)
        assert len(locations) > 0
        assert any("jedi_server.py" in location["relativePath"] for location in locations)
        
        # Test completions
        # Find a line with "server." for completions
        for i, line in enumerate(lines):
            if "server." in line:
                completion_line = i
                completion_column = line.index("server.") + 7  # After "server."
                break
        
        completions = await server.request_completions(test_file_path, completion_line, completion_column)
        assert len(completions) > 0
        
        # Test hover
        hover = await server.request_hover(test_file_path, definition_line, definition_column)
        assert hover is not None


@pytest.mark.asyncio
async def test_jedi_direct_api_with_test_context():
    """
    Test the direct Jedi API implementation using the test context
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23"
    }
    with create_test_context(params) as context:
        # Create a JediServer instance directly instead of using LanguageServer.create
        server = JediServer(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        async with server.start_server():
            # Test definition
            result = await server.request_definition(str(PurePath("src/black/mode.py")), 163, 4)

            assert isinstance(result, list)
            assert len(result) > 0
            
            # Test references
            result = await server.request_references(str(PurePath("src/black/mode.py")), 163, 4)
            assert isinstance(result, list)
            assert len(result) > 0
            
            # Test document symbols
            symbols, tree = await server.request_document_symbols(str(PurePath("src/black/mode.py")))
            assert len(symbols) > 0
            
            # Test completions
            completions = await server.request_completions(str(PurePath("src/black/mode.py")), 163, 4)
            assert isinstance(completions, list)
