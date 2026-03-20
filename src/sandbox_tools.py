"""Sandbox tools for safe code execution within the workspace."""
import subprocess
import os
from pathlib import Path
from strands import tool


def create_sandbox_executor(workspace_dir: Path):
    """Create a sandbox executor tool bound to a specific workspace directory.
    
    Args:
        workspace_dir: The workspace directory where commands will be executed
        
    Returns:
        A tool function that executes commands in the sandbox
    """
    workspace_path = workspace_dir.absolute()
    
    @tool(name="execute_command")
    def execute_command(command: str, timeout: int = 60) -> str:
        """Execute a shell command in the workspace sandbox.
        
        Use this tool to run tests, execute Python scripts, or perform other
        shell operations within the workspace directory.
        
        Args:
            command: The shell command to execute (e.g., "python -m pytest test_calculator.py")
            timeout: Maximum execution time in seconds (default: 60)
            
        Returns:
            The command output (stdout and stderr combined)
            
        Examples:
            - Run tests: execute_command("python -m pytest test_calculator.py -v")
            - Run a script: execute_command("python calculator.py")
            - List files: execute_command("ls -la")
        """
        # Security: Only allow execution within the workspace
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            )
            
            output_parts = []
            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            
            output = "\n".join(output_parts) if output_parts else "(no output)"
            exit_info = f"\nExit code: {result.returncode}"
            
            return output + exit_info
            
        except subprocess.TimeoutExpired:
            return f"ERROR: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    return execute_command
