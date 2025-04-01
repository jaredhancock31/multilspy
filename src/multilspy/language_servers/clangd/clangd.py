"""
Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
"""

import asyncio
import json
import logging
import os
import stat
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import FileUtils
from multilspy.multilspy_utils import PlatformUtils


class ClangdServer(LanguageServer):
    """
    Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a ClangdServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        clangd_executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=clangd_executable_path, cwd=repository_root_path),
            "cpp",  # Use "cpp" as the language ID for C/C++
        )
        self.server_ready = asyncio.Event()

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for clangd.
        Prioritizes finding local installations before attempting to download.
        
        Search order:
        1. PATH environment (using shutil.which)
        2. Common installation locations based on platform
        3. IDE bundled installations
        4. Download from specified URL if no local installation found
        
        Returns:
            str: Path to the clangd executable
        """
        # Helper function to check if an executable exists and is valid
        def is_valid_executable(path):
            if not os.path.exists(path):
                return False
            
            if not os.access(path, os.X_OK):
                try:
                    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
                except Exception:
                    return False
            
            return True
        
        # Helper function to verify clangd version
        def verify_clangd_version(path):
            try:
                import subprocess
                result = subprocess.run([path, "--version"], capture_output=True, text=True)
                if result.returncode == 0:
                    version_info = result.stdout
                    logger.log(f"Found clangd version: {version_info.strip()}", logging.INFO)
                    return True
                return False
            except Exception as e:
                logger.log(f"Error verifying clangd version: {str(e)}", logging.INFO)
                return False
        
        # 1. First, check if clangd is in PATH
        try:
            import shutil
            system_clangd_path = shutil.which("clangd")
            if system_clangd_path and verify_clangd_version(system_clangd_path):
                logger.log(f"Found system clangd in PATH: {system_clangd_path}", logging.INFO)
                return system_clangd_path
        except Exception as e:
            logger.log(f"Error checking for clangd in PATH: {str(e)}", logging.INFO)
        
        # 2. Check platform-specific common installation locations
        platform_id = PlatformUtils.get_platform_id()
        common_paths = []
        
        if platform_id.value.startswith("osx"):
            # macOS paths
            common_paths = [
                "/opt/homebrew/bin/clangd",
                "/usr/local/bin/clangd",
                "/usr/bin/clangd",
                "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clangd",
                os.path.expanduser("~/Library/Application Support/Code/User/globalStorage/llvm-vs-code-extensions.vscode-clangd/install/clangd_16/bin/clangd")
            ]
        elif platform_id.value.startswith("linux"):
            # Linux paths
            common_paths = [
                "/usr/bin/clangd",
                "/usr/local/bin/clangd",
                "/snap/bin/clangd",
                "/opt/clangd/bin/clangd",
                os.path.expanduser("~/.local/bin/clangd"),
                os.path.expanduser("~/.vscode/extensions/llvm-vs-code-extensions.vscode-clangd/install/clangd_16/bin/clangd")
            ]
        elif platform_id.value.startswith("win"):
            # Windows paths
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            common_paths = [
                os.path.join(program_files, "LLVM", "bin", "clangd.exe"),
                os.path.join(program_files_x86, "LLVM", "bin", "clangd.exe"),
                os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\Default"), ".vscode", "extensions", "llvm-vs-code-extensions.vscode-clangd", "install", "clangd_16", "bin", "clangd.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"), "Programs", "LLVM", "bin", "clangd.exe")
            ]
        
        # Check all common paths
        for path in common_paths:
            if is_valid_executable(path) and verify_clangd_version(path):
                logger.log(f"Found clangd at common location: {path}", logging.INFO)
                return path
        
        # 3. Check for bundled clangd
        clangd_ls_dir = os.path.join(os.path.dirname(__file__), "static", "Clangd")
        
        # Load runtime dependencies
        try:
            with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
                d = json.load(f)
                del d["_description"]

            runtime_dependencies = d["runtimeDependencies"]
            runtime_dependencies = [
                dependency for dependency in runtime_dependencies if dependency["platformId"] == platform_id.value
            ]
            
            if not runtime_dependencies:
                logger.log(f"No runtime dependencies found for platform {platform_id.value}", logging.ERROR)
                raise Exception(f"No runtime dependencies found for platform {platform_id.value}")
                
            dependency = runtime_dependencies[0]
            clangd_executable_path = os.path.join(clangd_ls_dir, dependency["binaryName"])
            
            # Check if we already have the executable
            if is_valid_executable(clangd_executable_path) and verify_clangd_version(clangd_executable_path):
                logger.log(f"Using existing bundled clangd at {clangd_executable_path}", logging.INFO)
                return clangd_executable_path
                
            # 4. Download and extract clangd as last resort
            logger.log(f"No local clangd installation found. Downloading from {dependency['url']}", logging.INFO)
            
            if not os.path.exists(clangd_ls_dir):
                os.makedirs(clangd_ls_dir)
                
            try:
                if dependency["archiveType"] == "gz":
                    FileUtils.download_and_extract_archive(
                        logger, dependency["url"], clangd_executable_path, dependency["archiveType"]
                    )
                else:
                    FileUtils.download_and_extract_archive(
                        logger, dependency["url"], clangd_ls_dir, dependency["archiveType"]
                    )
                    
                if not is_valid_executable(clangd_executable_path):
                    logger.log(f"Downloaded clangd is not executable: {clangd_executable_path}", logging.ERROR)
                    raise Exception(f"Downloaded clangd is not executable: {clangd_executable_path}")
                
                if not verify_clangd_version(clangd_executable_path):
                    logger.log(f"Downloaded clangd failed version verification: {clangd_executable_path}", logging.ERROR)
                    raise Exception(f"Downloaded clangd failed version verification: {clangd_executable_path}")
                
                logger.log(f"Successfully downloaded and set up clangd at {clangd_executable_path}", logging.INFO)
                return clangd_executable_path
                
            except Exception as e:
                logger.log(f"Error downloading clangd: {str(e)}", logging.ERROR)
                raise Exception(f"Failed to find or download clangd: {str(e)}")
                
        except Exception as e:
            logger.log(f"Error setting up clangd: {str(e)}", logging.ERROR)
            raise Exception(f"Failed to set up clangd: {str(e)}")

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Clangd Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["ClangdServer"]:
        """
        Starts the Clangd Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def do_nothing(params):
            return

        # Register handlers for clangd notifications and requests
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)

        async with super().start_server():
            self.logger.log("Starting Clangd server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            
            # Check server capabilities
            assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
            assert "completionProvider" in init_response["capabilities"]
            
            self.server.notify.initialized({})
            self.completions_available.set()
            
            # Set server ready
            self.server_ready.set()

            yield self

            await self.server.shutdown()
            await self.server.stop()
