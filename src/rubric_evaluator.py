"""Rubric-based evaluation for benchmark workspaces."""
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from strands import Agent
from strands.models.anthropic import AnthropicModel
from strands.handlers.callback_handler import null_callback_handler

from .prompt_loader import load_prompt
from .config import DEFAULT_MODEL


@dataclass
class EvidenceManifest:
    """Collected evidence from a workspace for evaluation."""
    workspace: str
    file_tree: list[dict] = field(default_factory=list)
    file_contents: dict[str, str] = field(default_factory=dict)
    test_results: dict[str, Any] | None = None
    build_results: dict[str, Any] | None = None
    keyword_matches: dict[str, list[str]] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "file_tree": self.file_tree,
            "file_contents": self.file_contents,
            "test_results": self.test_results,
            "build_results": self.build_results,
            "keyword_matches": self.keyword_matches,
        }


@dataclass
class CriterionScore:
    """Score for a single criterion."""
    criterion_id: str
    criterion_name: str
    max_points: int
    awarded_points: float
    reasoning: str
    evidence_used: list[str] = field(default_factory=list)


@dataclass
class CategoryTotal:
    """Total score for a category."""
    category: str
    max_points: int
    awarded_points: float
    percentage: float


@dataclass
class EvaluationResult:
    """Complete evaluation result for a workspace."""
    workspace: str
    scores: list[CriterionScore] = field(default_factory=list)
    category_totals: list[CategoryTotal] = field(default_factory=list)
    total_score: float = 0.0
    max_score: int = 100
    grade: str = "F"
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "scores": [
                {
                    "criterion_id": s.criterion_id,
                    "criterion_name": s.criterion_name,
                    "max_points": s.max_points,
                    "awarded_points": s.awarded_points,
                    "reasoning": s.reasoning,
                    "evidence_used": s.evidence_used,
                }
                for s in self.scores
            ],
            "category_totals": [
                {
                    "category": c.category,
                    "max_points": c.max_points,
                    "awarded_points": c.awarded_points,
                    "percentage": c.percentage,
                }
                for c in self.category_totals
            ],
            "total_score": self.total_score,
            "max_score": self.max_score,
            "grade": self.grade,
            "summary": self.summary,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "evidence_gaps": self.evidence_gaps,
        }


