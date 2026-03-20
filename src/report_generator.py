"""Benchmark report generation with Mermaid visualizations."""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .validator import ValidationResult
from .rubric_evaluator import EvaluationResult
from .config import calculate_cost, FileMetrics, MODEL_SPECS


# Mermaid theme configuration for consistent styling
MERMAID_THEME = """%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#4F46E5',
    'primaryTextColor': '#fff',
    'primaryBorderColor': '#3730A3',
    'lineColor': '#6366F1',
    'secondaryColor': '#10B981',
    'tertiaryColor': '#F59E0B',
    'errorColor': '#EF4444',
    'errorTextColor': '#fff',
    'errorBorderColor': '#DC2626',
    'xyChart': {
      'plotColorPalette': '#4F46E5, #10B981, #F59E0B, #EF4444, #8B5CF6, #EC4899'
    }
  }
}}%%"""

# Colors for Single Agent (indigo/purple tones) and Multi-Agent (green/teal tones)
SINGLE_AGENT_COLOR = "#4F46E5"  # Indigo
MULTI_AGENT_COLOR = "#10B981"   # Emerald/Green
SINGLE_AGENT_SECONDARY = "#8B5CF6"  # Purple
MULTI_AGENT_SECONDARY = "#14B8A6"   # Teal
ERROR_COLOR = "#EF4444"  # Red
WARNING_COLOR = "#F59E0B"  # Amber


