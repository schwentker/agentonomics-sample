"""Output validation for benchmark results."""
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileValidation:
    """Validation result for a single file."""
    path: str
    exists: bool
    syntax_valid: bool | None = None  # None if not applicable
    syntax_error: str | None = None
    size_bytes: int = 0


@dataclass
class TestValidation:
    """Validation result for running tests."""
    ran: bool = False
    passed: int = 0
    failed: int = 0
    errors: int = 0
    output: str = ""
    success: bool = False


@dataclass
class ValidationResult:
    """Complete validation result for a benchmark run."""
    workspace: str
    files_expected: list[str] = field(default_factory=list)
    files_validated: list[FileValidation] = field(default_factory=list)
    files_found: int = 0
    files_missing: int = 0
    syntax_errors: int = 0
    test_validation: TestValidation | None = None
    overall_success: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "workspace": self.workspace,
            "files_expected": self.files_expected,
            "files_validated": [
                {
                    "path": f.path,
                    "exists": f.exists,
                    "syntax_valid": f.syntax_valid,
                    "syntax_error": f.syntax_error,
                    "size_bytes": f.size_bytes,
                }
                for f in self.files_validated
            ],
            "files_found": self.files_found,
            "files_missing": self.files_missing,
            "syntax_errors": self.syntax_errors,
            "test_validation": {
                "ran": self.test_validation.ran,
                "passed": self.test_validation.passed,
                "failed": self.test_validation.failed,
                "errors": self.test_validation.errors,
                "success": self.test_validation.success,
                "output": self.test_validation.output[:2000] if self.test_validation.output else "",
            } if self.test_validation else None,
            "overall_success": self.overall_success,
        }


class OutputValidator:
    """Validates benchmark outputs against expected requirements."""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
    
    def validate_file_exists(self, relative_path: str) -> FileValidation:
        """Check if a file exists and get basic info."""
        full_path = self.workspace / relative_path
        exists = full_path.exists() and full_path.is_file()
        
        validation = FileValidation(
            path=relative_path,
            exists=exists,
            size_bytes=full_path.stat().st_size if exists else 0,
        )
        
        # Check syntax for Python files
        if exists and relative_path.endswith('.py'):
            validation.syntax_valid, validation.syntax_error = self._check_python_syntax(full_path)
        
        return validation
    
    def _check_python_syntax(self, file_path: Path) -> tuple[bool, str | None]:
        """Check Python file for syntax errors."""
        try:
            with open(file_path, 'r') as f:
                source = f.read()
            compile(source, str(file_path), 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, str(e)
    
    def run_pytest(self, test_file: str = "test_calculator.py") -> TestValidation:
        """Run pytest on the test file and capture results."""
        test_path = self.workspace / test_file
        
        if not test_path.exists():
            return TestValidation(
                ran=False,
                output=f"Test file not found: {test_file}",
                success=False,
            )
        
        try:
            # Run pytest with just the filename since cwd is the workspace
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.workspace),
            )
            
            output = result.stdout + result.stderr
            
            # Parse pytest output for pass/fail counts
            passed = 0
            failed = 0
            errors = 0
            
            for line in output.split('\n'):
                # Look for summary line like "23 passed" or "5 failed, 18 passed"
                import re
                
                # Match patterns like "23 passed", "5 failed", "2 errors"
                passed_match = re.search(r'(\d+)\s+passed', line)
                if passed_match:
                    passed = int(passed_match.group(1))
                
                failed_match = re.search(r'(\d+)\s+failed', line)
                if failed_match:
                    failed = int(failed_match.group(1))
                
                errors_match = re.search(r'(\d+)\s+error', line)
                if errors_match:
                    errors = int(errors_match.group(1))
            
            return TestValidation(
                ran=True,
                passed=passed,
                failed=failed,
                errors=errors,
                output=output,
                success=result.returncode == 0,
            )
            
        except subprocess.TimeoutExpired:
            return TestValidation(
                ran=True,
                output="Test execution timed out after 60 seconds",
                success=False,
            )
        except Exception as e:
            return TestValidation(
                ran=False,
                output=f"Failed to run tests: {e}",
                success=False,
            )
    
    def validate(self, expected_files: list[str], run_tests: bool = True) -> ValidationResult:
        """Run full validation on the workspace."""
        result = ValidationResult(
            workspace=str(self.workspace),
            files_expected=expected_files,
        )
        
        # Validate each expected file
        for file_path in expected_files:
            validation = self.validate_file_exists(file_path)
            result.files_validated.append(validation)
            
            if validation.exists:
                result.files_found += 1
            else:
                result.files_missing += 1
            
            if validation.syntax_valid is False:
                result.syntax_errors += 1
        
        # Run tests if requested and test file exists
        if run_tests:
            # Find test file in expected files
            test_files = [f for f in expected_files if f.startswith('test_') and f.endswith('.py')]
            if test_files:
                result.test_validation = self.run_pytest(test_files[0])
        
        # Determine overall success
        result.overall_success = (
            result.files_missing == 0 and
            result.syntax_errors == 0 and
            (result.test_validation is None or result.test_validation.success)
        )
        
        return result


def extract_expected_files_from_goal(goal: str) -> list[str]:
    """Extract expected file names from a goal description.
    
    This is a simple heuristic that looks for common patterns like:
    - Create a `filename.py` file
    - Create `filename.py`
    - filename.py file
    """
    import re
    
    files = []
    
    # Pattern: backtick-quoted filenames
    backtick_pattern = r'`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`'
    matches = re.findall(backtick_pattern, goal)
    files.extend(matches)
    
    # Pattern: Create a/the filename
    create_pattern = r'[Cc]reate\s+(?:a\s+)?(?:the\s+)?`?([a-zA-Z0-9_\-./]+\.(?:py|md|txt|json|yaml|yml))`?'
    matches = re.findall(create_pattern, goal)
    files.extend(matches)
    
    # Deduplicate while preserving order
    seen = set()
    unique_files = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    
    return unique_files