class EvidenceCollector:
    """Collects evidence from a workspace for rubric evaluation."""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
    
    def collect(self, rubric: dict, max_file_size: int = 5000) -> EvidenceManifest:
        """Collect evidence based on rubric requirements.
        
        Args:
            rubric: The rubric dict with criteria
            max_file_size: Max chars to include per file (truncate larger files)
        """
        manifest = EvidenceManifest(workspace=str(self.workspace))
        
        # Collect file tree
        manifest.file_tree = self._collect_file_tree()
        
        # Extract targets from rubric criteria
        targets = self._extract_targets(rubric)
        
        # Collect targeted file contents
        manifest.file_contents = self._collect_file_contents(targets, max_file_size)
        
        # Run tests if test files exist
        manifest.test_results = self._run_tests()
        
        # Check build if package.json or setup.py exists
        manifest.build_results = self._check_build()
        
        # Search for keywords from rubric
        keywords = self._extract_keywords(rubric)
        manifest.keyword_matches = self._search_keywords(keywords)
        
        return manifest
    
    def _collect_file_tree(self, max_depth: int = 5) -> list[dict]:
        """Collect file tree with metadata."""
        files = []
        
        for path in self.workspace.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(self.workspace)
                
                # Skip common non-essential directories
                parts = rel_path.parts
                if any(p in parts for p in ['node_modules', '.git', '__pycache__', '.venv', 'venv', '.next']):
                    continue
                
                # Limit depth
                if len(parts) > max_depth:
                    continue
                
                try:
                    stat = path.stat()
                    files.append({
                        "path": str(rel_path),
                        "size_bytes": stat.st_size,
                        "extension": path.suffix,
                    })
                except OSError:
                    continue
        
        return sorted(files, key=lambda x: x["path"])
    
    def _extract_targets(self, rubric: dict) -> set[str]:
        """Extract file/pattern targets from rubric criteria."""
        targets = set()
        
        for criterion in rubric.get("criteria", []):
            verification = criterion.get("verification", {})
            target = verification.get("target", "")
            
            # Extract file paths from target
            # Match patterns like "src/auth/login.ts" or "*.py" or "test_*.py"
            path_pattern = r'[\w\-./]+\.\w+'
            matches = re.findall(path_pattern, target)
            targets.update(matches)
            
            # Also check evidence_needed
            evidence = verification.get("evidence_needed", "")
            matches = re.findall(path_pattern, evidence)
            targets.update(matches)
        
        return targets
    
    def _collect_file_contents(self, targets: set[str], max_size: int) -> dict[str, str]:
        """Collect contents of targeted files."""
        contents = {}
        
        for target in targets:
            # Handle glob patterns
            if '*' in target:
                pattern = target.replace('*', '**/*') if '**' not in target else target
                for path in self.workspace.glob(pattern):
                    if path.is_file():
                        rel_path = str(path.relative_to(self.workspace))
                        contents[rel_path] = self._read_file(path, max_size)
            else:
                # Direct file path
                path = self.workspace / target
                if path.exists() and path.is_file():
                    contents[target] = self._read_file(path, max_size)
        
        # Also include common important files
        important_files = [
            "README.md", "package.json", "setup.py", "pyproject.toml",
            "requirements.txt", "Makefile", "Dockerfile", ".env.example",
        ]
        for filename in important_files:
            path = self.workspace / filename
            if path.exists() and filename not in contents:
                contents[filename] = self._read_file(path, max_size)
        
        return contents
    
    def _read_file(self, path: Path, max_size: int) -> str:
        """Read file content with size limit."""
        try:
            content = path.read_text(errors='replace')
            if len(content) > max_size:
                return content[:max_size] + f"\n\n[TRUNCATED - {len(content)} total chars]"
            return content
        except Exception as e:
            return f"[ERROR reading file: {e}]"
    
    def _run_tests(self) -> dict[str, Any] | None:
        """Run tests and capture results."""
        # Check for pytest
        test_files = list(self.workspace.glob("**/test_*.py"))
        if test_files:
            return self._run_pytest()
        
        # Check for npm test
        if (self.workspace / "package.json").exists():
            return self._run_npm_test()
        
        return None
    
    def _run_pytest(self) -> dict[str, Any]:
        """Run pytest and parse results."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", "--tb=short", "-q"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.workspace),
            )
            
            output = result.stdout + result.stderr
            
            # Parse results
            passed = 0
            failed = 0
            errors = 0
            
            for line in output.split('\n'):
                if match := re.search(r'(\d+)\s+passed', line):
                    passed = int(match.group(1))
                if match := re.search(r'(\d+)\s+failed', line):
                    failed = int(match.group(1))
                if match := re.search(r'(\d+)\s+error', line):
                    errors = int(match.group(1))
            
            return {
                "framework": "pytest",
                "ran": True,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "success": result.returncode == 0,
                "output_summary": output[-2000:] if len(output) > 2000 else output,
            }
        except subprocess.TimeoutExpired:
            return {"framework": "pytest", "ran": False, "error": "Timeout after 120s"}
        except Exception as e:
            return {"framework": "pytest", "ran": False, "error": str(e)}
    
    def _run_npm_test(self) -> dict[str, Any]:
        """Run npm test and parse results."""
        try:
            result = subprocess.run(
                ["npm", "test", "--", "--passWithNoTests"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.workspace),
            )
            
            output = result.stdout + result.stderr
            
            return {
                "framework": "npm",
                "ran": True,
                "success": result.returncode == 0,
                "output_summary": output[-2000:] if len(output) > 2000 else output,
            }
        except subprocess.TimeoutExpired:
            return {"framework": "npm", "ran": False, "error": "Timeout after 120s"}
        except FileNotFoundError:
            return {"framework": "npm", "ran": False, "error": "npm not found"}
        except Exception as e:
            return {"framework": "npm", "ran": False, "error": str(e)}
    
    def _check_build(self) -> dict[str, Any] | None:
        """Check if project builds successfully."""
        # Python project
        if (self.workspace / "setup.py").exists() or (self.workspace / "pyproject.toml").exists():
            return self._check_python_build()
        
        # Node project
        if (self.workspace / "package.json").exists():
            return self._check_npm_build()
        
        return None
    
    def _check_python_build(self) -> dict[str, Any]:
        """Check Python syntax across all .py files."""
        errors = []
        checked = 0
        
        for path in self.workspace.rglob("*.py"):
            rel_path = path.relative_to(self.workspace)
            if any(p in rel_path.parts for p in ['node_modules', '.git', '__pycache__', '.venv', 'venv']):
                continue
            
            checked += 1
            try:
                source = path.read_text()
                compile(source, str(rel_path), 'exec')
            except SyntaxError as e:
                errors.append(f"{rel_path}:{e.lineno}: {e.msg}")
        
        return {
            "type": "python_syntax",
            "files_checked": checked,
            "errors": errors,
            "success": len(errors) == 0,
        }
    
    def _check_npm_build(self) -> dict[str, Any]:
        """Check if npm build succeeds."""
        # First check if build script exists
        try:
            pkg = json.loads((self.workspace / "package.json").read_text())
            if "build" not in pkg.get("scripts", {}):
                return {"type": "npm_build", "ran": False, "reason": "No build script"}
        except Exception:
            return {"type": "npm_build", "ran": False, "reason": "Invalid package.json"}
        
        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(self.workspace),
            )
            
            return {
                "type": "npm_build",
                "ran": True,
                "success": result.returncode == 0,
                "output_summary": (result.stdout + result.stderr)[-1000:],
            }
        except subprocess.TimeoutExpired:
            return {"type": "npm_build", "ran": False, "error": "Timeout after 180s"}
        except FileNotFoundError:
            return {"type": "npm_build", "ran": False, "error": "npm not found"}
        except Exception as e:
            return {"type": "npm_build", "ran": False, "error": str(e)}
    
    def _extract_keywords(self, rubric: dict) -> set[str]:
        """Extract keywords to search for from rubric."""
        keywords = set()
        
        for criterion in rubric.get("criteria", []):
            verification = criterion.get("verification", {})
            evidence = verification.get("evidence_needed", "")
            
            # Extract quoted strings as keywords
            quoted = re.findall(r'"([^"]+)"', evidence)
            keywords.update(quoted)
            
            # Extract technical terms (capitalized or camelCase)
            terms = re.findall(r'\b[A-Z][a-zA-Z]+\b', evidence)
            keywords.update(terms)
        
        return keywords
    
    def _search_keywords(self, keywords: set[str]) -> dict[str, list[str]]:
        """Search for keywords in workspace files."""
        matches = {}
        
        for keyword in keywords:
            if len(keyword) < 3:  # Skip very short keywords
                continue
            
            found_in = []
            for path in self.workspace.rglob("*"):
                if not path.is_file():
                    continue
                
                rel_path = path.relative_to(self.workspace)
                if any(p in rel_path.parts for p in ['node_modules', '.git', '__pycache__', '.venv']):
                    continue
                
                try:
                    content = path.read_text(errors='replace')
                    if keyword.lower() in content.lower():
                        found_in.append(str(rel_path))
                except Exception:
                    continue
            
            if found_in:
                matches[keyword] = found_in[:10]  # Limit to 10 files per keyword
        
        return matches


class RubricGenerator:
    """Generates assessment rubrics from goals."""
    
    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL):
        from .config import MODEL_SPECS
        max_output = MODEL_SPECS.get(model_id, {}).get("max_output", 16384)
        self.model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            max_tokens=max_output,
        )
    
    def generate(self, goal: str) -> dict:
        """Generate a rubric for the given goal.
        
        Args:
            goal: The goal text to analyze
            
        Returns:
            Rubric dict with categories and criteria
        """
        prompt = load_prompt("rubric_generator", goal=goal)
        
        # Use null callback to suppress stdout output
        agent = Agent(model=self.model, callback_handler=null_callback_handler)
        response = str(agent(prompt))
        
        # Extract JSON from response
        return self._parse_rubric_response(response)
    
    def _parse_rubric_response(self, response: str) -> dict:
        """Parse rubric JSON from LLM response."""
        # Try to find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                rubric = json.loads(json_match.group())
                self._validate_rubric(rubric)
                return rubric
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in rubric response: {e}")
        
        raise ValueError("No JSON found in rubric response")
    
    def _validate_rubric(self, rubric: dict):
        """Validate rubric structure and totals."""
        if "criteria" not in rubric:
            raise ValueError("Rubric missing 'criteria' field")
        
        total = sum(c.get("points", 0) for c in rubric["criteria"])
        if total != 100:
            # Auto-correct if close
            if 95 <= total <= 105:
                # Scale to 100
                scale = 100 / total
                for c in rubric["criteria"]:
                    c["points"] = round(c["points"] * scale, 1)
            else:
                raise ValueError(f"Rubric points sum to {total}, expected 100")


class RubricEvaluator:
    """Evaluates workspaces against rubrics."""
    
    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL):
        from .config import MODEL_SPECS
        max_output = MODEL_SPECS.get(model_id, {}).get("max_output", 16384)
        self.model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            max_tokens=max_output,
        )
    
    def evaluate(self, workspace: Path, rubric: dict, 
                 additional_evidence: str = "") -> EvaluationResult:
        """Evaluate a workspace against a rubric.
        
        Args:
            workspace: Path to the workspace to evaluate
            rubric: The rubric dict with criteria
            additional_evidence: Optional additional context
            
        Returns:
            EvaluationResult with scores
        """
        # Collect evidence
        collector = EvidenceCollector(workspace)
        evidence = collector.collect(rubric)
        
        # Generate evaluation prompt
        prompt = load_prompt(
            "rubric_evaluator",
            rubric=rubric,
            evidence=evidence.to_dict(),
            workspace_name=workspace.name,
            additional_evidence=additional_evidence,
        )
        
        # Run evaluation with null callback to suppress stdout output
        agent = Agent(model=self.model, callback_handler=null_callback_handler)
        response = str(agent(prompt))
        
        # Parse response
        return self._parse_evaluation_response(response, workspace.name)
    
    def _parse_evaluation_response(self, response: str, workspace: str) -> EvaluationResult:
        """Parse evaluation JSON from LLM response."""
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError("No JSON found in evaluation response")
        
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in evaluation response: {e}")
        
        result = EvaluationResult(workspace=workspace)
        
        # Parse scores
        for score_data in data.get("scores", []):
            result.scores.append(CriterionScore(
                criterion_id=score_data.get("criterion_id", ""),
                criterion_name=score_data.get("criterion_name", ""),
                max_points=score_data.get("max_points", 0),
                awarded_points=score_data.get("awarded_points", 0),
                reasoning=score_data.get("reasoning", ""),
                evidence_used=score_data.get("evidence_used", []),
            ))
        
        # Parse category totals
        for cat_data in data.get("category_totals", []):
            result.category_totals.append(CategoryTotal(
                category=cat_data.get("category", ""),
                max_points=cat_data.get("max_points", 0),
                awarded_points=cat_data.get("awarded_points", 0),
                percentage=cat_data.get("percentage", 0),
            ))
        
        result.total_score = data.get("total_score", 0)
        result.max_score = data.get("max_score", 100)
        result.grade = data.get("grade", "F")
        result.summary = data.get("summary", "")
        result.strengths = data.get("strengths", [])
        result.weaknesses = data.get("weaknesses", [])
        result.evidence_gaps = data.get("evidence_gaps", [])
        
        return result
