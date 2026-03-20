{{ goal }}

{% if files %}

## Required Output Files

{% for file in files %}

- `{{ file.path }}`{% if file.description %} - {{ file.description }}{% endif %}

{% endfor %}
{% endif %}

{% include 'verification_instructions.md' %}

IMPORTANT: Do not consider your task complete until ALL verification steps pass. If any step fails, fix the issue and re-verify.
