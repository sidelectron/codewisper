"""ADK agent definitions: root (codewhisper) + 4 sub-agents. Approach A: all tools on agents; tools return clear message when service unavailable."""

import os

from config import settings
from google.adk.agents import LlmAgent

from . import tools as tools_module
from .prompts import (
    CODE_REVIEW_INSTRUCTION,
    NAVIGATOR_INSTRUCTION,
    ROOT_INSTRUCTION,
    SECURITY_INSTRUCTION,
    SUMMARY_INSTRUCTION,
)

MODEL = os.environ.get("AGENT_MODEL", settings.agent_model)

# Sub-agents (defined first; root references them)
code_reviewer = LlmAgent(
    name="code_reviewer",
    model=MODEL,
    description="Reads and explains code. Tracks file relationships and imports.",
    instruction=CODE_REVIEW_INSTRUCTION,
    tools=[tools_module.get_file_contents, tools_module.list_project_files],
)

security_scanner = LlmAgent(
    name="security_scanner",
    model=MODEL,
    description="Scans code for security vulnerabilities and bad practices.",
    instruction=SECURITY_INSTRUCTION,
    tools=[tools_module.get_file_contents, tools_module.get_git_diff],
)

navigator = LlmAgent(
    name="navigator",
    model=MODEL,
    description="Opens files, scrolls through code, and interacts with the IDE.",
    instruction=NAVIGATOR_INSTRUCTION,
    tools=[
        tools_module.open_file,
        tools_module.click_screen,
        tools_module.scroll_screen,
        tools_module.press_keys,
        tools_module.type_text,
    ],
)

summarizer = LlmAgent(
    name="summarizer",
    model=MODEL,
    description="Generates end-of-session summaries on demand.",
    instruction=SUMMARY_INSTRUCTION,
    tools=[
        tools_module.get_git_diff,
        tools_module.list_project_files,
        tools_module.get_file_contents,
    ],
)

root_agent = LlmAgent(
    name="codewhisper",
    model=MODEL,
    description="Real-time AI coding companion that explains code through voice.",
    instruction=ROOT_INSTRUCTION,
    sub_agents=[code_reviewer, security_scanner, navigator, summarizer],
    tools=[tools_module.get_session_info],
)
