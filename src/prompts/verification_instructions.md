{% if files or verification_steps %}

## MANDATORY VERIFICATION STEPS

You MUST complete these verification steps before finishing. These steps ensure your work is complete and correct.

{% set step_num = namespace(value=1) %}
{% if files %}

### Step {{ step_num.value }}: Verify all required files exist

Use `list_directory` to confirm these files were created:
{% for file in files %}

- `{{ file.path }}`{% if file.description %} - {{ file.description }}{% endif %}

{% endfor %}
{% set step_num.value = step_num.value + 1 %}
{% endif %}
{% set code_files = [] %}
{% for file in files %}
{% if file.path is endswith('.py') %}
{% set _ = code_files.append(file) %}
{% endif %}
{% endfor %}
{% if code_files %}

### Step {{ step_num.value }}: Verify Python syntax

Read each Python file to confirm it has valid syntax:
{% for file in code_files %}

- `{{ file.path }}`
  {% endfor %}
  {% set step_num.value = step_num.value + 1 %}
  {% endif %}
  {% set test_files = [] %}
  {% for file in files %}
  {% if file.path is startswith('test_') and file.path is endswith('.py') %}
  {% set _ = test_files.append(file) %}
  {% endif %}
  {% endfor %}
  {% if test_files %}

### Step {{ step_num.value }}: Run the test suite

Use the `execute_command` tool to run the tests:

```
execute_command(command="python -m pytest {{ test_files[0].path }} -v")
```

If tests fail, fix the issues and re-run until all tests pass.
{% set step_num.value = step_num.value + 1 %}
{% endif %}
{% for vs in verification_steps %}

### Step {{ step_num.value }}: {{ vs.description }}

Tool: `{{ vs.tool_to_use }}`
Expected: {{ vs.expected_outcome }}
{% set step_num.value = step_num.value + 1 %}
{% endfor %}

### Final Step: Report verification results

In your final response, include a verification summary:

```
## Verification Results
{% for file in files %}
- [ ] {{ file.path }} exists and is valid
{% endfor %}
{% if test_files %}
- [ ] All tests pass
{% endif %}
```

{% endif %}
