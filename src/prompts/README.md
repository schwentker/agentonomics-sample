# Prompt Templates

This directory contains Jinja2 templates for all agent prompts used in the benchmark system.

## Usage

```python
from src.prompt_loader import load_prompt

prompt = load_prompt('template_name', variable1='value1', variable2='value2')
```

## Templates

| Template                       | Purpose                            | Variables                                                     |
| ------------------------------ | ---------------------------------- | ------------------------------------------------------------- |
| `decomposition.md`             | Task decomposition for multi-agent | `goal`, `tool_descriptions`                                   |
| `validation.md`                | Goal validation check              | `goal`, `tool_names`                                          |
| `single_agent.md`              | Single agent system prompt         | `enhanced_goal`, `tool_instructions`                          |
| `sub_agent.md`                 | Sub-agent task prompt              | `task` (object), `tool_instructions`                          |
| `orchestrator.md`              | Multi-agent orchestrator           | `goal`, `files`, `decomposition`, `verification_instructions` |
| `enhanced_goal.md`             | Goal with verification steps       | `goal`, `files`, `verification_steps`                         |
| `verification_instructions.md` | Dynamic verification steps         | `files`, `verification_steps`                                 |
| `rubric_generator.md`          | Generate assessment rubric         | `goal`                                                        |
| `rubric_evaluator.md`          | Evaluate workspace against rubric  | `rubric`, `evidence`, `workspace_name`, `additional_evidence` |

## Jinja2 Features

Templates support:

- Variable interpolation: `{{ variable }}`
- Conditionals: `{% if condition %}...{% endif %}`
- Loops: `{% for item in items %}...{% endfor %}`
- Custom tests: `is endswith('.py')`, `is startswith('test_')`
- Template includes: `{% include 'other_template.md' %}`

## Adding New Templates

1. Create a `.md` file in this directory
2. Use Jinja2 syntax for dynamic content
3. Load with `load_prompt('filename_without_extension', **kwargs)`
