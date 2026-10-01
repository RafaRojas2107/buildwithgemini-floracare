# Copyright 2026 Google LLC
import pytest
from app.agent import root_agent, memory_bank_service_builder, generate_memories_callback
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService


def test_agent_memory_and_code_executor_config():
    # Verify PreloadMemoryTool is in agent tools
    assert any(isinstance(t, PreloadMemoryTool) for t in root_agent.tools)

    # Verify after_agent_callback is configured for long-term memory extraction
    assert root_agent.after_agent_callback == generate_memories_callback

    # Verify AgentEngineSandboxCodeExecutor is configured
    assert isinstance(root_agent.code_executor, AgentEngineSandboxCodeExecutor)
    assert "8263696847655141376" in root_agent.code_executor.sandbox_resource_name


def test_memory_bank_service_builder():
    svc = memory_bank_service_builder()
    assert isinstance(svc, VertexAiMemoryBankService)
    assert svc._agent_engine_id == "8882989075418578944"
    assert svc._project == "qwiklabs-gcp-03-c2254edad736"
    assert svc._location == "us-central1"


def test_allergy_memory_configuration():
    # Verify instruction enforces remembering allergies
    instruction = str(root_agent.instruction).lower()
    assert "allergies" in instruction
    assert "health" in instruction or "sensitive" in instruction


def test_a2ui_configuration():
    from app.a2ui_utils import a2ui_callback
    assert root_agent.after_model_callback == a2ui_callback
    instruction = str(root_agent.instruction)
    assert "A2UI" in instruction or "a2ui" in instruction
