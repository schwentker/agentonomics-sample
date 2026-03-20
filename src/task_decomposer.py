"""Task decomposition for multi-agent orchestration."""
import json
from strands import Agent
from strands.models.anthropic import AnthropicModel
from pydantic import BaseModel, Field, field_validator

from .prompt_loader import load_prompt


class SubTask(BaseModel):
    """A decomposed sub-task for a specialized agent."""
    id: str = Field(description="Unique identifier for the task")
    name: str = Field(description="Short descriptive name")
    description: str = Field(description="Detailed description of what needs to be done")
    tools_required: list[str] = Field(description="List of tool names needed for this task")
    dependencies: list[str] = Field(default_factory=list, description="IDs of tasks this depends on")
    rationale: str = Field(description="Why this task was separated")
    
    @field_validator('dependencies', mode='before')
    @classmethod
    def ensure_list(cls, v):
        """Ensure dependencies is always a list, even if None is provided."""
        if v is None:
            return []
        return v


class TaskDecomposition(BaseModel):
    """Complete task decomposition result."""
    original_goal: str = Field(description="The original goal being decomposed")
    decomposition_approach: str = Field(description="Explanation of how the goal was broken down")
    separation_rationale: str = Field(description="Why tasks were separated this way")
    tasks: list[SubTask] = Field(description="List of decomposed sub-tasks")





class TaskDecomposer:
    """Decomposes goals into sub-tasks for multi-agent execution."""
    
    def __init__(self, api_key: str, model_id: str = "claude-sonnet-4-20250514", max_tokens: int = 16384):
        self.model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            max_tokens=max_tokens,
        )
    
    def decompose(self, goal: str, tool_descriptions: str) -> TaskDecomposition:
        """Decompose a goal into sub-tasks."""
        agent = Agent(model=self.model)
        
        prompt = load_prompt(
            "decomposition",
            tool_descriptions=tool_descriptions,
            goal=goal,
        )
        
        result = agent.structured_output(TaskDecomposition, prompt)
        return result
    
    def generate_sub_agent_prompt(self, task: SubTask, tool_descriptions: str) -> str:
        """Generate a focused prompt for a sub-agent."""
        return load_prompt(
            "sub_agent",
            task=task,
            tool_instructions=tool_descriptions,
        )
    
    def save_decomposition(self, decomposition: TaskDecomposition, output_path: str):
        """Save the task decomposition to a file."""
        with open(output_path, "w") as f:
            json.dump(decomposition.model_dump(), f, indent=2)
