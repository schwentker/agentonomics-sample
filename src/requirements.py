"""Structured requirements extraction and verification instructions."""
import re
from dataclasses import dataclass, field
from typing import Any

from .prompt_loader import load_prompt


@dataclass
class FileRequirement:
    """A required output file."""
    path: str
    description: str = ""
    must_be_valid_syntax: bool = False  # For code files
    must_have_tests: bool = False  # For test files


@dataclass 
class VerificationStep:
    """A verification step the agent must perform."""
    description: str
    tool_to_use: str  # e.g., "list_directory", "read_file", "run_command"
    expected_outcome: str


@dataclass
class StructuredRequirements:
    """Structured requirements extracted from a goal."""
    files: list[FileRequirement] = field(default_factory=list)
    verification_steps: list[VerificationStep] = field(default_factory=list)
    raw_goal: str = ""
    
    def get_verification_instructions(self) -> str:
        """Generate verification instructions for the agent."""
        if not self.files and not self.verification_steps:
            return ""
        
        return load_prompt(
            "verification_instructions",
            files=self.files,
            verification_steps=self.verification_steps,
        )
    
    def get_file_list(self) -> list[str]:
        """Get list of expected file paths."""
        return [f.path for f in self.files]


def extract_requirements_from_goal(goal: str) -> StructuredRequirements:
    """Extract structured requirements from a goal description.
    
    Looks for patterns like:
    - Create a `filename.py` file
    - Create `filename.py` with ...
    - test_*.py files
    - README.md
    """
    requirements = StructuredRequirements(raw_goal=goal)
    seen_paths = set()
    
    # Pattern 1: Create a `filename.ext` file with/containing description
    # More restrictive to avoid capturing too much
    file_pattern = r'[Cc]reate\s+(?:a\s+)?(?:the\s+)?`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`(?:\s+file)?(?:\s+(?:with|containing|that has|for)\s+([^`\n]+?))?(?:\n|$|:)'
    
    for match in re.finditer(file_pattern, goal):
        path = match.group(1)
        description = match.group(2).strip() if match.group(2) else ""
        # Clean up description - take only first meaningful part
        if description:
            description = description.split('\n')[0].strip()
            # Remove trailing punctuation artifacts
            description = re.sub(r'[:\d\.\s]+$', '', description).strip()
        
        if path in seen_paths:
            continue
        seen_paths.add(path)
        
        # Determine file type properties
        is_python = path.endswith('.py')
        is_test = path.startswith('test_') and is_python
        
        req = FileRequirement(
            path=path,
            description=description,
            must_be_valid_syntax=is_python,
            must_have_tests=is_test,
        )
        requirements.files.append(req)
    
    # Pattern 2: Simple backtick patterns for any files we missed
    simple_pattern = r'`([a-zA-Z0-9_\-./]+\.(?:py|md|txt|json|yaml|yml))`'
    for match in re.finditer(simple_pattern, goal):
        path = match.group(1)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        
        is_python = path.endswith('.py')
        requirements.files.append(FileRequirement(
            path=path,
            description="",
            must_be_valid_syntax=is_python,
        ))
    
    return requirements


def create_enhanced_goal(goal: str, requirements: StructuredRequirements) -> str:
    """Create an enhanced goal with explicit requirements and verification steps."""
    if not requirements.files and not requirements.verification_steps:
        return goal
    
    return load_prompt(
        "enhanced_goal",
        goal=goal,
        files=requirements.files,
        verification_steps=requirements.verification_steps,
    )
