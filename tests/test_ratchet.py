"""Tests for the ratchet.

These cover the claims the submission actually makes — that authority is earned, that
it is revoked, that an effect cannot fire twice, and that verification refuses to
pass an operation which promised nothing. If any of these fail, the pitch is false.

They run with no credentials and no ADK: `authority`, `effects` and `world` import
neither.
"""

from __future__ import annotations

import pytest

from ratchet.authority import Authority, AuthorityLedger, PROMOTION_THRESHOLD
from ratchet.effects import Actuator, Effect, EffectLog, fingerprint
from ratchet.world import DictReader, FaultProfile, VirtualWorld, verify


# --------------------------------------------------------------------------- #
# the ratchet
# --------------------------------------------------------------------------- #

@pytest.fixture
def ledger() -> AuthorityLedger:
    return AuthorityLedger()


SHAPE = "gcs.delete_bucket:abc123abc123"


def test_new_operations_start_in_shadow(ledger: AuthorityLedger) -> None:
    decision = ledger.decide("gcs.delete_bucket", SHAPE)
    assert decision.authority is Authority.SHADOW
    assert decision.commits is False
    assert decision.verify is True


def test_authority_is_earned_not_granted(ledger: AuthorityLedger) -> None:
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW] - 1):
        ledger.observe("op", SHAPE, passed=True)
    assert ledger.record("op").authority is Authority.SHADOW

    ledger.observe("op", SHAPE, passed=True)
    assert ledger.record("op").authority is Authority.PROVISIONAL
    assert ledger.decide("op", SHAPE).commits is True


def test_one_failure_demotes_and_resets_the_streak(ledger: AuthorityLedger) -> None:
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
        ledger.observe("op", SHAPE, passed=True)
    assert ledger.record("op").authority is Authority.PROVISIONAL

    record = ledger.observe("op", SHAPE, passed=False, detail="post-condition drifted")
    assert record.authority is Authority.SHADOW
    assert record.streak == 0
    assert record.demotions == 1
    assert "drifted" in record.last_reason


def test_the_ratchet_turns_both_ways_repeatedly(ledger: AuthorityLedger) -> None:
    for cycle in range(3):
        for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
            ledger.observe("op", SHAPE, passed=True)
        assert ledger.record("op").authority is Authority.PROVISIONAL, cycle
        ledger.observe("op", SHAPE, passed=False)
        assert ledger.record("op").authority is Authority.SHADOW, cycle


def test_provisional_verifies_every_run(ledger: AuthorityLedger) -> None:
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
        ledger.observe("op", SHAPE, passed=True)
    assert ledger.decide("op", SHAPE).verify is True


def test_shadow_never_commits_however_long_it_waits(ledger: AuthorityLedger) -> None:
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW] - 1):
        ledger.observe("op", SHAPE, passed=True)
        assert ledger.decide("op", SHAPE).commits is False


def test_earned_authority_does_not_transfer_to_an_unrehearsed_shape(ledger: AuthorityLedger) -> None:
    """The heart of it: trust is per shape of work, not per tool."""
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
        ledger.observe("op", SHAPE, passed=True)
    assert ledger.decide("op", SHAPE).commits is True

    novel = ledger.decide("op", "op:deadbeefdead")
    assert novel.commits is False
    assert novel.in_envelope is False
    assert "unrehearsed" in novel.reason


# --------------------------------------------------------------------------- #
# effects
# --------------------------------------------------------------------------- #

def test_environment_changes_the_operation_identity() -> None:
    scratch = fingerprint("bucket.delete", {"project": "scratch", "name": "a"})
    prod = fingerprint("bucket.delete", {"project": "prod", "name": "a"})
    assert scratch != prod


def test_argument_values_do_not_change_the_operation_identity() -> None:
    a = fingerprint("bucket.delete", {"project": "scratch", "name": "alpha"})
    b = fingerprint("bucket.delete", {"project": "scratch", "name": "beta"})
    assert a == b


def test_an_effect_fires_exactly_once_across_a_resume() -> None:
    """Checkpointing is not durable execution. This is the difference."""
    fired: list[dict] = []

    def delete(**params):
        fired.append(params)
        return {"exists": False}

    log = EffectLog()
    actuator = Actuator(log, {"bucket.delete": delete})
    effect = Effect("bucket.delete", {"name": "alpha"}, expect={"exists": False}, run_id="r1")

    first = actuator.commit(effect)
    second = actuator.commit(effect)  # the resumed node re-runs

    assert len(fired) == 1
    assert first.committed and not first.replayed
    assert second.replayed is True
    assert second.observed == first.observed


