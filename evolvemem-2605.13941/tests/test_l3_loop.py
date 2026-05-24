"""Tests for L3 Retrieval Loop."""
import json
import pytest
from loops.l3_retrieval.loop import L3Loop
from loops.action_space import RetrievalConfig
from dev_set import DevSetConfig


def test_l3_quick_mode_no_state(stub_router, mock_llm, failure_logger, tmp_data, sample_dev_set):
    loop = L3Loop(
        router=stub_router,
        llm=mock_llm,
        failure_logger=failure_logger,
        state_path=tmp_data / "loop_states" / "l3_state.json",
        dev_set_path=sample_dev_set,
        evolved_dir=tmp_data / "evolved",
        quick_mode=True,
    )
    result = loop.run()
    assert result.loop_id == "L3"
    assert result.rounds_run == 1
    # quick mode: no state file written
    assert not (tmp_data / "loop_states" / "l3_state.json").exists()


def test_l3_full_run(stub_router, mock_llm, failure_logger, tmp_data, sample_dev_set):
    loop = L3Loop(
        router=stub_router,
        llm=mock_llm,
        failure_logger=failure_logger,
        state_path=tmp_data / "loop_states" / "l3_state.json",
        dev_set_path=sample_dev_set,
        evolved_dir=tmp_data / "evolved",
        quick_mode=False,
    )
    # Use 2 rounds for speed
    loop.max_rounds = 2
    result = loop.run()
    assert result.rounds_run == 2
    assert (tmp_data / "evolved" / "retrieval_config.json").exists()


def test_l3_prompt_injection(stub_router, mock_llm, failure_logger, tmp_data, sample_dev_set):
    loop = L3Loop(
        router=stub_router,
        llm=mock_llm,
        failure_logger=failure_logger,
        state_path=tmp_data / "l3_inj.json",
        dev_set_path=sample_dev_set,
        evolved_dir=tmp_data / "evolved",
        quick_mode=True,
    )
    custom_prompt = "Custom prompt text {config_json} {f1} {history} {stagnating}"
    loop.set_diagnosis_prompt(custom_prompt)
    # Should not raise
    result = loop.run()
    assert result is not None


def test_l3_open_schema_patch(stub_router, failure_logger, tmp_data, sample_dev_set):
    from loops.llm import MockProvider
    mock = MockProvider('{"entity_swap": true, "entity_swap_domain": "it_support"}')
    loop = L3Loop(
        router=stub_router,
        llm=mock,
        failure_logger=failure_logger,
        state_path=tmp_data / "l3_schema.json",
        dev_set_path=sample_dev_set,
        evolved_dir=tmp_data / "evolved",
        quick_mode=True,
    )
    result = loop.run()
    # Open-schema dims should be discoverable
    dims = result.discovered_dimensions
    assert "entity_swap" in dims or "entity_swap_domain" in dims
