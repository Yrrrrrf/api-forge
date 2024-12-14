import re
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
import time

# Text formatting
bold = lambda x: f"\033[1m{x}\033[0m"
italic = lambda x: f"\033[3m{x}\033[0m"
underline = lambda x: f"\033[4m{x}\033[0m"
strike = lambda x: f"\033[9m{x}\033[0m"
dim = lambda x: f"\033[2m{x}\033[0m"

# Colors
gray = lambda x: f"\033[90m{x}\033[0m"
green = lambda x: f"\033[32m{x}\033[0m"
yellow = lambda x: f"\033[33m{x}\033[0m"
red = lambda x: f"\033[31m{x}\033[0m"
blue = lambda x: f"\033[94m{x}\033[0m"
magenta = lambda x: f"\033[95m{x}\033[0m"
cyan = lambda x: f"\033[96m{x}\033[0m"

# Styles
bright = lambda x: f"\033[1;97m{x}\033[0m"
header = lambda x: f"\n{bright('='*50)}\n{bright(x)}\n{bright('='*50)}"
bullet = lambda x: f"• {x}"
arrow = lambda x: f"→ {x}"
box = lambda x: f"┌{'─'*50}┐\n│{x:^50}│\n└{'─'*50}┘"

class Logger:
    """Simple logger with ANSI color support and basic timing capabilities."""
    
    def __init__(self, module_name: str = "FastForge"):
        self.module_name = module_name
        self.indent_level = 0
        self.show_timestamp = True

    def _format_msg(self, level: str, color_fn, msg: str) -> str:
        """Format log message with consistent styling."""
        timestamp = f"{gray(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))} " if self.show_timestamp else ""
        indent = "  " * self.indent_level
        return f"{timestamp}{color_fn(f'[{level}]')} {cyan(f'[{self.module_name}]')} {indent}{msg}"

    def debug(self, msg: str) -> None:
        print(self._format_msg("DEBUG", dim, msg))

    def info(self, msg: str) -> None:
        print(self._format_msg("INFO", gray, msg))

    def success(self, msg: str) -> None:
        print(self._format_msg("SUCCESS", green, msg))

    def warn(self, msg: str) -> None:
        print(self._format_msg("WARN", yellow, msg))

    def error(self, msg: str) -> None:
        print(self._format_msg("ERROR", red, msg))

    def critical(self, msg: str) -> None:
        print(self._format_msg("CRITICAL", lambda x: red(bold(x)), msg))

    @contextmanager
    def indent(self, levels: int = 1):
        """Context manager for temporary indentation."""
        self.indent_level += levels
        try:
            yield
        finally:
            self.indent_level -= levels

    @contextmanager
    def timer(self, operation: str = "Operation"):
        """Context manager for timing operations."""
        start_time = time.time()
        try:
            yield
        finally:
            elapsed_time = time.time() - start_time
            self.info(f"{operation} completed in {elapsed_time:.2f} seconds")

    def section(self, title: str) -> None:
        """Print a section header."""
        print("\n" + header(title))

# Create a single logger instance for the package
log = Logger()