def test_a_different_run_is_a_different_key() -> None:
    effect_a = Effect("bucket.delete", {"name": "alpha"}, run_id="r1")
    effect_b = Effect("bucket.delete", {"name": "alpha"}, run_id="r2")
    assert effect_a.key != effect_b.key


def test_a_failing_tool_is_recorded_not_raised() -> None:
    def boom(**_):
        raise TimeoutError("upstream gone")

    actuator = Actuator(EffectLog(), {"x": boom})
    result = actuator.commit(Effect("x", {}, run_id="r"))
    assert result.committed is False
    assert "TimeoutError" in result.error


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #

def test_an_effect_that_promises_nothing_cannot_pass() -> None:
    verdict = verify(Effect("x", {}), before={"a": 1}, after={"a": 2})
    assert verdict.passed is False
    assert "no expected post-conditions" in verdict.reason


def test_a_no_op_does_not_count_as_success() -> None:
    effect = Effect("x", {}, expect={"state": "idle"})
    verdict = verify(effect, before={"state": "idle"}, after={"state": "idle"})
    assert verdict.passed is False
    assert "no-op" in verdict.reason


def test_post_conditions_are_checked_against_observed_state() -> None:
    effect = Effect("x", {}, expect={"state": "stopped", "count": 0})
    verdict = verify(effect, before={"state": "running", "count": 3}, after={"state": "stopped", "count": 3})
    assert verdict.passed is False
    assert verdict.mismatches == ["count: expected 0, observed 3"]


def test_a_real_change_that_matches_passes() -> None:
    effect = Effect("x", {}, expect={"state": "stopped"})
    verdict = verify(effect, before={"state": "running"}, after={"state": "stopped"})
    assert verdict.passed is True


# --------------------------------------------------------------------------- #
# rehearsal
# --------------------------------------------------------------------------- #

def _world(faults: FaultProfile | None = None) -> VirtualWorld:
    return VirtualWorld(
        reader=DictReader({"vm.stop:web-1": {"state": "running"}}),
        simulators={"vm.stop": lambda before, params: {**before, "state": "stopped"}},
        faults=faults,
    )


def test_rehearsal_predicts_the_delta_without_committing() -> None:
    world = _world()
    effect = Effect("vm.stop", {"target": "web-1"}, expect={"state": "stopped"}, run_id="r1")
    delta, error = world.rehearse(effect)

    assert error == ""
    assert delta.changed == {"state": ("running", "stopped")}
    assert verify(effect, delta.before, delta.after).passed is True


def test_injected_faults_surface_as_rehearsal_failures() -> None:
    world = _world(FaultProfile(error_rate=1.0, seed=7))
    delta, error = world.rehearse(Effect("vm.stop", {"target": "web-1"}, expect={"state": "stopped"}, run_id="r1"))
    assert "injected fault" in error
    assert delta.changed == {}


def test_an_operation_with_no_simulator_cannot_rehearse() -> None:
    _, error = _world().rehearse(Effect("vm.incinerate", {"target": "web-1"}, run_id="r1"))
    assert "no simulator" in error


def test_a_later_run_rehearses_against_the_real_world_again() -> None:
    """Regression: the virtual world used to accumulate across runs, so the second
    rehearsal of the same operation saw its own leftovers, scored as a no-op, and no
    operation could ever leave shadow."""
    world = _world()
    first = Effect("vm.stop", {"target": "web-1"}, expect={"state": "stopped"}, run_id="r1")
    second = Effect("vm.stop", {"target": "web-1"}, expect={"state": "stopped"}, run_id="r2")

    d1, _ = world.rehearse(first)
    d2, _ = world.rehearse(second)

    assert d1.changed == d2.changed == {"state": ("running", "stopped")}
    assert verify(second, d2.before, d2.after).passed is True


def test_a_multi_step_plan_sees_its_own_earlier_rehearsals() -> None:
    world = VirtualWorld(
        reader=DictReader({"counter.bump:c": {"n": 0}}),
        simulators={"counter.bump": lambda before, params: {"n": before.get("n", 0) + 1}},
    )
    step1 = Effect("counter.bump", {"target": "c"}, expect={"n": 1}, run_id="same")
    step2 = Effect("counter.bump", {"target": "c"}, expect={"n": 2}, run_id="same")

    world.rehearse(step1)
    delta, _ = world.rehearse(step2)
    assert delta.changed == {"n": (1, 2)}


