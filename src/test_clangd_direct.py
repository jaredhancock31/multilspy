"""
Test the clangd language server directly.
"""

import os
import logging
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import SyncLanguageServer

def main():
    """
    Main function to test the clangd language server.
    """
    # Create a logger
    logger = MultilspyLogger()
    logger.logger.setLevel(logging.INFO)

    # Create a handler that prints to stdout
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logger.logger.addHandler(handler)

    # Create a config for C++
    config = MultilspyConfig(code_language=Language.CPP, trace_lsp_communication=True)

    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(current_dir)

    # Create a test C++ file
    test_file_path = os.path.join(current_dir, "test_cpp_file.cpp")
    with open(test_file_path, "w") as f:
        f.write("""
#include <iostream>

class TestClass {
public:
    void testMethod() {
        std::cout << "Hello, World!" << std::endl;
    }
};

int main() {
    TestClass test;
    test.testMethod();
    return 0;
}
""")

    try:
        # Create a language server
        lsp = SyncLanguageServer.create(config, logger, repo_root)

        # Start the server
        with lsp.start_server():
            logger.log("Server started", logging.INFO)

            # Open the file
            with lsp.open_file("src/test_cpp_file.cpp"):
                logger.log("File opened", logging.INFO)

                # Get document symbols
                symbols, _ = lsp.request_document_symbols("src/test_cpp_file.cpp")
                logger.log(f"Found {len(symbols)} symbols", logging.INFO)
                for symbol in symbols:
                    logger.log(f"Symbol: {symbol['name']}, kind: {symbol['kind']}", logging.INFO)

                # Get completions
                completions = lsp.request_completions("src/test_cpp_file.cpp", 5, 8)
                logger.log(f"Found {len(completions)} completions", logging.INFO)
                for completion in completions[:5]:  # Show only first 5 completions
                    logger.log(f"Completion: {completion['completionText']}, kind: {completion['kind']}", logging.INFO)

                # Get hover information
                hover = lsp.request_hover("src/test_cpp_file.cpp", 3, 10)  # Position of TestClass
                if hover:
                    logger.log(f"Hover info: {hover}", logging.INFO)
                else:
                    logger.log("No hover info found", logging.INFO)

                # Get definition
                definitions = lsp.request_definition("src/test_cpp_file.cpp", 10, 10)  # Position of testMethod call
                logger.log(f"Found {len(definitions)} definitions", logging.INFO)
                for definition in definitions:
                    logger.log(f"Definition: {definition}", logging.INFO)

                # Get references
                references = lsp.request_references("src/test_cpp_file.cpp", 4, 10)  # Position of testMethod definition
                logger.log(f"Found {len(references)} references", logging.INFO)
                for reference in references:
                    logger.log(f"Reference: {reference}", logging.INFO)

    except Exception as e:
        logger.log(f"Error: {e}", logging.ERROR)
        import traceback
        logger.log(traceback.format_exc(), logging.ERROR)
    finally:
        # Clean up the test file
        if os.path.exists(test_file_path):
            os.remove(test_file_path)

if __name__ == "__main__":
    main()
