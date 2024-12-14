from pydantic import BaseModel, Field
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from forge.utils.sql_types import *


# * TEXT FORMATTING
bold = lambda x: f"\033[1m{x}\033[0m"
italic = lambda x: f"\033[3m{x}\033[0m"
underline = lambda x: f"\033[4m{x}\033[0m"
strike = lambda x: f"\033[9m{x}\033[0m"
dim = lambda x: f"\033[2m{x}\033[0m"
# * COLORS
gray = lambda x: f"\033[90m{x}\033[0m"
green = lambda x: f"\033[32m{x}\033[0m"
yellow = lambda x: f"\033[33m{x}\033[0m"
red = lambda x: f"\033[31m{x}\033[0m"
blue = lambda x: f"\033[94m{x}\033[0m"
magenta = lambda x: f"\033[95m{x}\033[0m"
cyan = lambda x: f"\033[96m{x}\033[0m"
# * STYLES
bright = lambda x: f"\033[1;97m{x}\033[0m"
header = lambda x: f"\n{bright('='*50)}\n{bright(x)}\n{bright('='*50)}"
bullet = lambda x: f"• {x}"
arrow = lambda x: f"→ {x}"
box = lambda x: f"┌{'─'*50}┐\n│{x:^50}│\n└{'─'*50}┘"

def visible_len(text: str) -> int:
    """Calculate the visible length of a string, ignoring ANSI color codes."""
    # Remove all ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return len(ansi_escape.sub('', text))
