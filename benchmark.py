#!/usr/bin/env python3
"""
Agent Benchmark System - Interactive Initialization Script

Compares single-agent vs multi-agent approaches for completing goals.
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
import warnings
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Suppress Pydantic serialization warnings from Strands SDK
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

# Suppress asyncio "Event loop is closed" errors during httpx client cleanup
# This is a known issue with async HTTP clients during Python shutdown
def _suppress_event_loop_closed_error(loop, context):
    """Custom exception handler to suppress 'Event loop is closed' errors."""
    if "exception" in context:
        exc = context["exception"]
        if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
            return  # Suppress this specific error
    # For all other exceptions, use default handling
    loop.default_exception_handler(context)

# Apply the custom exception handler to suppress cleanup errors
try:
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_suppress_event_loop_closed_error)
except RuntimeError:
    pass  # No event loop yet, will be handled when one is created

# Enable auto-consent for strands_tools file operations (no interactive prompts)
os.environ["BYPASS_TOOL_CONSENT"] = "true"

from src.config import BenchmarkConfig, MODEL_SPECS, DEFAULT_MODEL
from src.mcp_manager import MCPManager
from src.single_agent import SingleAgentExecutor
from src.multi_agent import MultiAgentExecutor
from src.report_generator import ReportGenerator
from src.validator import OutputValidator, extract_expected_files_from_goal
from src.rubric_evaluator import RubricGenerator, RubricEvaluator
from src.prompt_loader import load_prompt

# Force terminal mode for Rich to ensure output is visible
console = Console(force_terminal=True)

# Load .env early so env vars are available for defaults
load_dotenv()


def get_env_float(key: str, default: float | None = None) -> float | None:
    """Get a float value from environment."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def get_env_int(key: str, default: int | None = None) -> int | None:
    """Get an int value from environment."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get a bool value from environment."""
    val = os.getenv(key, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def load_goal_file(goal_path: Path) -> str:
    """Load and return the goal from a markdown file."""
    if not goal_path.exists():
        console.print(f"[red]Error: Goal file not found: {goal_path}[/red]")
        sys.exit(1)
    
    with open(goal_path) as f:
        return f.read().strip()


def validate_api_key() -> str:
    """Validate and return the Anthropic API key."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY not found in environment or .env file[/red]")
        console.print("Please create a .env file with your API key:")
        console.print("  ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)
    
    return api_key


def verify_mcp_tools(mcp_manager: MCPManager) -> list[dict]:
    """Verify MCP tools are accessible and get authorization."""
    console.print("\n[bold]Verifying MCP Tools...[/bold]")
    
    all_tools = []
    servers = mcp_manager.config.get("mcpServers", {})
    
    for server_name in servers:
        console.print(f"  Connecting to [cyan]{server_name}[/cyan]...")
        try:
            client = mcp_manager.create_client(server_name)
            tools = mcp_manager.verify_tools(client)
            all_tools.extend(tools)
            console.print(f"    [green]✓[/green] Found {len(tools)} tools")
        except Exception as e:
            console.print(f"    [red]✗[/red] Failed: {e}")
            if not Confirm.ask(f"Continue without {server_name}?"):
                sys.exit(1)
    
    if not all_tools:
        console.print("[yellow]Warning: No MCP tools available[/yellow]")
    
    return all_tools


def display_tools(tools: list[dict]):
    """Display available tools in a table."""
    if not tools:
        return
    
    table = Table(title="Available MCP Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Description", style="white")
    
    for tool in tools[:10]:  # Show first 10
        desc = tool.get("description", "")[:60]
        if len(tool.get("description", "")) > 60:
            desc += "..."
        table.add_row(tool["name"], desc)
    
    if len(tools) > 10:
        table.add_row("...", f"({len(tools) - 10} more tools)")
    
    console.print(table)


def validate_goal(api_key: str, goal: str, tools: list[dict]) -> tuple[bool, str]:
    """Validate the goal is achievable with available tools."""
    from strands import Agent
    from strands.models.anthropic import AnthropicModel
    
    console.print("\n[bold]Validating Goal...[/bold]")
    
    # Include sandbox execute_command tool in validation
    sandbox_tool = {
        "name": "execute_command",
        "description": "Execute shell commands in the workspace sandbox. Run tests (pytest), execute Python scripts, install packages (pip/npm), run build commands, and perform any shell operations. Commands run with a 60-second timeout."
    }
    all_tools = tools + [sandbox_tool]
    
    tool_names = [t["name"] for t in all_tools]
    
    model = AnthropicModel(
        client_args={"api_key": api_key},
        model_id=DEFAULT_MODEL,
        max_tokens=1024,
    )
    
    validation_prompt = load_prompt(
        "validation",
        goal=goal,
        tool_names=", ".join(tool_names),
    )
    
    try:
        agent = Agent(model=model)
        response = str(agent(validation_prompt))
        
        is_valid = "VALID" in response.upper() and "INVALID" not in response.upper()
        return is_valid, response
    except Exception as e:
        return False, f"Validation failed: {e}"


def get_followup_info(validation_response: str) -> str | None:
    """Get any followup information needed based on validation."""
    if "QUESTIONS:" in validation_response:
        questions_part = validation_response.split("QUESTIONS:")[-1].strip()
        if questions_part.lower() != "none" and questions_part:
            console.print("\n[yellow]The system has some clarifying questions:[/yellow]")
            console.print(questions_part)
            
            if Confirm.ask("Would you like to provide additional context?"):
                return Prompt.ask("Additional context")
    return None


def select_model() -> str:
    """Let user select a model."""
    console.print("\n[bold]Available Models:[/bold]")
    models = list(MODEL_SPECS.keys())
    
    for i, model in enumerate(models, 1):
        specs = MODEL_SPECS[model]
        display_name = specs.get("display_name", model)
        context = specs["context"]
        max_out = specs["max_output"]
        console.print(f"  {i}. {display_name} [{model}] (context: {context:,}, max output: {max_out:,})")
    
    choice = Prompt.ask(
        "Select model",
        default="1",
        choices=[str(i) for i in range(1, len(models) + 1)]
    )
    
    return models[int(choice) - 1]


def collect_file_metrics(workspace: Path) -> 'FileMetrics':
    """Collect metrics about files created in a workspace."""
    from src.config import FileMetrics
    
    metrics = FileMetrics()
    
    # Skip common non-essential directories
    skip_dirs = {'node_modules', '.git', '__pycache__', '.venv', 'venv', '.next', '.cache'}
    
    for path in workspace.rglob("*"):
        if path.is_file():
            # Check if any parent is in skip list
            if any(p in skip_dirs for p in path.relative_to(workspace).parts):
                continue
            try:
                size = path.stat().st_size
                metrics.add_file(path, size)
            except OSError:
                continue
    
    return metrics


def run_benchmark(config: BenchmarkConfig, api_key: str, goal: str, 
                  mcp_config_path: Path, quiet: bool = False) -> Path:
    """Run the benchmark comparing single and multi-agent approaches."""
    report_gen = ReportGenerator(config.output_dir, config.to_dict())
    
    # Extract expected files from goal for validation
    expected_files = extract_expected_files_from_goal(goal)
    if expected_files:
        console.print(f"\n[dim]Expected output files: {', '.join(expected_files)}[/dim]")
    
    # Run single agent with its own workspace
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]Running Single Agent Benchmark[/bold cyan]")
    console.print("=" * 60)
    
    single_workspace = config.output_dir / "workspace" / "single_agent"
    single_workspace.mkdir(parents=True, exist_ok=True)
    console.print(f"  Workspace: [cyan]{single_workspace}[/cyan]")
    
    # Set workspace for this agent
    config.workspace_dir = single_workspace
    single_mcp_manager = MCPManager(mcp_config_path, single_workspace)
    
    if quiet:
        console.print("Single agent executing...")
        single_executor = SingleAgentExecutor(config, api_key, single_mcp_manager)
        single_result = single_executor.execute(goal)
        single_metrics = single_executor.get_metrics()
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Single agent executing...", total=None)
            
            single_executor = SingleAgentExecutor(config, api_key, single_mcp_manager)
            single_result = single_executor.execute(goal)
            single_metrics = single_executor.get_metrics()
            
            progress.update(task, completed=True)
    
    if single_result["success"]:
        console.print("[green]✓ Single agent completed successfully[/green]")
    else:
        console.print(f"[red]✗ Single agent failed: {single_result.get('error')}[/red]")
    
    # Collect file metrics for single agent
    single_file_metrics = collect_file_metrics(single_workspace)
    console.print(f"[dim]Files created: {single_file_metrics.total_files} ({single_file_metrics._format_bytes(single_file_metrics.total_bytes)})[/dim]")
    
    # Validate single agent output
    single_validation = None
    if expected_files:
        console.print("[dim]Validating single agent output...[/dim]")
        single_validator = OutputValidator(single_workspace)
        single_validation = single_validator.validate(expected_files, run_tests=True)
        
        if single_validation.overall_success:
            console.print(f"[green]✓ Validation passed: {single_validation.files_found}/{len(expected_files)} files, tests passed[/green]")
        else:
            issues = []
            if single_validation.files_missing > 0:
                issues.append(f"{single_validation.files_missing} missing files")
            if single_validation.syntax_errors > 0:
                issues.append(f"{single_validation.syntax_errors} syntax errors")
            if single_validation.test_validation and not single_validation.test_validation.success:
                tv = single_validation.test_validation
                if tv.ran:
                    issues.append(f"tests failed ({tv.passed} passed, {tv.failed} failed)")
                else:
                    issues.append("tests could not run")
            console.print(f"[yellow]⚠ Validation issues: {', '.join(issues)}[/yellow]")
    
    report_gen.add_single_agent_results(single_metrics, single_result, single_validation, single_file_metrics)
    
    # Run multi-agent with its own workspace
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]Running Multi-Agent Benchmark[/bold cyan]")
    console.print("=" * 60)
    
    multi_workspace = config.output_dir / "workspace" / "multi_agent"
    multi_workspace.mkdir(parents=True, exist_ok=True)
    console.print(f"  Workspace: [cyan]{multi_workspace}[/cyan]")
    
    # Set workspace for this agent
    config.workspace_dir = multi_workspace
    multi_mcp_manager = MCPManager(mcp_config_path, multi_workspace)
    
    if quiet:
        console.print("Multi-agent orchestration executing...")
        multi_executor = MultiAgentExecutor(config, api_key, multi_mcp_manager)
        multi_result = multi_executor.execute(goal)
        multi_metrics = multi_executor.get_metrics()
        decomp_report = multi_executor.get_decomposition_report()
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Multi-agent orchestration executing...", total=None)
            
            multi_executor = MultiAgentExecutor(config, api_key, multi_mcp_manager)
            multi_result = multi_executor.execute(goal)
            multi_metrics = multi_executor.get_metrics()
            decomp_report = multi_executor.get_decomposition_report()
            
            progress.update(task, completed=True)
    
    if multi_result["success"]:
        console.print("[green]✓ Multi-agent completed successfully[/green]")
    else:
        console.print(f"[red]✗ Multi-agent failed: {multi_result.get('error')}[/red]")
    
    # Collect file metrics for multi-agent
    multi_file_metrics = collect_file_metrics(multi_workspace)
    console.print(f"[dim]Files created: {multi_file_metrics.total_files} ({multi_file_metrics._format_bytes(multi_file_metrics.total_bytes)})[/dim]")
    
    # Validate multi-agent output
    multi_validation = None
    if expected_files:
        console.print("[dim]Validating multi-agent output...[/dim]")
        multi_validator = OutputValidator(multi_workspace)
        multi_validation = multi_validator.validate(expected_files, run_tests=True)
        
        if multi_validation.overall_success:
            console.print(f"[green]✓ Validation passed: {multi_validation.files_found}/{len(expected_files)} files, tests passed[/green]")
        else:
            issues = []
            if multi_validation.files_missing > 0:
                issues.append(f"{multi_validation.files_missing} missing files")
            if multi_validation.syntax_errors > 0:
                issues.append(f"{multi_validation.syntax_errors} syntax errors")
            if multi_validation.test_validation and not multi_validation.test_validation.success:
                tv = multi_validation.test_validation
                if tv.ran:
                    issues.append(f"tests failed ({tv.passed} passed, {tv.failed} failed)")
                else:
                    issues.append("tests could not run")
            console.print(f"[yellow]⚠ Validation issues: {', '.join(issues)}[/yellow]")
    
    # Get sub-agent metrics breakdown if available
    sub_agent_metrics = multi_executor.get_sub_agent_metrics() if hasattr(multi_executor, 'get_sub_agent_metrics') else None
    
    report_gen.add_multi_agent_results(
        multi_metrics, multi_result, decomp_report, multi_validation,
        multi_file_metrics, sub_agent_metrics
    )
    
    # Rubric-based evaluation
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]Running Rubric-Based Evaluation[/bold cyan]")
    console.print("=" * 60)
    
    try:
        # Generate rubric from goal
        console.print("[dim]Generating assessment rubric from goal...[/dim]")
        rubric_gen = RubricGenerator(api_key, config.model_id)
        rubric = rubric_gen.generate(goal)
        report_gen.set_rubric(rubric)
        
        console.print(f"[green]✓ Rubric generated: {len(rubric.get('criteria', []))} criteria across {len(rubric.get('categories', []))} categories[/green]")
        
        # Save rubric
        rubric_file = config.output_dir / "rubric.json"
        with open(rubric_file, "w") as f:
            json.dump(rubric, f, indent=2)
        
        # Evaluate single agent workspace
        console.print("[dim]Evaluating single agent output...[/dim]")
        evaluator = RubricEvaluator(api_key, config.model_id)
        single_eval = evaluator.evaluate(single_workspace, rubric)
        report_gen.add_rubric_evaluation("single_agent", single_eval)
        console.print(f"[green]✓ Single agent score: {single_eval.total_score}/100 (Grade: {single_eval.grade})[/green]")
        
        # Evaluate multi-agent workspace
        console.print("[dim]Evaluating multi-agent output...[/dim]")
        multi_eval = evaluator.evaluate(multi_workspace, rubric)
        report_gen.add_rubric_evaluation("multi_agent", multi_eval)
        console.print(f"[green]✓ Multi-agent score: {multi_eval.total_score}/100 (Grade: {multi_eval.grade})[/green]")
        
    except Exception as e:
        console.print(f"[yellow]⚠ Rubric evaluation failed: {e}[/yellow]")
        console.print("[dim]Continuing with report generation...[/dim]")
    
    # Generate report
    console.print("\n[bold]Generating Benchmark Report...[/bold]")
    report_path = report_gen.save_report()
    
    return report_path


def display_quick_summary(output_dir: Path):
    """Display a quick summary of the benchmark results."""
    report_file = output_dir / "benchmark_report.json"
    
    if not report_file.exists():
        return
    
    with open(report_file) as f:
        data = json.load(f)
    
    comp = data.get("comparison", {})
    single = data.get("single_agent", {}).get("metrics", {})
    multi = data.get("multi_agent", {}).get("metrics", {})
    single_val = data.get("single_agent", {}).get("validation")
    multi_val = data.get("multi_agent", {}).get("validation")
    single_eval = data.get("rubric_evaluation", {}).get("single_agent")
    multi_eval = data.get("rubric_evaluation", {}).get("multi_agent")
    
    console.print("\n" + "=" * 60)
    console.print("[bold green]Benchmark Complete![/bold green]")
    console.print("=" * 60)
    
    table = Table(title="Quick Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Single Agent", justify="right")
    table.add_column("Multi-Agent", justify="right")
    table.add_column("Winner", justify="center")
    
    single_tokens = single.get("tokens", {}).get("total_tokens", 0)
    multi_tokens = multi.get("total_tokens", {}).get("total_tokens", 0)
    
    single_time = single.get("execution_time_seconds", 0)
    multi_time = multi.get("total_execution_time_seconds", 0)
    
    table.add_row(
        "Total Tokens",
        f"{single_tokens:,}",
        f"{multi_tokens:,}",
        "🏆 Single" if single_tokens < multi_tokens else "🏆 Multi"
    )
    
    table.add_row(
        "Execution Time",
        f"{single_time:.2f}s",
        f"{multi_time:.2f}s",
        "🏆 Single" if single_time < multi_time else "🏆 Multi"
    )
    
    # Add validation row
    def val_emoji(val):
        if val is None:
            return "N/A"
        return "✅" if val.get("overall_success") else "❌"
    
    single_valid = single_val.get("overall_success") if single_val else None
    multi_valid = multi_val.get("overall_success") if multi_val else None
    
    if single_valid is not None or multi_valid is not None:
        winner = "-"
        if single_valid and not multi_valid:
            winner = "🏆 Single"
        elif multi_valid and not single_valid:
            winner = "🏆 Multi"
        elif single_valid and multi_valid:
            winner = "✅ Both"
        
        table.add_row(
            "Output Validated",
            val_emoji(single_val),
            val_emoji(multi_val),
            winner
        )
    
    # Add rubric score row
    if single_eval or multi_eval:
        single_score = single_eval.get("total_score", 0) if single_eval else 0
        multi_score = multi_eval.get("total_score", 0) if multi_eval else 0
        single_grade = single_eval.get("grade", "?") if single_eval else "N/A"
        multi_grade = multi_eval.get("grade", "?") if multi_eval else "N/A"
        
        score_winner = "-"
        if single_score > multi_score:
            score_winner = "🏆 Single"
        elif multi_score > single_score:
            score_winner = "🏆 Multi"
        elif single_score == multi_score and single_score > 0:
            score_winner = "Tie"
        
        table.add_row(
            "Quality Score",
            f"{single_score}/100 ({single_grade})",
            f"{multi_score}/100 ({multi_grade})",
            score_winner
        )
    
    # Add cost row
    single_costs = data.get("single_agent", {}).get("costs", {})
    multi_costs = data.get("multi_agent", {}).get("costs", {})
    if single_costs or multi_costs:
        single_cost = single_costs.get("total_cost", 0)
        multi_cost = multi_costs.get("total_cost", 0)
        table.add_row(
            "Total Cost",
            f"${single_cost:.4f}",
            f"${multi_cost:.4f}",
            "🏆 Single" if single_cost < multi_cost else "🏆 Multi"
        )
    
    console.print(table)
    
    # Show apples-to-apples status
    if comp.get("both_validated"):
        console.print("\n[green]✅ Apples-to-apples comparison: Both outputs validated successfully[/green]")
    elif single_val is not None or multi_val is not None:
        console.print("\n[yellow]⚠️ Comparison caveat: Outputs differ in quality (see report for details)[/yellow]")


def main():
    # Get env defaults (CLI args will override these)
    env_model = os.getenv("BENCHMARK_MODEL")
    env_mcp_config = os.getenv("BENCHMARK_MCP_CONFIG", "mcp.json")
    env_output = os.getenv("BENCHMARK_OUTPUT")
    env_temperature = get_env_float("BENCHMARK_TEMPERATURE", 1.0)
    env_top_p = get_env_float("BENCHMARK_TOP_P")
    env_top_k = get_env_int("BENCHMARK_TOP_K")
    env_max_tokens = get_env_int("BENCHMARK_MAX_TOKENS")
    env_skip_validation = get_env_bool("BENCHMARK_SKIP_VALIDATION", False)
    
    parser = argparse.ArgumentParser(
        description="Agent Benchmark System - Compare single vs multi-agent approaches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables (can be set in .env file):
  ANTHROPIC_API_KEY         Required. Your Anthropic API key.
  BENCHMARK_MODEL           Model ID to use
  BENCHMARK_MCP_CONFIG      Path to MCP config file
  BENCHMARK_OUTPUT          Output directory
  BENCHMARK_TEMPERATURE     Model temperature (0.0-1.0)
  BENCHMARK_TOP_P           Top-p sampling
  BENCHMARK_TOP_K           Top-k sampling
  BENCHMARK_MAX_TOKENS      Max output tokens
  BENCHMARK_SKIP_VALIDATION Skip goal validation (true/false)

CLI arguments override environment variables.
"""
    )
    parser.add_argument(
        "--goal", "-g",
        type=Path,
        required=True,
        help="Path to markdown file containing the goal"
    )
    parser.add_argument(
        "--mcp-config", "-m",
        type=Path,
        default=Path(env_mcp_config),
        help=f"Path to MCP configuration file (default: {env_mcp_config})"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(env_output) if env_output else None,
        help="Output directory for benchmark results"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=env_model,
        help="Model ID to use (interactive selection if not provided)"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        default=env_skip_validation,
        help="Skip goal validation step"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=env_temperature,
        help=f"Model temperature (0.0-1.0, default: {env_temperature})"
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=env_top_p,
        help="Top-p sampling (nucleus sampling)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=env_top_k,
        help="Top-k sampling"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=env_max_tokens,
        help="Max output tokens (default: model's max)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=get_env_bool("BENCHMARK_QUIET", False),
        help="Disable spinner/progress indicators (useful for CI/logging)"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=get_env_bool("BENCHMARK_YES", False),
        help="Auto-confirm prompts (skip confirmation dialogs)"
    )
    
    args = parser.parse_args()
    
    # Display header
    console.print(Panel.fit(
        "[bold blue]Agent Benchmark System[/bold blue]\n"
        "Comparing Single-Agent vs Multi-Agent Approaches",
        border_style="blue"
    ))
    
    # Step 1: Validate API key
    console.print("\n[bold]Step 1: Checking API Key[/bold]")
    api_key = validate_api_key()
    console.print("[green]✓ API key found[/green]")
    
    # Step 2: Load goal
    console.print("\n[bold]Step 2: Loading Goal[/bold]")
    goal = load_goal_file(args.goal)
    console.print(f"[green]✓ Goal loaded from {args.goal}[/green]")
    console.print(Panel(goal[:500] + ("..." if len(goal) > 500 else ""), title="Goal Preview"))
    
    # Step 3: Determine output directory (but don't create yet)
    console.print("\n[bold]Step 3: Setting Up Directories[/bold]")
    if args.output:
        output_dir = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(f"benchmark_results_{timestamp}")
    
    console.print(f"[green]✓ Output directory: {output_dir}[/green]")
    console.print(f"[dim]  Workspaces will be created at: {output_dir}/workspace/single_agent and {output_dir}/workspace/multi_agent[/dim]")
    
    # Step 4: Verify MCP tools (use a temp directory outside the output dir)
    console.print("\n[bold]Step 4: Verifying MCP Tools[/bold]")
    if not args.mcp_config.exists():
        console.print(f"[yellow]Warning: MCP config not found at {args.mcp_config}[/yellow]")
        if not Confirm.ask("Continue without MCP tools?"):
            sys.exit(1)
        tools = []
    else:
        # Create a temporary workspace for tool verification (outside output_dir)
        with tempfile.TemporaryDirectory(prefix="benchmark_verify_") as temp_dir:
            temp_workspace = Path(temp_dir)
            mcp_manager = MCPManager(args.mcp_config, temp_workspace)
            tools = verify_mcp_tools(mcp_manager)
            display_tools(tools)
            # temp directory is automatically cleaned up
    
    # Step 5: Validate goal
    if not args.skip_validation:
        console.print("\n[bold]Step 5: Validating Goal[/bold]")
        is_valid, validation_response = validate_goal(api_key, goal, tools)
        
        if is_valid:
            console.print("[green]✓ Goal validated successfully[/green]")
        else:
            console.print("[yellow]⚠ Goal validation raised concerns[/yellow]")
            console.print(validation_response)
            
            if not Confirm.ask("Continue anyway?"):
                sys.exit(1)
        
        # Check for followup questions
        additional_context = get_followup_info(validation_response)
        if additional_context:
            goal = f"{goal}\n\nAdditional Context:\n{additional_context}"
    
    # Step 6: Select model
    console.print("\n[bold]Step 6: Model Selection[/bold]")
    if args.model:
        model_id = args.model
        console.print(f"Using specified model: [cyan]{model_id}[/cyan]")
    else:
        model_id = select_model()
    console.print(f"[green]✓ Selected: {model_id}[/green]")
    
    # Create config
    max_tokens = args.max_tokens or MODEL_SPECS.get(model_id, {}).get("max_output", 16384)
    
    config = BenchmarkConfig(
        goal_file=args.goal,
        mcp_config_file=args.mcp_config,
        output_dir=output_dir,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
    )
    
    # Confirm before running
    console.print("\n" + "=" * 60)
    if not args.yes and not Confirm.ask("[bold]Ready to run benchmark?[/bold]"):
        console.print("Benchmark cancelled.")
        sys.exit(0)
    
    # Now create the output directory (after all confirmations passed)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the goal to output directory
    goal_output = output_dir / "goal.md"
    with open(goal_output, "w") as f:
        f.write(goal)
    
    # Run benchmark
    report_path = run_benchmark(config, api_key, goal, args.mcp_config, args.quiet)
    
    # Display summary
    display_quick_summary(output_dir)
    
    console.print(f"\n[bold]Full report saved to:[/bold] {report_path}")
    console.print(f"[bold]All artifacts in:[/bold] {output_dir}")


if __name__ == "__main__":
    main()