def test_the_same_run_id_reused_later_still_rehearses_cleanly() -> None:
    """Regression, second occurrence: a caller that reuses run ids (a long-lived
    server handing out r1..r8 per request) must not inherit the previous run's
    rehearsal slice. `discard` is called by the graph's report node."""
    world = _world()
    effect = Effect("vm.stop", {"target": "web-1"}, expect={"state": "stopped"}, run_id="r1")

    first, _ = world.rehearse(effect)
    world.discard("r1")
    second, _ = world.rehearse(effect)

    assert first.changed == second.changed == {"state": ("running", "stopped")}


def test_an_llm_agent_slots_into_the_graph_and_validates() -> None:
    """The structural claim: the proposer can be a real model without the machinery
    around it changing. Construction runs ADK's full graph validation — edges,
    cross-edge schemas, terminals, the cycle rule — so this fails loudly if the
    mixed deterministic/LLM topology is wrong. Only inference needs a key."""
    from google.adk.agents import LlmAgent
    from google.adk.apps import App, ResumabilityConfig

    from ratchet.domains import finops
    from ratchet.graph import Deps, build_workflow
    from ratchet.world import DictReader

    reader = DictReader(finops.sample_estate())
    deps = Deps(
        AuthorityLedger(),
        Actuator(EffectLog(), {}),
        VirtualWorld(reader, finops.simulators()),
        reader,
    )
    proposer = LlmAgent(
        name="proposer",
        model="gemini-3.6-flash",
        description="Proposes reclamation operations.",
        instruction="Propose operations to reclaim idle spend.",
    )

    workflow = build_workflow(deps, proposer)
    app = App(name="t", root_agent=workflow, resumability_config=ResumabilityConfig(is_resumable=True))

    assert app.root_agent is workflow
    assert len(workflow.edges) == 7


def _has_vertex() -> bool:
    import os
    from pathlib import Path

    return bool(os.environ.get("GOOGLE_API_KEY")) or (
        Path.home() / ".config/gcloud/application_default_credentials.json"
    ).exists()


@pytest.mark.skipif(not _has_vertex(), reason="needs Gemini credentials (ADC or API key)")
def test_a_live_model_proposal_is_still_subject_to_the_ladder() -> None:
    """The claim that cannot be made without a credential: a real model's proposal
    enters the same machinery as a hardcoded one, and being correct does not grant
    it authority. Verified against Gemini 3.6 Flash on Vertex, 13 Aug 2026."""
    import asyncio
    import os

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        pytest.skip("GOOGLE_CLOUD_PROJECT not set")

    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from ratchet.domains import finops
    from ratchet.graph import Deps, Proposal, build_app
    from ratchet.world import DictReader

    estate = finops.sample_estate()
    reader = DictReader(estate)
    deps = Deps(
        AuthorityLedger(), Actuator(EffectLog(), {}), VirtualWorld(reader, finops.simulators()), reader
    )
    catalogue = "\n".join(f"- {n}: {s.summary}" for n, s in finops.SPECS.items())
    inventory = "\n".join(
        f"- {k.split(':')[1]} ({k.split(':')[0]}): ${v['monthly_cost_usd']}/mo" for k, v in estate.items()
    )
    proposer = LlmAgent(
        name="proposer",
        model="gemini-3.6-flash",
        output_schema=Proposal,
        description="Picks the single highest-value reclamation.",
        instruction=f"You are a FinOps analyst.\n\nOperations:\n{catalogue}\n\nEstate:\n{inventory}\n\n"
        "Pick the ONE operation with the largest monthly saving.",
    )

    async def run() -> list:
        app = build_app(deps, proposer, name="live", to_effect=finops.to_effect)
        runner = Runner(app=app, session_service=InMemorySessionService(), auto_create_session=True)
        seen = []
        async for event in runner.run_async(
            user_id="u",
            session_id="live-test",
            new_message=types.Content(role="user", parts=[types.Part(text="What first?")]),
            state_delta={"goal": "reclaim idle spend", "run_id": "live-test"},
        ):
            if getattr(event, "output", None) is not None:
                seen.append(event.output)
        return seen

    outputs = asyncio.run(run())
    intake = next(o for o in outputs if isinstance(o, dict) and "accepted" in o)
    gate = next(o for o in outputs if isinstance(o, dict) and o.get("route") in ("shadow", "commit", "consult"))

    assert intake["accepted"] is True
    assert intake["op_class"] in finops.SPECS
    # Correctness is not authority: a brand-new class rehearses regardless.
    assert gate["route"] == "shadow"