class ReportGenerator:
    """Generates benchmark comparison reports with Mermaid visualizations."""
    
    def __init__(self, output_dir: Path, config: dict | None = None):
        self.output_dir = output_dir
        self.report_data: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "benchmark_config": config or {},
            "single_agent": {},
            "multi_agent": {},
            "comparison": {},
            "rubric": None,
            "rubric_evaluation": {"single_agent": None, "multi_agent": None},
        }
    
    def set_config(self, config: dict):
        self.report_data["benchmark_config"] = config
    
    def set_rubric(self, rubric: dict):
        self.report_data["rubric"] = rubric
    
    def add_single_agent_results(self, metrics: dict[str, Any], result: dict[str, Any],
                                  validation: ValidationResult | None = None,
                                  file_metrics: FileMetrics | None = None):
        model_id = self.report_data["benchmark_config"].get("model_id", "claude-sonnet-4-6")
        tokens = metrics.get("tokens", {})
        costs = calculate_cost(model_id, tokens.get("input_tokens", 0), tokens.get("output_tokens", 0))
        
        self.report_data["single_agent"] = {
            "metrics": metrics, "costs": costs, "success": result.get("success", False),
            "error": result.get("error"), "validation": validation.to_dict() if validation else None,
            "file_metrics": file_metrics.to_dict() if file_metrics else None,
        }

    def add_multi_agent_results(self, metrics: dict[str, Any], result: dict[str, Any], 
                                 decomposition_report: str, validation: ValidationResult | None = None,
                                 file_metrics: FileMetrics | None = None, sub_agent_metrics: list[dict] | None = None):
        model_id = self.report_data["benchmark_config"].get("model_id", "claude-sonnet-4-6")
        total_tokens = metrics.get("total_tokens", {})
        costs = calculate_cost(model_id, total_tokens.get("input_tokens", 0), total_tokens.get("output_tokens", 0))
        
        agent_costs = []
        if sub_agent_metrics:
            for am in sub_agent_metrics:
                at = am.get("tokens", {})
                ac = calculate_cost(model_id, at.get("input_tokens", 0), at.get("output_tokens", 0))
                agent_costs.append({
                    "agent_name": am.get("agent_name", "unknown"), "tokens": at, "costs": ac,
                    "tool_calls": am.get("tool_calls", 0), "tool_calls_by_type": am.get("tool_calls_by_type", {}),
                    "error_metrics": am.get("error_metrics", {}), "error_rate_percent": am.get("error_rate_percent", 0),
                })
        
        self.report_data["multi_agent"] = {
            "metrics": metrics, "costs": costs, "success": result.get("success", False),
            "error": result.get("error"), "decomposition_report": decomposition_report,
            "task_count": len(result.get("task_results", {})),
            "validation": validation.to_dict() if validation else None,
            "file_metrics": file_metrics.to_dict() if file_metrics else None,
            "agent_breakdown": agent_costs,
        }
    
    def add_rubric_evaluation(self, agent_type: str, evaluation: EvaluationResult):
        self.report_data["rubric_evaluation"][agent_type] = evaluation.to_dict()
    
    def _calculate_comparison(self):
        single = self.report_data["single_agent"].get("metrics", {})
        multi = self.report_data["multi_agent"].get("metrics", {})
        
        single_tokens = single.get("tokens", {})
        multi_tokens = multi.get("total_tokens", {})
        single_total = single_tokens.get("total_tokens", 0)
        multi_total = multi_tokens.get("total_tokens", 0)
        
        single_time = single.get("execution_time_seconds", 0)
        multi_time = multi.get("total_execution_time_seconds", 0)
        
        single_errors = single.get("error_metrics", {})
        multi_errors = multi.get("error_metrics", {})
        
        single_costs = self.report_data["single_agent"].get("costs", {})
        multi_costs = self.report_data["multi_agent"].get("costs", {})
        
        single_val = self.report_data["single_agent"].get("validation")
        multi_val = self.report_data["multi_agent"].get("validation")
        single_validated = single_val.get("overall_success", False) if single_val else None
        multi_validated = multi_val.get("overall_success", False) if multi_val else None
        
        single_eval = self.report_data["rubric_evaluation"].get("single_agent")
        multi_eval = self.report_data["rubric_evaluation"].get("multi_agent")
        single_score = single_eval.get("total_score", 0) if single_eval else None
        multi_score = multi_eval.get("total_score", 0) if multi_eval else None
        
        single_files = self.report_data["single_agent"].get("file_metrics", {})
        multi_files = self.report_data["multi_agent"].get("file_metrics", {})
        
        self.report_data["comparison"] = {
            "input_token_difference": multi_tokens.get("input_tokens", 0) - single_tokens.get("input_tokens", 0),
            "output_token_difference": multi_tokens.get("output_tokens", 0) - single_tokens.get("output_tokens", 0),
            "total_token_difference": multi_total - single_total,
            "token_ratio": multi_total / single_total if single_total > 0 else 0,
            "time_difference_seconds": multi_time - single_time,
            "time_ratio": multi_time / single_time if single_time > 0 else 0,
            "input_cost_difference": multi_costs.get("input_cost", 0) - single_costs.get("input_cost", 0),
            "output_cost_difference": multi_costs.get("output_cost", 0) - single_costs.get("output_cost", 0),
            "total_cost_difference": multi_costs.get("total_cost", 0) - single_costs.get("total_cost", 0),
            "single_error_rate": single_errors.get("error_rate_percent", single.get("error_rate_percent", 0)),
            "multi_error_rate": multi_errors.get("error_rate_percent", 0),
            "single_total_errors": single_errors.get("total_errors", 0),
            "multi_total_errors": multi_errors.get("total_errors", 0),
            "single_retry_time": single_errors.get("time_spent_on_retries_seconds", 0),
            "multi_retry_time": multi_errors.get("time_spent_on_retries_seconds", 0),
            "single_agent_more_efficient": single_total < multi_total,
            "single_agent_faster": single_time < multi_time,
            "single_agent_cheaper": single_costs.get("total_cost", 0) < multi_costs.get("total_cost", 0),
            "single_agent_fewer_errors": single_errors.get("total_errors", 0) < multi_errors.get("total_errors", 0),
            "single_agent_validated": single_validated,
            "multi_agent_validated": multi_validated,
            "both_validated": single_validated and multi_validated if single_validated is not None and multi_validated is not None else None,
            "single_agent_score": single_score,
            "multi_agent_score": multi_score,
            "score_difference": (multi_score - single_score) if single_score is not None and multi_score is not None else None,
            "higher_quality": "single_agent" if single_score and multi_score and single_score > multi_score else "multi_agent" if multi_score and single_score and multi_score > single_score else "tie",
            "single_files_created": single_files.get("total_files", 0),
            "multi_files_created": multi_files.get("total_files", 0),
            "single_bytes_created": single_files.get("total_bytes", 0),
            "multi_bytes_created": multi_files.get("total_bytes", 0),
        }

    def _generate_token_comparison_chart(self) -> str:
        single_tokens = self.report_data["single_agent"].get("metrics", {}).get("tokens", {})
        multi_tokens = self.report_data["multi_agent"].get("metrics", {}).get("total_tokens", {})
        si, so = single_tokens.get("input_tokens", 0) // 1000, single_tokens.get("output_tokens", 0) // 1000
        mi, mo = multi_tokens.get("input_tokens", 0) // 1000, multi_tokens.get("output_tokens", 0) // 1000
        max_val = max(si, so, mi, mo, 1) + 10
        return f"""```mermaid
%%{{init: {{'theme': 'base', 'themeVariables': {{'xyChart': {{'plotColorPalette': '{SINGLE_AGENT_COLOR}, {SINGLE_AGENT_SECONDARY}, {MULTI_AGENT_COLOR}, {MULTI_AGENT_SECONDARY}'}}}}}}}}%%
xychart-beta
    title "Token Usage Comparison (in thousands)"
    x-axis ["Single Input", "Single Output", "Multi Input", "Multi Output"]
    y-axis "Tokens (K)" 0 --> {max_val}
    bar [{si}, {so}, {mi}, {mo}]
```"""

    def _generate_cost_pie_chart(self, agent_type: str) -> str:
        costs = self.report_data["single_agent" if agent_type == "single" else "multi_agent"].get("costs", {})
        title = "Single Agent Cost" if agent_type == "single" else "Multi-Agent Cost"
        ic, oc = costs.get("input_cost", 0), costs.get("output_cost", 0)
        if ic == 0 and oc == 0: return ""
        return f"""```mermaid
{MERMAID_THEME}
pie showData
    title {title}
    "Input Cost" : {ic:.4f}
    "Output Cost" : {oc:.4f}
```"""

    def _generate_efficiency_radar(self) -> str:
        sm = self.report_data["single_agent"].get("metrics", {})
        mm = self.report_data["multi_agent"].get("metrics", {})
        st = sm.get("tokens", {}).get("total_tokens", 1)
        mt = mm.get("total_tokens", {}).get("total_tokens", 1)
        max_t = max(st, mt)
        se = self.report_data["rubric_evaluation"].get("single_agent")
        me = self.report_data["rubric_evaluation"].get("multi_agent")
        ss = se.get("total_score", 50) if se else 50
        ms = me.get("total_score", 50) if me else 50
        ste = round((1 - st / max_t) * 100) if max_t > 0 else 50
        mte = round((1 - mt / max_t) * 100) if max_t > 0 else 50
        return f"""```mermaid
{MERMAID_THEME}
quadrantChart
    title Efficiency vs Quality Comparison
    x-axis Low Efficiency --> High Efficiency
    y-axis Low Quality --> High Quality
    quadrant-1 Optimal
    quadrant-2 Quality Focus
    quadrant-3 Needs Improvement
    quadrant-4 Efficiency Focus
    Single Agent: [{max(0.1, min(0.9, ste/100))}, {max(0.1, min(0.9, ss/100))}]
    Multi Agent: [{max(0.1, min(0.9, mte/100))}, {max(0.1, min(0.9, ms/100))}]
```"""

    def _generate_error_comparison_chart(self) -> str:
        sm = self.report_data["single_agent"].get("metrics", {})
        mm = self.report_data["multi_agent"].get("metrics", {})
        se = sm.get("error_metrics", {})
        me = mm.get("error_metrics", {})
        st, stl, sr = se.get("total_errors", 0), se.get("tool_errors", 0), se.get("retry_count", 0)
        mt, mtl, mr = me.get("total_errors", 0), me.get("tool_errors", 0), me.get("retry_count", 0)
        mv = max(st, stl, sr, mt, mtl, mr, 1) + 2
        return f"""```mermaid
%%{{init: {{'theme': 'base', 'themeVariables': {{'xyChart': {{'plotColorPalette': '{SINGLE_AGENT_COLOR}, {SINGLE_AGENT_SECONDARY}, {WARNING_COLOR}, {MULTI_AGENT_COLOR}, {MULTI_AGENT_SECONDARY}, {ERROR_COLOR}'}}}}}}}}%%
xychart-beta
    title "Error Metrics Comparison"
    x-axis ["Single Total", "Single Tool", "Single Retries", "Multi Total", "Multi Tool", "Multi Retries"]
    y-axis "Count" 0 --> {mv}
    bar [{st}, {stl}, {sr}, {mt}, {mtl}, {mr}]
```"""

    def _generate_time_breakdown_chart(self) -> str:
        sm = self.report_data["single_agent"].get("metrics", {})
        mm = self.report_data["multi_agent"].get("metrics", {})
        st = sm.get("execution_time_seconds", 0)
        sef = sm.get("effective_execution_time_seconds", st)
        mt = mm.get("total_execution_time_seconds", 0)
        mef = mm.get("effective_execution_time_seconds", mt)
        max_val = max(st, mt, 1) + 10
        return f"""```mermaid
%%{{init: {{'theme': 'base', 'themeVariables': {{'xyChart': {{'plotColorPalette': '{SINGLE_AGENT_COLOR}, {WARNING_COLOR}, {MULTI_AGENT_COLOR}, {ERROR_COLOR}'}}}}}}}}%%
xychart-beta
    title "Execution Time Breakdown (seconds)"
    x-axis ["Single Effective", "Single Retry", "Multi Effective", "Multi Retry"]
    y-axis "Time (s)" 0 --> {max_val}
    bar [{sef:.1f}, {st - sef:.1f}, {mef:.1f}, {mt - mef:.1f}]
```"""

    def _generate_agent_error_breakdown(self) -> str:
        ab = self.report_data["multi_agent"].get("agent_breakdown", [])
        if not ab: return ""
        awe = [a for a in ab if a.get("error_metrics", {}).get("total_errors", 0) > 0]
        if not awe: return ""
        lines = [f'    "{a["agent_name"]}" : {a.get("error_metrics", {}).get("total_errors", 0)}' for a in awe]
        return f"""```mermaid
{MERMAID_THEME}
pie showData
    title Errors by Agent
{chr(10).join(lines)}
```"""

    def _generate_tool_usage_chart(self, agent_type: str) -> str:
        m = self.report_data["single_agent" if agent_type == "single" else "multi_agent"].get("metrics", {})
        title = "Single Agent Tool Usage" if agent_type == "single" else "Multi-Agent Tool Usage"
        tc = m.get("tool_calls_by_type", {})
        if not tc: return ""
        st = sorted(tc.items(), key=lambda x: -x[1])[:6]
        if not st: return ""
        lines = [f'    "{t[0]}" : {t[1]}' for t in st]
        return f"""```mermaid
{MERMAID_THEME}
pie showData
    title {title}
{chr(10).join(lines)}
```"""

    def _generate_quality_comparison_chart(self) -> str:
        se = self.report_data["rubric_evaluation"].get("single_agent")
        me = self.report_data["rubric_evaluation"].get("multi_agent")
        if not se and not me: return ""
        ss = se.get("total_score", 0) if se else 0
        ms = me.get("total_score", 0) if me else 0
        return f"""```mermaid
%%{{init: {{'theme': 'base', 'themeVariables': {{'xyChart': {{'plotColorPalette': '{SINGLE_AGENT_COLOR}, {MULTI_AGENT_COLOR}'}}}}}}}}%%
xychart-beta
    title "Quality Score Comparison"
    x-axis ["Single Agent", "Multi-Agent"]
    y-axis "Score" 0 --> 100
    bar [{ss}, {ms}]
```"""

    def _generate_category_comparison_chart(self) -> str:
        rubric = self.report_data.get("rubric")
        se = self.report_data["rubric_evaluation"].get("single_agent")
        me = self.report_data["rubric_evaluation"].get("multi_agent")
        if not rubric or (not se and not me): return ""
        sc = {c["category"]: c for c in (se.get("category_totals", []) if se else [])}
        mc = {c["category"]: c for c in (me.get("category_totals", []) if me else [])}
        cats = rubric.get("categories", [])[:5]
        if not cats: return ""
        labels = ", ".join(f'"{c["name"][:15]}"' for c in cats)
        sv = ", ".join(str(int(sc.get(c["name"], {}).get("percentage", 0))) for c in cats)
        mv = ", ".join(str(int(mc.get(c["name"], {}).get("percentage", 0))) for c in cats)
        return f"""```mermaid
%%{{init: {{'theme': 'base', 'themeVariables': {{'xyChart': {{'plotColorPalette': '{SINGLE_AGENT_COLOR}, {MULTI_AGENT_COLOR}'}}}}}}}}%%
xychart-beta
    title "Category Score Comparison (%)"
    x-axis [{labels}]
    y-axis "Score %" 0 --> 100
    bar [{sv}]
    line [{mv}]
```"""

    def _generate_postmortem_analysis(self) -> str:
        """Generate a non-domain-specific post-mortem analysis comparing outputs."""
        single = self.report_data["single_agent"]
        multi = self.report_data["multi_agent"]
        sf = single.get("file_metrics", {})
        mf = multi.get("file_metrics", {})
        sv = single.get("validation", {})
        mv = multi.get("validation", {})
        
        report = "\n---\n\n## Post-Mortem Analysis\n\n"
        report += "> This section provides objective comparisons of actual outputs beyond rubric scoring.\n\n"
        
        # File size comparison
        report += "### Output Size Comparison\n\n"
        s_bytes = sf.get("total_bytes", 0)
        m_bytes = mf.get("total_bytes", 0)
        s_files = sf.get("total_files", 0)
        m_files = mf.get("total_files", 0)
        
        if s_bytes > 0 and m_bytes > 0:
            size_ratio = m_bytes / s_bytes
            report += f"| Metric | Single Agent | Multi-Agent | Ratio |\n"
            report += f"|--------|-------------|-------------|-------|\n"
            report += f"| Total Files | {s_files} | {m_files} | {m_files/max(s_files,1):.1f}x |\n"
            report += f"| Total Bytes | {s_bytes:,} | {m_bytes:,} | {size_ratio:.1f}x |\n"
            report += f"| Avg Bytes/File | {s_bytes//max(s_files,1):,} | {m_bytes//max(m_files,1):,} | {(m_bytes/max(m_files,1))/(s_bytes/max(s_files,1)) if s_files > 0 and s_bytes > 0 else 0:.1f}x |\n\n"
            
            if size_ratio > 1.5:
                report += f"📊 Multi-agent produced **{size_ratio:.1f}x more output** by volume.\n\n"
            elif size_ratio < 0.67:
                report += f"📊 Single agent produced **{1/size_ratio:.1f}x more output** by volume.\n\n"
        
        # Per-extension breakdown comparison
        s_ext = sf.get("by_extension", {})
        m_ext = mf.get("by_extension", {})
        if s_ext and m_ext:
            all_exts = set(s_ext.keys()) | set(m_ext.keys())
            code_exts = {e for e in all_exts if e in ['.py', '.js', '.ts', '.java', '.go', '.rs', '.c', '.cpp', '.rb', '.php']}
            
            if code_exts:
                report += "### Code File Comparison\n\n"
                report += "| Extension | Single (bytes) | Multi (bytes) | Ratio |\n"
                report += "|-----------|---------------|---------------|-------|\n"
                for ext in sorted(code_exts):
                    s_b = s_ext.get(ext, {}).get("bytes", 0)
                    m_b = m_ext.get(ext, {}).get("bytes", 0)
                    ratio = m_b / s_b if s_b > 0 else 0
                    report += f"| {ext} | {s_b:,} | {m_b:,} | {ratio:.1f}x |\n"
                report += "\n"
        
        # Test count comparison
        s_tests = sv.get("test_validation", {}) if sv else {}
        m_tests = mv.get("test_validation", {}) if mv else {}
        s_passed = s_tests.get("passed", 0)
        m_passed = m_tests.get("passed", 0)
        
        if s_passed > 0 or m_passed > 0:
            report += "### Test Coverage Comparison\n\n"
            report += f"| Metric | Single Agent | Multi-Agent |\n"
            report += f"|--------|-------------|-------------|\n"
            report += f"| Tests Written | {s_passed} | {m_passed} |\n"
            if s_passed > 0 and m_passed > 0:
                report += f"| Test Ratio | 1.0x | {m_passed/s_passed:.1f}x |\n"
            report += "\n"
            
            if m_passed > s_passed * 1.5:
                report += f"📊 Multi-agent wrote **{m_passed/s_passed:.1f}x more tests** than single agent.\n\n"
            elif s_passed > m_passed * 1.5:
                report += f"📊 Single agent wrote **{s_passed/m_passed:.1f}x more tests** than multi-agent.\n\n"
        
        # Efficiency analysis
        sm = single.get("metrics", {})
        mm = multi.get("metrics", {})
        s_tokens = sm.get("tokens", {}).get("total_tokens", 0)
        m_tokens = mm.get("total_tokens", {}).get("total_tokens", 0)
        
        if s_bytes > 0 and m_bytes > 0 and s_tokens > 0 and m_tokens > 0:
            report += "### Output Efficiency\n\n"
            s_efficiency = s_bytes / s_tokens * 1000  # bytes per 1K tokens
            m_efficiency = m_bytes / m_tokens * 1000
            report += f"| Metric | Single Agent | Multi-Agent |\n"
            report += f"|--------|-------------|-------------|\n"
            report += f"| Bytes per 1K tokens | {s_efficiency:.1f} | {m_efficiency:.1f} |\n"
            report += f"| Tokens per output byte | {s_tokens/s_bytes:.1f} | {m_tokens/m_bytes:.1f} |\n\n"
            
            if s_efficiency > m_efficiency * 1.5:
                report += f"📊 Single agent was **{s_efficiency/m_efficiency:.1f}x more efficient** at producing output per token spent.\n\n"
            elif m_efficiency > s_efficiency * 1.5:
                report += f"📊 Multi-agent was **{m_efficiency/s_efficiency:.1f}x more efficient** at producing output per token spent.\n\n"
        
        # Key observations
        report += "### Key Observations\n\n"
        observations = []
        
        if m_bytes > s_bytes * 2:
            observations.append(f"Multi-agent produced significantly more output ({m_bytes/s_bytes:.1f}x) which may indicate more thorough implementation")
        elif s_bytes > m_bytes * 2:
            observations.append(f"Single agent produced significantly more output ({s_bytes/m_bytes:.1f}x) which may indicate more thorough implementation")
        
        if m_passed > s_passed * 1.5:
            observations.append(f"Multi-agent wrote more comprehensive tests ({m_passed} vs {s_passed})")
        elif s_passed > m_passed * 1.5:
            observations.append(f"Single agent wrote more comprehensive tests ({s_passed} vs {m_passed})")
        
        if s_tokens > 0 and m_tokens > 0:
            token_ratio = m_tokens / s_tokens
            if token_ratio > 5:
                observations.append(f"Multi-agent used {token_ratio:.1f}x more tokens, suggesting significant overhead from task decomposition and coordination")
        
        se = self.report_data["rubric_evaluation"].get("single_agent")
        me = self.report_data["rubric_evaluation"].get("multi_agent")
        if se and me:
            ss = se.get("total_score", 0)
            ms = me.get("total_score", 0)
            if ss == ms and ss == 100:
                observations.append("Both agents achieved perfect rubric scores, but this doesn't capture qualitative differences in output depth or thoroughness")
        
        if observations:
            for obs in observations:
                report += f"- {obs}\n"
        else:
            report += "- No significant differences detected in output characteristics\n"
        
        report += "\n"
        return report

    def generate_markdown_report(self) -> str:
        self._calculate_comparison()
        
        config = self.report_data.get("benchmark_config", {})
        single = self.report_data["single_agent"]
        multi = self.report_data["multi_agent"]
        comp = self.report_data["comparison"]
        
        sm = single.get("metrics", {})
        mm = multi.get("metrics", {})
        st = sm.get("tokens", {})
        mt = mm.get("total_tokens", {})
        sc = single.get("costs", {})
        mc = multi.get("costs", {})
        sv = single.get("validation")
        mv = multi.get("validation")
        se = self.report_data["rubric_evaluation"].get("single_agent")
        me = self.report_data["rubric_evaluation"].get("multi_agent")
        sf = single.get("file_metrics", {})
        mf = multi.get("file_metrics", {})
        serr = sm.get("error_metrics", {})
        merr = mm.get("error_metrics", {})
        
        def val_status(v):
            if v is None: return "N/A"
            return "✅ Passed" if v.get("overall_success") else "❌ Failed"
        
        def score_display(e):
            if e is None: return "N/A"
            return f"{e.get('total_score', 0)}/100 ({e.get('grade', '?')})"
        
        def fmt_cost(c): return f"${c:.4f}"
        
        def fmt_bytes(s):
            for u in ['B', 'KB', 'MB', 'GB']:
                if s < 1024: return f"{s:.1f} {u}"
                s /= 1024
            return f"{s:.1f} TB"
        
        report = f"""# Agent Benchmark Report

**Generated:** {self.report_data["timestamp"]}

---

## Benchmark Configuration

| Parameter | Value |
|-----------|-------|
| Goal File | `{config.get("goal_file", "N/A")}` |
| Model | `{config.get("model_id", "N/A")}` |
| Context Limit | {config.get("model_context_limit", 0):,} tokens |
| Max Output | {config.get("max_tokens", 0):,} tokens |
| Temperature | {config.get("temperature", 1.0)} |
| Top-P | {config.get("top_p", "N/A")} |
| Top-K | {config.get("top_k", "N/A")} |
| Input Cost | ${config.get("model_input_cost_per_mtok", 0):.2f} / 1M tokens |
| Output Cost | ${config.get("model_output_cost_per_mtok", 0):.2f} / 1M tokens |

---

## Executive Summary

| Metric | Single Agent | Multi-Agent | Winner |
|--------|-------------|-------------|--------|
| Input Tokens | {st.get("input_tokens", 0):,} | {mt.get("input_tokens", 0):,} | {"🏆 Single" if st.get("input_tokens", 0) < mt.get("input_tokens", 0) else "🏆 Multi"} |
| Output Tokens | {st.get("output_tokens", 0):,} | {mt.get("output_tokens", 0):,} | {"🏆 Single" if st.get("output_tokens", 0) < mt.get("output_tokens", 0) else "🏆 Multi"} |
| **Total Tokens** | **{st.get("total_tokens", 0):,}** | **{mt.get("total_tokens", 0):,}** | **{"🏆 Single" if comp.get("single_agent_more_efficient") else "🏆 Multi"}** |
| Execution Time | {sm.get("execution_time_seconds", 0):.2f}s | {mm.get("total_execution_time_seconds", 0):.2f}s | {"🏆 Single" if comp.get("single_agent_faster") else "🏆 Multi"} |
| **Total Cost** | **{fmt_cost(sc.get("total_cost", 0))}** | **{fmt_cost(mc.get("total_cost", 0))}** | **{"🏆 Single" if comp.get("single_agent_cheaper") else "🏆 Multi"}** |
| Tool Calls | {sm.get("tool_calls", 0)} | {mm.get("total_tool_calls", 0)} | - |
| Files Created | {sf.get("total_files", 0)} | {mf.get("total_files", 0)} | - |
| Bytes Written | {fmt_bytes(sf.get("total_bytes", 0))} | {fmt_bytes(mf.get("total_bytes", 0))} | - |
| **Error Rate** | **{serr.get("error_rate_percent", sm.get("error_rate_percent", 0)):.1f}%** | **{merr.get("error_rate_percent", 0):.1f}%** | **{"🏆 Single" if comp.get("single_agent_fewer_errors") else "🏆 Multi"}** |
| Output Validated | {val_status(sv)} | {val_status(mv)} | - |
| **Quality Score** | **{score_display(se)}** | **{score_display(me)}** | **{"🏆 Single" if comp.get("higher_quality") == "single_agent" else "🏆 Multi" if comp.get("higher_quality") == "multi_agent" else "Tie"}** |

---

## Visual Comparisons

### Token Usage

{self._generate_token_comparison_chart()}

### Efficiency vs Quality

{self._generate_efficiency_radar()}

### Quality Scores

{self._generate_quality_comparison_chart()}

---

## Error Rate Analysis

Tracking errors and retries is critical for understanding the true cost of task completion.

| Metric | Single Agent | Multi-Agent |
|--------|-------------|-------------|
| Total Errors | {serr.get("total_errors", 0)} | {merr.get("total_errors", 0)} |
| Tool Errors | {serr.get("tool_errors", 0)} | {merr.get("tool_errors", 0)} |
| Model Errors | {serr.get("model_errors", 0)} | {merr.get("model_errors", 0)} |
| Retry Count | {serr.get("retry_count", 0)} | {merr.get("retry_count", 0)} |
| Time on Retries | {serr.get("time_spent_on_retries_seconds", 0):.2f}s | {merr.get("time_spent_on_retries_seconds", 0):.2f}s |
| **Error Rate** | **{serr.get("error_rate_percent", sm.get("error_rate_percent", 0)):.2f}%** | **{merr.get("error_rate_percent", 0):.2f}%** |
| Effective Time | {sm.get("effective_execution_time_seconds", sm.get("execution_time_seconds", 0)):.2f}s | {mm.get("effective_execution_time_seconds", mm.get("total_execution_time_seconds", 0)):.2f}s |

{self._generate_error_comparison_chart()}

{self._generate_time_breakdown_chart()}

"""
        # Errors by type
        sbt = serr.get("errors_by_type", {})
        mbt = merr.get("errors_by_type", {})
        if sbt or mbt:
            all_types = set(sbt.keys()) | set(mbt.keys())
            if all_types:
                report += "### Errors by Type\n\n| Error Type | Single Agent | Multi-Agent |\n|------------|-------------|-------------|\n"
                for et in sorted(all_types):
                    report += f"| {et} | {sbt.get(et, 0)} | {mbt.get(et, 0)} |\n"
        
        # Errors by tool
        sbtl = serr.get("errors_by_tool", {})
        mbtl = merr.get("errors_by_tool", {})
        if sbtl or mbtl:
            all_tools = set(sbtl.keys()) | set(mbtl.keys())
            if all_tools:
                report += "\n### Errors by Tool\n\n| Tool | Single Agent | Multi-Agent |\n|------|-------------|-------------|\n"
                for tl in sorted(all_tools):
                    report += f"| {tl} | {sbtl.get(tl, 0)} | {mbtl.get(tl, 0)} |\n"
        
        # Per-agent error breakdown
        ab = multi.get("agent_breakdown", [])
        if ab:
            report += "\n### Multi-Agent Error Breakdown by Sub-Agent\n\n| Agent | Errors | Error Rate | Retry Time |\n|-------|--------|------------|------------|\n"
            for a in ab:
                ae = a.get("error_metrics", {})
                report += f"| {a.get('agent_name', 'unknown')} | {ae.get('total_errors', 0)} | {a.get('error_rate_percent', 0):.1f}% | {ae.get('time_spent_on_retries_seconds', 0):.2f}s |\n"
            aec = self._generate_agent_error_breakdown()
            if aec: report += f"\n{aec}\n"
        
        report += f"""
---

## Cost Analysis

| Cost Type | Single Agent | Multi-Agent | Difference |
|-----------|-------------|-------------|------------|
| Input Cost | {fmt_cost(sc.get("input_cost", 0))} | {fmt_cost(mc.get("input_cost", 0))} | {fmt_cost(comp.get("input_cost_difference", 0))} |
| Output Cost | {fmt_cost(sc.get("output_cost", 0))} | {fmt_cost(mc.get("output_cost", 0))} | {fmt_cost(comp.get("output_cost_difference", 0))} |
| **Total** | **{fmt_cost(sc.get("total_cost", 0))}** | **{fmt_cost(mc.get("total_cost", 0))}** | **{fmt_cost(comp.get("total_cost_difference", 0))}** |

{self._generate_cost_pie_chart("single")}

{self._generate_cost_pie_chart("multi")}

---

## Token Usage Details

### Single Agent

| Category | Tokens | Cost |
|----------|--------|------|
| Input | {st.get("input_tokens", 0):,} | {fmt_cost(sc.get("input_cost", 0))} |
| Output | {st.get("output_tokens", 0):,} | {fmt_cost(sc.get("output_cost", 0))} |
| **Total** | **{st.get("total_tokens", 0):,}** | **{fmt_cost(sc.get("total_cost", 0))}** |

### Multi-Agent (Aggregated)

| Category | Tokens | Cost |
|----------|--------|------|
| Input | {mt.get("input_tokens", 0):,} | {fmt_cost(mc.get("input_cost", 0))} |
| Output | {mt.get("output_tokens", 0):,} | {fmt_cost(mc.get("output_cost", 0))} |
| **Total** | **{mt.get("total_tokens", 0):,}** | **{fmt_cost(mc.get("total_cost", 0))}** |

"""
        if ab:
            report += "### Multi-Agent Breakdown by Sub-Agent\n\n| Agent | Input | Output | Total | Cost | Tools | Errors |\n|-------|-------|--------|-------|------|-------|--------|\n"
            for a in ab:
                at = a.get("tokens", {})
                ac = a.get("costs", {})
                ae = a.get("error_metrics", {})
                report += f"| {a.get('agent_name', 'unknown')} | {at.get('input_tokens', 0):,} | {at.get('output_tokens', 0):,} | {at.get('total_tokens', 0):,} | {fmt_cost(ac.get('total_cost', 0))} | {a.get('tool_calls', 0)} | {ae.get('total_errors', 0)} |\n"
        
        report += f"""
---

## Tool Usage Analysis

### Single Agent Tool Calls

{self._generate_tool_usage_chart("single")}

"""
        tc = sm.get("tool_calls_by_type", {})
        if tc:
            report += "\n| Tool | Calls |\n|------|-------|\n"
            for t, c in sorted(tc.items(), key=lambda x: -x[1]):
                report += f"| {t} | {c} |\n"
        
        report += f"""
### Multi-Agent Tool Calls (Aggregated)

{self._generate_tool_usage_chart("multi")}

"""
        tc = mm.get("tool_calls_by_type", {})
        if tc:
            report += "\n| Tool | Calls |\n|------|-------|\n"
            for t, c in sorted(tc.items(), key=lambda x: -x[1]):
                report += f"| {t} | {c} |\n"
        
        report += "\n---\n\n## Files Created\n\n### Single Agent\n"
        if sf:
            report += f"\n- **Total Files:** {sf.get('total_files', 0)}\n- **Total Size:** {sf.get('total_bytes_formatted', '0 B')}\n\n| Extension | Files | Size |\n|-----------|-------|------|\n"
            for ext, data in sorted(sf.get("by_extension", {}).items(), key=lambda x: -x[1]["count"]):
                report += f"| {ext} | {data['count']} | {fmt_bytes(data['bytes'])} |\n"
        
        report += "\n### Multi-Agent\n"
        if mf:
            report += f"\n- **Total Files:** {mf.get('total_files', 0)}\n- **Total Size:** {mf.get('total_bytes_formatted', '0 B')}\n\n| Extension | Files | Size |\n|-----------|-------|------|\n"
            for ext, data in sorted(mf.get("by_extension", {}).items(), key=lambda x: -x[1]["count"]):
                report += f"| {ext} | {data['count']} | {fmt_bytes(data['bytes'])} |\n"
        
        # Rubric evaluation
        report += "\n---\n\n## Rubric-Based Quality Evaluation\n\n"
        report += """> ⚠️ **Rubric Scope Disclaimer**
>
> This rubric evaluates whether outputs meet minimum functional requirements (files exist, functions work, 
> tests pass). It uses threshold-based scoring and does not measure:
> - Depth of test coverage (number of test cases, edge case comprehensiveness)
> - Documentation thoroughness (length, detail, examples)
> - Code sophistication or elegance
> - Implementation completeness beyond requirements
>
> Two outputs may score identically while differing significantly in quality dimensions not captured by the rubric.

"""
        rubric = self.report_data.get("rubric")
        if rubric:
            report += f"### Evaluation Rubric\n\n**Goal Type:** {rubric.get('goal_type', 'N/A')}\n**Summary:** {rubric.get('goal_summary', 'N/A')}\n\n{self._generate_category_comparison_chart()}\n\n#### Categories\n\n| Category | Weight | Single Agent | Multi-Agent |\n|----------|--------|--------------|-------------|\n"
            scat = {c["category"]: c for c in (se.get("category_totals", []) if se else [])}
            mcat = {c["category"]: c for c in (me.get("category_totals", []) if me else [])}
            for cat in rubric.get("categories", []):
                cn = cat["name"]
                report += f"| {cn} | {cat['weight']}% | {scat.get(cn, {}).get('percentage', 0):.0f}% | {mcat.get(cn, {}).get('percentage', 0):.0f}% |\n"
        
        report += "\n### Single Agent Evaluation\n\n"
        if se:
            report += f"**Score:** {se.get('total_score', 0)}/100 (Grade: {se.get('grade', '?')})\n\n**Summary:** {se.get('summary', 'N/A')}\n\n**Strengths:**\n"
            for s in se.get("strengths", []): report += f"- {s}\n"
            report += "\n**Weaknesses:**\n"
            for w in se.get("weaknesses", []): report += f"- {w}\n"
            report += "\n<details>\n<summary>Detailed Scores</summary>\n\n| Criterion | Points | Reasoning |\n|-----------|--------|----------|\n"
            for sc in se.get("scores", []):
                r = sc.get('reasoning', '')[:80] + ("..." if len(sc.get('reasoning', '')) > 80 else "")
                report += f"| {sc['criterion_name']} | {sc['awarded_points']}/{sc['max_points']} | {r} |\n"
            report += "\n</details>\n"
        else:
            report += "*No rubric evaluation performed*\n"
        
        report += "\n### Multi-Agent Evaluation\n\n"
        if me:
            report += f"**Score:** {me.get('total_score', 0)}/100 (Grade: {me.get('grade', '?')})\n\n**Summary:** {me.get('summary', 'N/A')}\n\n**Strengths:**\n"
            for s in me.get("strengths", []): report += f"- {s}\n"
            report += "\n**Weaknesses:**\n"
            for w in me.get("weaknesses", []): report += f"- {w}\n"
            report += "\n<details>\n<summary>Detailed Scores</summary>\n\n| Criterion | Points | Reasoning |\n|-----------|--------|----------|\n"
            for sc in me.get("scores", []):
                r = sc.get('reasoning', '')[:80] + ("..." if len(sc.get('reasoning', '')) > 80 else "")
                report += f"| {sc['criterion_name']} | {sc['awarded_points']}/{sc['max_points']} | {r} |\n"
            report += "\n</details>\n"
        else:
            report += "*No rubric evaluation performed*\n"
        
        # Validation
        report += "\n---\n\n## Output Validation Results\n\n"
        if sv:
            report += f"### Single Agent\n\n| Check | Result |\n|-------|--------|\n| Files Found | {sv.get('files_found', 0)}/{len(sv.get('files_expected', []))} |\n| Files Missing | {sv.get('files_missing', 0)} |\n| Syntax Errors | {sv.get('syntax_errors', 0)} |\n"
            tv = sv.get("test_validation")
            if tv:
                report += f"| Tests Ran | {'Yes' if tv.get('ran') else 'No'} |\n| Tests Passed | {tv.get('passed', 0)} |\n| Tests Failed | {tv.get('failed', 0)} |\n"
        
        if mv:
            report += f"\n### Multi-Agent\n\n| Check | Result |\n|-------|--------|\n| Files Found | {mv.get('files_found', 0)}/{len(mv.get('files_expected', []))} |\n| Files Missing | {mv.get('files_missing', 0)} |\n| Syntax Errors | {mv.get('syntax_errors', 0)} |\n"
            tv = mv.get("test_validation")
            if tv:
                report += f"| Tests Ran | {'Yes' if tv.get('ran') else 'No'} |\n| Tests Passed | {tv.get('passed', 0)} |\n| Tests Failed | {tv.get('failed', 0)} |\n"
        
        report += f"\n---\n\n## Task Decomposition Analysis\n\n{multi.get('decomposition_report', 'No decomposition data available.')}\n"
        
        # Post-mortem analysis
        report += self._generate_postmortem_analysis()
        
        # Conclusions
        report += f"""
---

## Conclusions

### Efficiency Analysis

| Metric | Single Agent | Multi-Agent | Ratio |
|--------|-------------|-------------|-------|
| Tokens | {st.get("total_tokens", 0):,} | {mt.get("total_tokens", 0):,} | {comp.get("token_ratio", 0):.2f}x |
| Time | {sm.get("execution_time_seconds", 0):.1f}s | {mm.get("total_execution_time_seconds", 0):.1f}s | {comp.get("time_ratio", 0):.2f}x |
| Cost | {fmt_cost(sc.get("total_cost", 0))} | {fmt_cost(mc.get("total_cost", 0))} | {(mc.get("total_cost", 0) / sc.get("total_cost", 1)) if sc.get("total_cost", 0) > 0 else 0:.2f}x |
| Errors | {serr.get("total_errors", 0)} | {merr.get("total_errors", 0)} | - |
| Retry Time | {serr.get("time_spent_on_retries_seconds", 0):.1f}s | {merr.get("time_spent_on_retries_seconds", 0):.1f}s | - |

"""
        if se and me:
            ss = se.get("total_score", 0)
            ms = me.get("total_score", 0)
            stot = st.get("total_tokens", 1)
            mtot = mt.get("total_tokens", 1)
            report += f"""### Quality vs Efficiency

| Metric | Single Agent | Multi-Agent |
|--------|-------------|-------------|
| Quality Score | {ss}/100 | {ms}/100 |
| Quality/1K Tokens | {(ss / stot) * 1000:.3f} | {(ms / mtot) * 1000:.3f} |
| Cost per Quality Point | {fmt_cost(sc.get("total_cost", 0) / max(ss, 1))} | {fmt_cost(mc.get("total_cost", 0) / max(ms, 1))} |

"""
        
        report += """
### Recommendations

**Use Single Agent when:**
- Token/cost efficiency is critical
- Task is straightforward or linear
- Context continuity matters
- Error recovery needs to be centralized

**Use Multi-Agent when:**
- Task has clear separable components
- Quality justifies additional cost
- Parallel execution is beneficial
- Isolated error handling per task is preferred

---

*Report generated by Agent Benchmark System*
"""
        return report
    
    def save_report(self):
        json_file = self.output_dir / "benchmark_report.json"
        with open(json_file, "w") as f:
            json.dump(self.report_data, f, indent=2, default=str)
        
        md_report = self.generate_markdown_report()
        md_file = self.output_dir / "benchmark_report.md"
        with open(md_file, "w") as f:
            f.write(md_report)
        
        if self.report_data.get("rubric"):
            rubric_file = self.output_dir / "rubric.json"
            with open(rubric_file, "w") as f:
                json.dump(self.report_data["rubric"], f, indent=2)
        
        return md_file
