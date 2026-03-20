"""Prompt template loader using Jinja2."""
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

PROMPTS_DIR = Path(__file__).parent / "prompts"


def regex_match(value: str, pattern: str) -> bool:
    """Custom Jinja2 filter to test regex match."""
    return bool(re.match(pattern, value))


def endswith_filter(value: str, suffix: str) -> bool:
    """Custom Jinja2 filter to test string suffix."""
    return value.endswith(suffix)


def startswith_filter(value: str, prefix: str) -> bool:
    """Custom Jinja2 filter to test string prefix."""
    return value.startswith(prefix)


env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters['match'] = regex_match
env.tests['endswith'] = endswith_filter
env.tests['startswith'] = startswith_filter


def load_prompt(name: str, **kwargs) -> str:
    """Load and render a prompt template.
    
    Args:
        name: Template name without extension (e.g., 'decomposition')
        **kwargs: Variables to pass to the template
        
    Returns:
        Rendered prompt string
    """
    template = env.get_template(f"{name}.md")
    return template.render(**kwargs)
