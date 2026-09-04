import json
import re
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
COURSE_PATH = ROOT / "content" / "dist" / "course-v1.json"
SEARCH_PATH = ROOT / "content" / "dist" / "search-v1.json"


@pytest.fixture(scope="module")
def course() -> dict:
    return json.loads(COURSE_PATH.read_text())


def test_bundle_has_complete_guide_and_outcome_coverage(course: dict) -> None:
    assert course["metadata"]["chapter_count"] == 40
    assert course["metadata"]["weekend_outcome_count"] == 8
    assert len(course["coverage"]["chapters"]) == 40
    assert len(course["coverage"]["weekend_outcomes"]) == 8


def test_campaign_has_seven_worlds_and_enough_active_missions(course: dict) -> None:
    assert len(course["worlds"]) == 7
    missions = [mission for world in course["worlds"] for mission in world["missions"]]
    assert len(missions) >= 24
    assert all(len(mission["beats"]) == 5 for mission in missions)


def test_question_bank_is_source_backed_and_varied(course: dict) -> None:
    questions = course["questions"]
    citation_ids = set(course["references"])

    assert len(questions) >= 120
    assert {question["type"] for question in questions} >= {
        "classification",
        "mapping",
        "ordering",
        "evidence_judgment",
        "teach_back",
        "unsafe_assumption",
    }
    for question in questions:
        assert question["answer"]
        assert question["explanation"]
        assert question["mastery_skill"]
        assert question["citation_id"] in citation_ids


def test_atlas_covers_primary_inventories(course: dict) -> None:
    atlas = course["atlas"]

    assert len(atlas["fgi_source_pairs"]) == 35
    assert len(atlas["workflow_families"]) == 6
    assert len(atlas["glue_jobs"]) == 14
    assert len(atlas["dynamodb_tables"]) == 14


def test_evidence_labels_match_the_guide_contract(course: dict) -> None:
    assert set(course["evidence_legend"]) == {
        "verified_in_code",
        "configured",
        "documented",
        "environment_specific",
        "legacy_test_template",
        "unconfirmed_gap",
        "hypothesis",
    }


def test_bundle_contains_no_local_paths_accounts_or_secret_shapes(course: dict) -> None:
    serialized = json.dumps(course)

    assert "/Users/" not in serialized
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", serialized)
    assert not re.search(r"AKIA[0-9A-Z]{16}", serialized)
    assert "BEGIN PRIVATE KEY" not in serialized


def test_every_simulation_state_is_reachable_and_terminates(course: dict) -> None:
    assert len(course["simulations"]) >= 2
    for simulation in course["simulations"]:
        states = {state["id"]: state for state in simulation["states"]}
        seen: set[str] = set()
        queue = deque([simulation["start_state"]])
        terminal_seen = False
        while queue:
            state_id = queue.popleft()
            if state_id in seen:
                continue
            seen.add(state_id)
            state = states[state_id]
            terminal_seen = terminal_seen or state["terminal"]
            queue.extend(choice["next_state"] for choice in state["choices"])

        assert seen == set(states)
        assert terminal_seen


def test_search_index_points_to_existing_references(course: dict) -> None:
    search = json.loads(SEARCH_PATH.read_text())

    assert len(search["documents"]) >= 40
    assert all(document["reference_id"] in course["references"] for document in search["documents"])
