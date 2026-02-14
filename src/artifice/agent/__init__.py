from ..config import ArtificeConfig
from .common import AgentResponse as AgentResponse
from .common import AgentBase as AgentBase
from .claude import ClaudeAgent as ClaudeAgent
from .ollama import OllamaAgent as OllamaAgent
from .copilot import CopilotAgent as CopilotAgent
from .simulated import SimulatedAgent as SimulatedAgent, ScriptedAgent as ScriptedAgent, EchoAgent as EchoAgent

def create_agent(config: ArtificeConfig) -> AgentBase | None:
    if not config.provider:
        return None
    if config.provider.lower() == "anthropic":
        return ClaudeAgent(model=config.model, system_prompt=config.system_prompt, thinking_budget=config.thinking_budget)
    elif config.provider.lower() == "copilot":
        return CopilotAgent(model=config.model, system_prompt=config.system_prompt)
    elif config.provider.lower() == "ollama":
        return OllamaAgent(model=config.model, system_prompt=config.system_prompt, thinking_budget=config.thinking_budget)
    elif config.provider.lower() == "simulated":
        agent = SimulatedAgent(response_delay=0.001)
        agent.default_scenarios_and_response()
        return agent
    else:
        raise Exception(f"Unsupported agent provider {config.provider}")

