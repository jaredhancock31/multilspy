"""
Provides Python specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Python.
"""

import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Tuple, Union
from pathlib import Path

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy import multilspy_types


class JediServer(LanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Python.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a JediServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        # Initialize with a dummy ProcessLaunchInfo since we won't actually launch a server process
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd="echo 'Direct Jedi API mode - no server needed'", cwd=repository_root_path),
            "python",
        )
        
        # Import Jedi
        try:
            import jedi
            logger.log(f"Jedi imported from: {jedi.__file__}", logging.INFO)
            self.jedi = jedi
        except ImportError as e:
            logger.log(f"Error importing jedi: {e}", logging.ERROR)
            raise
        
        # Add additional paths that might contain Python modules
        additional_paths = [repository_root_path]
        
        # First add standard directories if they exist
        standard_dirs = ["tests", "src", "examples", "performance", "benchmarks", "docs"]
        for dir_name in standard_dirs:
            dir_path = os.path.join(repository_root_path, dir_name)
            if os.path.isdir(dir_path):
                logger.log(f"{dir_name.capitalize()} directory exists: {dir_path}", logging.INFO)
                additional_paths.append(dir_path)
        
        # Then scan all top-level directories for Python content
        for item in os.listdir(repository_root_path):
            item_path = os.path.join(repository_root_path, item)
            
            # Skip if not a directory or already added
            if not os.path.isdir(item_path) or item_path in additional_paths:
                continue
                
            # Check if directory contains Python files
            has_python_files = False
            for root, _, files in os.walk(item_path, topdown=True, followlinks=False):
                if any(f.endswith('.py') for f in files):
                    has_python_files = True
                    break
                    
            if has_python_files:
                logger.log(f"Found directory with Python files: {item_path}", logging.INFO)
                additional_paths.append(item_path)
        
        # Add any Python package directories inside src (if it exists)
        src_path = os.path.join(repository_root_path, "src")
        if os.path.isdir(src_path):
            for item in os.listdir(src_path):
                item_path = os.path.join(src_path, item)
                if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
                    logger.log(f"Found Python package: {item_path}", logging.INFO)
                    additional_paths.append(item_path)
        
        # Print the additional paths for debugging
        logger.log("\nAdditional paths added to Jedi:", logging.INFO)
        for path in additional_paths:
            logger.log(f"  - {path}", logging.INFO)
        
        # Create a project with added_sys_path including all relevant paths
        self.project = self.jedi.Project(
            path=repository_root_path,
            added_sys_path=additional_paths
        )
        
        logger.log(f"Project path: {self.project.path}", logging.INFO)
        logger.log(f"Added sys paths: {additional_paths}", logging.INFO)
    
    async def request_document_symbols(self, relative_file_path: str) -> Tuple[List[multilspy_types.UnifiedSymbolInformation], Union[List[multilspy_types.TreeRepr], None]]:
        """
        Requests the document symbols for the given file path using direct Jedi API.
        Returns a tuple of symbol information and tree representation (if available).
        
        :param relative_file_path: The relative path of the file that has the symbols
        :return: A tuple containing a list of symbols in the file and the tree representation (None for now)
        """
        # Try the direct Jedi approach first
        try:
            absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
            self.logger.log(f"Finding symbols in {absolute_file_path}", logging.INFO)
            
            # Check if file exists
            if not os.path.exists(absolute_file_path):
                self.logger.log(f"File does not exist: {absolute_file_path}", logging.ERROR)
                return await super().request_document_symbols(relative_file_path)
            
            # Read file content
            try:
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                self.logger.log(f"Successfully read file content, length: {len(file_content)}", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error reading file: {str(e)}", logging.ERROR)
                return await super().request_document_symbols(relative_file_path)
            
            # Create a Script object
            try:
                script = self.jedi.Script(
                    code=file_content,
                    path=absolute_file_path,
                    project=self.project
                )
                self.logger.log("Successfully created Jedi Script object", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error creating Jedi Script: {str(e)}", logging.ERROR)
                return await super().request_document_symbols(relative_file_path)
            
            # Get all names defined in the file
            try:
                all_names = script.get_names(all_scopes=True, definitions=True)
                self.logger.log(f"Found {len(all_names)} names in the file", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error getting names: {str(e)}", logging.ERROR)
                return await super().request_document_symbols(relative_file_path)
            
            # Map Jedi types to LSP symbol kinds
            JEDI_TYPE_TO_SYMBOL_KIND = {
                "module": multilspy_types.SymbolKind.Module,
                "class": multilspy_types.SymbolKind.Class,
                "function": multilspy_types.SymbolKind.Function,
                "statement": multilspy_types.SymbolKind.Variable,
                "instance": multilspy_types.SymbolKind.Variable,
                "param": multilspy_types.SymbolKind.Variable,
                "import": multilspy_types.SymbolKind.Module,
                "property": multilspy_types.SymbolKind.Property,
                "method": multilspy_types.SymbolKind.Method,
                "keyword": multilspy_types.SymbolKind.Constant,
            }
            
            # Convert Jedi names to UnifiedSymbolInformation objects
            symbols = []
            for name in all_names:
                try:
                    # Get the symbol kind
                    symbol_kind = JEDI_TYPE_TO_SYMBOL_KIND.get(name.type, multilspy_types.SymbolKind.Variable)
                    
                    # Get the start and end positions
                    start_pos = name.get_definition_start_position()
                    end_pos = name.get_definition_end_position()
                    
                    if start_pos is None or end_pos is None:
                        continue
                    
                    # Create the range
                    range_obj = {
                        "start": {
                            "line": start_pos[0] - 1,  # Convert from 1-based to 0-based
                            "character": start_pos[1]
                        },
                        "end": {
                            "line": end_pos[0] - 1,  # Convert from 1-based to 0-based
                            "character": end_pos[1]
                        }
                    }
                    
                    # Create the selection range (just the name itself)
                    selection_range = {
                        "start": {
                            "line": name.line - 1,  # Convert from 1-based to 0-based
                            "character": name.column
                        },
                        "end": {
                            "line": name.line - 1,  # Convert from 1-based to 0-based
                            "character": name.column + len(name.name)
                        }
                    }
                    
                    # Create the symbol information
                    symbol = {
                        "name": name.name,
                        "kind": symbol_kind,
                        "range": range_obj,
                        "selectionRange": selection_range
                    }
                    
                    # Add detail if available
                    if hasattr(name, "description") and name.description:
                        symbol["detail"] = name.description
                    
                    # Add to the list of symbols
                    symbols.append(multilspy_types.UnifiedSymbolInformation(**symbol))
                    self.logger.log(f"Added symbol: {name.name}, type: {name.type}, kind: {symbol_kind}", logging.INFO)
                except Exception as e:
                    self.logger.log(f"Error processing symbol {name.name}: {str(e)}", logging.ERROR)
            
            self.logger.log(f"Successfully converted {len(symbols)} symbols", logging.INFO)
            
            # For now, we don't build a tree representation
            tree_repr = None
            
            if symbols:
                return symbols, tree_repr
            
            # Fall back to the original implementation if no symbols were found
            self.logger.log("No symbols found with direct Jedi approach, falling back to LSP", logging.INFO)
            try:
                return await super().request_document_symbols(relative_file_path)
            except Exception as e:
                self.logger.log(f"Error in LSP fallback: {str(e)}", logging.ERROR)
                return [], None
            
        except Exception as e:
            import traceback
            self.logger.log(f"Error in direct Jedi approach: {str(e)}", logging.ERROR)
            self.logger.log(f"Traceback: {traceback.format_exc()}", logging.ERROR)
            # Fall back to the original implementation
            try:
                return await super().request_document_symbols(relative_file_path)
            except Exception as e:
                self.logger.log(f"Error in LSP fallback: {str(e)}", logging.ERROR)
                return [], None
    async def request_definition(
        self, relative_file_path: str, line: int, column: int
    ) -> List[multilspy_types.Location]:
        """
        Requests the definition of a symbol at the specified line and column in the given file.
        """
        # Try the direct Jedi approach first
        try:
            absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
            self.logger.log(f"Finding definitions in {absolute_file_path} at line {line}, column {column}", logging.INFO)
            
            # Check if file exists
            if not os.path.exists(absolute_file_path):
                self.logger.log(f"File does not exist: {absolute_file_path}", logging.ERROR)
                return await super().request_definition(relative_file_path, line, column)
            
            # Read file content
            try:
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                self.logger.log(f"Successfully read file content, length: {len(file_content)}", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error reading file: {str(e)}", logging.ERROR)
                return await super().request_definition(relative_file_path, line, column)
            
            # Create a Script object
            try:
                script = self.jedi.Script(
                    code=file_content,
                    path=absolute_file_path,
                    project=self.project
                )
                self.logger.log("Successfully created Jedi Script object", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error creating Jedi Script: {str(e)}", logging.ERROR)
                return await super().request_definition(relative_file_path, line, column)
            
            # Try different Jedi methods to find definitions
            definitions = []
            
            # Get all names defined in the file
            try:
                all_names = script.get_names(all_scopes=True, definitions=True)
                self.logger.log(f"Found {len(all_names)} names in the file", logging.INFO)
                
                # Find names at or near the current position
                names_at_position = []
                for name in all_names:
                    # Jedi uses 1-based line numbers
                    if name.line == line + 1:
                        # Check if the cursor is within or near the name
                        name_start = name.column
                        name_end = name.column + len(name.name)
                        # Allow a small margin around the name
                        if max(0, name_start - 5) <= column <= name_end + 5:
                            names_at_position.append(name)
                            self.logger.log(f"Found name at position: {name.name}, type: {name.type}, line: {name.line}, column: {name.column}", logging.INFO)
                
                if names_at_position:
                    # Add these names' definitions to our list
                    for name in names_at_position:
                        try:
                            name_defs = name.goto()
                            self.logger.log(f"Name {name.name} goto found {len(name_defs)} definitions", logging.INFO)
                            definitions.extend(name_defs)
                        except Exception as e:
                            self.logger.log(f"Error in name goto: {str(e)}", logging.INFO)
                else:
                    self.logger.log("No name found at position", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error getting names: {str(e)}", logging.INFO)
            
            # Method 1: goto
            try:
                goto_defs = script.goto(
                    line=line + 1,  # Jedi uses 1-based line numbers
                    column=column,
                    follow_imports=True
                )
                self.logger.log(f"Jedi goto found {len(goto_defs)} definitions", logging.INFO)
                definitions.extend(goto_defs)
            except Exception as e:
                self.logger.log(f"Error in Jedi goto: {str(e)}", logging.INFO)
            
            # Method 2: infer
            try:
                infer_defs = script.infer(
                    line=line + 1,  # Jedi uses 1-based line numbers
                    column=column
                )
                self.logger.log(f"Jedi infer found {len(infer_defs)} definitions", logging.INFO)
                definitions.extend(infer_defs)
            except Exception as e:
                self.logger.log(f"Error in Jedi infer: {str(e)}", logging.INFO)
            
            # Method 3: Try direct position-based methods
            
            # If we still don't have definitions, check the line content for function/class definitions
            if not definitions:
                try:
                    # Get the line content
                    lines = file_content.splitlines()
                    if line < len(lines):
                        line_content = lines[line]
                        self.logger.log(f"Line content: {line_content}", logging.INFO)
                        
                        # Check if this is a function or class definition
                        if line_content.strip().startswith("def ") or line_content.strip().startswith("class "):
                            # Get all names again but filter specifically for this line
                            specific_names = [name for name in all_names if name.line == line + 1]
                            
                            if specific_names:
                                for name in specific_names:
                                    self.logger.log(f"Found definition at line: {name.name}, type: {name.type}", logging.INFO)
                                    # Use the name itself as a definition
                                    definitions.append(name)
                except Exception as e:
                    self.logger.log(f"Error checking line content: {str(e)}", logging.INFO)
            
            # Remove duplicates
            unique_defs = []
            seen_paths_lines = set()
            for definition in definitions:
                key = (definition.module_path, definition.line, definition.column)
                if key not in seen_paths_lines:
                    seen_paths_lines.add(key)
                    unique_defs.append(definition)
            
            self.logger.log(f"Found {len(unique_defs)} unique definitions", logging.INFO)
            
            # Debug info about each definition
            for i, definition in enumerate(unique_defs):
                self.logger.log(f"Definition {i+1}: {definition.name}, type: {definition.type}, "
                               f"module: {definition.module_name}, path: {definition.module_path}, "
                               f"line: {definition.line}, column: {definition.column}", logging.INFO)
            
            # Convert Jedi definitions to LSP locations
            locations = []
            for definition in unique_defs:
                try:
                    uri = Path(definition.module_path).as_uri()
                    location = {
                        "uri": uri,
                        "range": {
                            "start": {
                                "line": definition.line - 1,  # LSP uses 0-based line numbers
                                "character": definition.column
                            },
                            "end": {
                                "line": definition.line - 1,
                                "character": definition.column + len(definition.name)
                            }
                        },
                        "absolutePath": str(definition.module_path),
                        "relativePath": os.path.relpath(str(definition.module_path), self.repository_root_path)
                    }
                    locations.append(multilspy_types.Location(**location))
                except Exception as e:
                    self.logger.log(f"Error converting definition to location: {str(e)}", logging.ERROR)
            
            self.logger.log(f"Successfully converted {len(locations)} definitions to locations", logging.INFO)
            
            if locations:
                return locations
            
            # Fall back to the original implementation if no definitions were found
            self.logger.log("No definitions found with direct Jedi approach, falling back to LSP", logging.INFO)
            try:
                return await super().request_definition(relative_file_path, line, column)
            except Exception as e:
                self.logger.log(f"Error in LSP fallback: {str(e)}", logging.ERROR)
                return []
            
        except Exception as e:
            import traceback
            self.logger.log(f"Error in direct Jedi approach: {str(e)}", logging.ERROR)
            self.logger.log(f"Traceback: {traceback.format_exc()}", logging.ERROR)
            # Fall back to the original implementation
            try:
                return await super().request_definition(relative_file_path, line, column)
            except Exception as e:
                self.logger.log(f"Error in LSP fallback: {str(e)}", logging.ERROR)
                return []

    
    async def request_references(
        self, relative_file_path: str, line: int, column: int
    ) -> List[multilspy_types.Location]:
        """
        Requests the references of a symbol at the specified line and column in the given file.
        """
        # Try the direct Jedi approach first
        try:
            absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
            self.logger.log(f"Finding references in {absolute_file_path} at line {line}, column {column}", logging.INFO)
            
            # Check if file exists
            if not os.path.exists(absolute_file_path):
                self.logger.log(f"File does not exist: {absolute_file_path}", logging.ERROR)
                return await super().request_references(relative_file_path, line, column)
            
            # Read file content
            try:
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                self.logger.log(f"Successfully read file content, length: {len(file_content)}", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error reading file: {str(e)}", logging.ERROR)
                return await super().request_references(relative_file_path, line, column)
            
            # Create a Script object
            try:
                script = self.jedi.Script(
                    code=file_content,
                    path=absolute_file_path,
                    project=self.project
                )
                self.logger.log("Successfully created Jedi Script object", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error creating Jedi Script: {str(e)}", logging.ERROR)
                return await super().request_references(relative_file_path, line, column)
            
            # Get all names defined in the file
            try:
                all_names = script.get_names(all_scopes=True, definitions=True)
                self.logger.log(f"Found {len(all_names)} names in the file", logging.INFO)
                
                # Find names at or near the current position
                names_at_position = []
                for name in all_names:
                    # Jedi uses 1-based line numbers
                    if name.line == line + 1:
                        # Check if the cursor is within or near the name
                        name_start = name.column
                        name_end = name.column + len(name.name)
                        # Allow a small margin around the name
                        if max(0, name_start - 5) <= column <= name_end + 5:
                            names_at_position.append(name)
                            self.logger.log(f"Found name at position: {name.name}, type: {name.type}, line: {name.line}, column: {name.column}", logging.INFO)
                
                if names_at_position:
                    # Use these names for references
                    names = names_at_position
                else:
                    self.logger.log("No name found at position", logging.INFO)
                    names = []
            except Exception as e:
                self.logger.log(f"Error getting names: {str(e)}", logging.INFO)
                names = []
            
            # Try to find references
            references = []
            
            # Method 1: get_references
            try:
                refs = script.get_references(
                    line=line + 1,  # Jedi uses 1-based line numbers
                    column=column,
                    include_builtins=False
                )
                self.logger.log(f"Jedi get_references found {len(refs)} references", logging.INFO)
                references.extend(refs)
            except Exception as e:
                self.logger.log(f"Error in Jedi get_references: {str(e)}", logging.INFO)
            
            # Method 2: If we found a name, try to get its references directly
            if names:
                try:
                    name_refs = names[0].get_references()
                    self.logger.log(f"Name get_references found {len(name_refs)} references", logging.INFO)
                    references.extend(name_refs)
                except Exception as e:
                    self.logger.log(f"Error in name get_references: {str(e)}", logging.INFO)
            
            # Remove duplicates
            unique_refs = []
            seen_paths_lines = set()
            for reference in references:
                key = (reference.module_path, reference.line, reference.column)
                if key not in seen_paths_lines:
                    seen_paths_lines.add(key)
                    unique_refs.append(reference)
            
            self.logger.log(f"Found {len(unique_refs)} unique references", logging.INFO)
            
            # Debug info about each reference
            for i, reference in enumerate(unique_refs):
                self.logger.log(f"Reference {i+1}: {reference.name}, type: {reference.type}, "
                               f"module: {reference.module_name}, path: {reference.module_path}, "
                               f"line: {reference.line}, column: {reference.column}", logging.INFO)
            
            # Convert Jedi references to LSP locations
            locations = []
            for reference in unique_refs:
                try:
                    uri = Path(reference.module_path).as_uri()
                    location = {
                        "uri": uri,
                        "range": {
                            "start": {
                                "line": reference.line - 1,  # LSP uses 0-based line numbers
                                "character": reference.column
                            },
                            "end": {
                                "line": reference.line - 1,
                                "character": reference.column + len(reference.name)
                            }
                        },
                        "absolutePath": str(reference.module_path),
                        "relativePath": os.path.relpath(str(reference.module_path), self.repository_root_path)
                    }
                    locations.append(multilspy_types.Location(**location))
                except Exception as e:
                    self.logger.log(f"Error converting reference to location: {str(e)}", logging.ERROR)
            
            self.logger.log(f"Successfully converted {len(locations)} references to locations", logging.INFO)
            
            if locations:
                return locations
            
            # Fall back to the original implementation if no references were found
            self.logger.log("No references found with direct Jedi approach, falling back to LSP", logging.INFO)
            try:
                return await super().request_references(relative_file_path, line, column)
            except Exception as e:
                self.logger.log(f"Error in LSP fallback: {str(e)}", logging.ERROR)
                return []
            
        except Exception as e:
            import traceback
            self.logger.log(f"Error in direct Jedi approach: {str(e)}", logging.ERROR)
            self.logger.log(f"Traceback: {traceback.format_exc()}", logging.ERROR)
            # Fall back to the original implementation
            try:
                return await super().request_references(relative_file_path, line, column)
            except Exception as e:
                self.logger.log(f"Error in LSP fallback: {str(e)}", logging.ERROR)
                return []
    async def request_completions(
        self, relative_file_path: str, line: int, column: int, allow_incomplete: bool = False
    ) -> List[multilspy_types.CompletionItem]:
        """
        Requests completions at the specified line and column in the given file using direct Jedi API.
        
        :param relative_file_path: The relative path of the file
        :param line: The line number (0-based)
        :param column: The column number
        :param allow_incomplete: Whether to allow incomplete completions
        :return: A list of completion items
        """
        try:
            absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
            self.logger.log(f"Finding completions in {absolute_file_path} at line {line}, column {column}", logging.INFO)
            
            # Check if file exists
            if not os.path.exists(absolute_file_path):
                self.logger.log(f"File does not exist: {absolute_file_path}", logging.ERROR)
                return []
            
            # Read file content
            try:
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                self.logger.log(f"Successfully read file content, length: {len(file_content)}", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error reading file: {str(e)}", logging.ERROR)
                return []
            
            # Create a Script object
            try:
                script = self.jedi.Script(
                    code=file_content,
                    path=absolute_file_path,
                    project=self.project
                )
                self.logger.log("Successfully created Jedi Script object", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error creating Jedi Script: {str(e)}", logging.ERROR)
                return []
            
            # Get completions
            try:
                completions = script.complete(
                    line=line + 1,  # Jedi uses 1-based line numbers
                    column=column
                )
                self.logger.log(f"Found {len(completions)} completions", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error getting completions: {str(e)}", logging.ERROR)
                return []
            
            # Map Jedi completion types to LSP completion item kinds
            JEDI_TYPE_TO_COMPLETION_KIND = {
                "module": multilspy_types.CompletionItemKind.Module,
                "class": multilspy_types.CompletionItemKind.Class,
                "function": multilspy_types.CompletionItemKind.Function,
                "instance": multilspy_types.CompletionItemKind.Variable,
                "statement": multilspy_types.CompletionItemKind.Variable,
                "param": multilspy_types.CompletionItemKind.Variable,
                "import": multilspy_types.CompletionItemKind.Module,
                "property": multilspy_types.CompletionItemKind.Property,
                "method": multilspy_types.CompletionItemKind.Method,
                "keyword": multilspy_types.CompletionItemKind.Keyword,
            }
            
            # Convert Jedi completions to CompletionItem objects
            completion_items = []
            for completion in completions:
                try:
                    # Get the completion kind
                    completion_kind = JEDI_TYPE_TO_COMPLETION_KIND.get(
                        completion.type, multilspy_types.CompletionItemKind.Text
                    )
                    
                    # Create the completion item
                    item = {
                        "completionText": completion.name,
                        "kind": completion_kind
                    }
                    
                    # Add detail if available
                    if hasattr(completion, "description") and completion.description:
                        item["detail"] = completion.description
                    
                    # Add to the list of completion items
                    completion_items.append(multilspy_types.CompletionItem(**item))
                    self.logger.log(f"Added completion: {completion.name}, type: {completion.type}, kind: {completion_kind}", logging.INFO)
                except Exception as e:
                    self.logger.log(f"Error processing completion {completion.name}: {str(e)}", logging.ERROR)
            
            self.logger.log(f"Successfully converted {len(completion_items)} completions", logging.INFO)
            
            return completion_items
            
        except Exception as e:
            import traceback
            self.logger.log(f"Error in direct Jedi approach for completions: {str(e)}", logging.ERROR)
            self.logger.log(f"Traceback: {traceback.format_exc()}", logging.ERROR)
            return []
    
    async def request_hover(self, relative_file_path: str, line: int, column: int) -> Union[multilspy_types.Hover, None]:
        """
        Requests hover information at the specified line and column in the given file using direct Jedi API.
        
        :param relative_file_path: The relative path of the file
        :param line: The line number (0-based)
        :param column: The column number
        :return: Hover information or None if not available
        """
        try:
            absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
            self.logger.log(f"Finding hover info in {absolute_file_path} at line {line}, column {column}", logging.INFO)
            
            # Check if file exists
            if not os.path.exists(absolute_file_path):
                self.logger.log(f"File does not exist: {absolute_file_path}", logging.ERROR)
                return None
            
            # Read file content
            try:
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                self.logger.log(f"Successfully read file content, length: {len(file_content)}", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error reading file: {str(e)}", logging.ERROR)
                return None
            
            # Create a Script object
            try:
                script = self.jedi.Script(
                    code=file_content,
                    path=absolute_file_path,
                    project=self.project
                )
                self.logger.log("Successfully created Jedi Script object", logging.INFO)
            except Exception as e:
                self.logger.log(f"Error creating Jedi Script: {str(e)}", logging.ERROR)
                return None
            
            # Try to get help on the symbol
            try:
                helps = script.help(
                    line=line + 1,  # Jedi uses 1-based line numbers
                    column=column
                )
                
                if helps:
                    help_text = helps[0].docstring()
                    if not help_text:
                        # Try to get a description if docstring is empty
                        help_text = helps[0].description
                    
                    self.logger.log(f"Found hover info: {help_text[:100]}...", logging.INFO)
                    
                    # Create the hover information
                    hover = {
                        "contents": {
                            "kind": "markdown",
                            "value": f"```python\n{help_text}\n```"
                        }
                    }
                    
                    return multilspy_types.Hover(**hover)
                else:
                    self.logger.log("No hover info found", logging.INFO)
                    return None
                
            except Exception as e:
                self.logger.log(f"Error getting hover info: {str(e)}", logging.ERROR)
                return None
            
        except Exception as e:
            import traceback
            self.logger.log(f"Error in direct Jedi approach for hover: {str(e)}", logging.ERROR)
            self.logger.log(f"Traceback: {traceback.format_exc()}", logging.ERROR)
            return None
    
    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Jedi Language Server.
        This is kept for compatibility but not actually used in direct Jedi API mode.
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
    async def start_server(self) -> AsyncIterator["JediServer"]:
        """
        Mock implementation that doesn't actually start a server process.
        Instead, it just sets up the necessary state for direct Jedi API usage.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        ```
        """
        # Set server_started flag to true to allow operations
        self.server_started = True
        
        # Set completions_available event to allow completions to work
        self.completions_available.set()
        
        self.logger.log("Using direct Jedi API mode (no server process needed)", logging.INFO)
        
        try:
            yield self
        finally:
            # Reset state on exit
            self.server_started = False
