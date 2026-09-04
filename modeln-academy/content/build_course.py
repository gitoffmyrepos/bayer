#!/usr/bin/env python3
"""Compile the canonical ModelN guide into a sanitized learning bundle."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVIDENCE_LEGEND = {
    "verified_in_code": "Directly observed in implementation or infrastructure source.",
    "configured": "Present in committed configuration; not proof of deployment or execution.",
    "documented": "Stated in supplied business, interface, or architecture material.",
    "environment_specific": "Must be checked in the applicable runtime environment.",
    "legacy_test_template": "Reference, test, sample, or template material.",
    "unconfirmed_gap": "Required evidence is missing, incomplete, or contradictory.",
    "hypothesis": "A reasoned possibility that still requires runtime or data proof.",
}

WORLD_RANGES = (
    (
        "see-the-system",
        "See the System",
        range(1, 6),
        "Understand the platform before memorizing names.",
    ),
    (
        "follow-inbound",
        "Follow Inbound",
        range(6, 17),
        "Trace masters and transactions into Model N.",
    ),
    ("run-the-engine", "Run the Engine", range(17, 28), "Operate the AWS middleware contracts."),
    (
        "shape-the-data",
        "Shape the Data",
        range(28, 31),
        "Follow parsing, Snowflake, and RODB boundaries.",
    ),
    (
        "close-the-loop",
        "Close the Loop",
        range(31, 33),
        "Construct, deliver, and correlate outbound files.",
    ),
    (
        "operate-safely",
        "Operate Safely",
        range(33, 41),
        "Investigate evidence, deploy, and change safely.",
    ),
)

QUESTION_TYPES = (
    "classification",
    "mapping",
    "ordering",
    "evidence_judgment",
    "teach_back",
    "unsafe_assumption",
)


@dataclass(frozen=True)
class Section:
    identifier: str
    title: str
    level: int
    content: str


def slugify(value: str) -> str:
    """Return a stable, URL-safe identifier."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[`*\\]", "", normalized.lower())
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def sanitize_text(value: str) -> str:
    """Remove workstation paths, account identifiers, and secret-shaped material."""
    value = re.sub(r"/Users/[^\s`,;|)\]}]+", "[local-source]", value)
    value = re.sub(r"(?<!\d)\d{12}(?!\d)", "<account-id>", value)
    value = re.sub(r"AKIA[0-9A-Z]{16}", "<redacted-access-key>", value)
    value = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "<redacted-private-key>",
        value,
        flags=re.DOTALL,
    )
    return value.strip()


def sanitize(value: Any) -> Any:
    """Recursively sanitize JSON-compatible data."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    return value


def parse_sections(markdown: str) -> list[Section]:
    """Split Markdown into headed sections while preserving readable text."""
    matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", markdown, re.MULTILINE))
    sections: list[Section] = []
    used: dict[str, int] = {}
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        base_id = slugify(title)
        used[base_id] = used.get(base_id, 0) + 1
        identifier = base_id if used[base_id] == 1 else f"{base_id}-{used[base_id]}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = sanitize_text(markdown[match.end() : end])
        body = re.sub(r"\n{3,}", "\n\n", body)
        sections.append(Section(identifier, title, len(match.group(1)), body[:6000]))
    return sections


def chapter_number(title: str) -> int | None:
    match = re.match(r"Chapter (\d+)\s+—\s+", title)
    return int(match.group(1)) if match else None


def evidence_for(section: Section) -> str:
    combined = f"{section.title} {section.content}".lower()
    if "legacy/test/template" in combined:
        return "legacy_test_template"
    if "hypothesis" in combined:
        return "hypothesis"
    if "unconfirmed" in combined or "gap" in combined:
        return "unconfirmed_gap"
    if "environment-specific" in combined or "environment specific" in combined:
        return "environment_specific"
    if "verified in code" in combined:
        return "verified_in_code"
    if "configured" in combined:
        return "configured"
    return "documented"


def first_reference_containing(sections: Iterable[Section], needle: str) -> str:
    needle = needle.lower()
    for section in sections:
        if needle in section.title.lower():
            return section.identifier
    return "evidence-legend"


def compact_fgi(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    target = record.get("target") or {}
    tables = record.get("tables") or {}
    return sanitize(
        {
            "id": record.get("id"),
            "file_group_id": record.get("fileGroupID"),
            "source_system_name": record.get("sourceSystemName"),
            "business_object": record.get("business_object"),
            "interface_family": record.get("interface_family"),
            "direction": record.get("direction"),
            "source_system": source.get("system"),
            "source_file_type": source.get("file_type"),
            "target_system": target.get("system"),
            "outputs": target.get("outputs") or [],
            "dependencies": record.get("dependencies") or [],
            "job_sequence": record.get("job_sequence") or [],
            "procedures": record.get("procedure_ids_from_process_config") or [],
            "tables": {key: tables.get(key) or [] for key in ("STG", "VARIANT", "TRANS", "OTBD")},
            "rodb": {
                "used": (record.get("rodb") or {}).get("used", False),
                "mode": (record.get("rodb") or {}).get("mode"),
                "lookup_keys": (record.get("rodb") or {}).get("lookup_keys") or [],
            },
            "evidence_limitations": record.get("evidence_limitations"),
        }
    )


def compact_workflow(record: dict[str, Any]) -> dict[str, Any]:
    variants = record.get("environment_variants") or []
    first_variant = variants[0] if variants else {}
    states = first_variant.get("states") or []
    return sanitize(
        {
            "id": record.get("id"),
            "name": record.get("name"),
            "classification": record.get("classification"),
            "status": record.get("status"),
            "evidence_class": record.get("evidence_class"),
            "state_count": len(states),
            "states": [state.get("name") for state in states],
            "evidence_limitations": record.get("evidence_limitations") or [],
        }
    )


def compact_glue(record: dict[str, Any]) -> dict[str, Any]:
    return sanitize(
        {
            "id": record.get("id"),
            "name": record.get("name"),
            "category": record.get("category"),
            "job_type": record.get("job_type"),
            "status": record.get("status"),
            "evidence_class": record.get("evidence_class"),
            "arguments": record.get("argument_names") or [],
            "inputs": record.get("s3_inputs") or [],
            "outputs": record.get("s3_outputs_storage_zones") or [],
            "dynamodb_tables": record.get("dynamodb_tables") or [],
            "snowflake_calls": record.get("snowflake_calls") or [],
            "rodb_calls": record.get("rodb_calls") or [],
            "failure_behavior": record.get("failure_behavior"),
            "evidence_limitations": record.get("evidence_limitations"),
        }
    )


def compact_dynamodb(record: dict[str, Any]) -> dict[str, Any]:
    return sanitize(
        {
            "id": record.get("id"),
            "name": record.get("name"),
            "status": record.get("status"),
            "evidence_class": record.get("evidence_class"),
            "purpose": record.get("purpose"),
            "known_fields": record.get("known_fields") or [],
            "readers": record.get("readers") or [],
            "writers": record.get("writers") or [],
            "fgi_resolution_role": record.get("FGI/source resolution role"),
            "process_resolution_role": record.get("process/job/procedure resolution role"),
            "rerun_audit_role": record.get("rerun/audit role"),
            "evidence_limitations": record.get("evidence_limitations"),
        }
    )


def make_question(
    identifier: str,
    kind: str,
    prompt: str,
    answer: Any,
    explanation: str,
    skill: str,
    citation_id: str,
    options: list[str] | None = None,
) -> dict[str, Any]:
    question = {
        "id": identifier,
        "type": kind,
        "prompt": sanitize_text(prompt),
        "answer": sanitize(answer),
        "explanation": sanitize_text(explanation),
        "mastery_skill": skill,
        "citation_id": citation_id,
        "difficulty": 2,
    }
    if options:
        question["options"] = sanitize(options)
    return question


def build_questions(
    chapters: list[Section],
    sections: list[Section],
    fgi: list[dict[str, Any]],
    workflows: list[dict[str, Any]],
    glue: list[dict[str, Any]],
    dynamodb: list[dict[str, Any]],
    outcomes: list[str],
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    world_by_chapter = {
        number: world_id
        for world_id, _title, numbers, _description in WORLD_RANGES
        for number in numbers
    }
    for chapter in chapters:
        number = chapter_number(chapter.title)
        assert number is not None
        questions.append(
            make_question(
                f"chapter-{number}-world",
                "classification",
                f"Which campaign world develops the capability in {chapter.title}?",
                world_by_chapter[number],
                f"{chapter.title} belongs to the {world_by_chapter[number].replace('-', ' ')} world.",
                "explain_platform_architecture",
                chapter.identifier,
                [world[0] for world in WORLD_RANGES],
            )
        )

    for index, record in enumerate(fgi, start=1):
        label = f"FGI {record['file_group_id']} / {record['source_system_name']}"
        citation = first_reference_containing(sections, f"FGI {record['file_group_id']}")
        questions.extend(
            [
                make_question(
                    f"fgi-{index}-direction",
                    "classification",
                    f"Classify the direction of {label}.",
                    record["direction"],
                    f"The configured lineage classifies {label} as {record['direction']}.",
                    "resolve_fgi_source_identity",
                    citation,
                ),
                make_question(
                    f"fgi-{index}-object",
                    "mapping",
                    f"Map {label} to its business object.",
                    record["business_object"],
                    f"This identity carries {record['business_object']} from {record['source_system']} toward {record['target_system']}.",
                    "trace_inbound_or_outbound",
                    citation,
                ),
            ]
        )

    glue_citation = first_reference_containing(sections, "Glue Jobs: Inventory")
    for index, record in enumerate(glue, start=1):
        questions.append(
            make_question(
                f"glue-{index}-role",
                "mapping",
                f"Map Glue job {record['name']} to its category and job type.",
                f"{record['category']} / {record['job_type']}",
                f"The inventory classifies this job as {record['category']} using {record['job_type']}.",
                "read_runtime_orchestration",
                glue_citation,
            )
        )

    dynamo_citation = first_reference_containing(sections, "DynamoDB Control Plane")
    for index, record in enumerate(dynamodb, start=1):
        questions.append(
            make_question(
                f"dynamodb-{index}-purpose",
                "mapping",
                f"What operator purpose does {record['name']} serve?",
                record["purpose"] or "Purpose is not evidenced in the reviewed source.",
                f"Use the table's explicit contract and evidence limitations: {record['purpose'] or 'purpose not evidenced'}.",
                "read_runtime_orchestration",
                dynamo_citation,
            )
        )

    workflow_citation = first_reference_containing(sections, "Workflow Family Register")
    for index, record in enumerate(workflows, start=1):
        questions.append(
            make_question(
                f"workflow-{index}-classification",
                "classification",
                f"Classify workflow {record['name']} by its operator role.",
                record["classification"],
                f"The workflow register classifies it as {record['classification']} and records {record['state_count']} states in the representative variant.",
                "read_runtime_orchestration",
                workflow_citation,
            )
        )

    outcome_citation = first_reference_containing(sections, "Weekend Outcomes")
    for index, outcome in enumerate(outcomes, start=1):
        questions.append(
            make_question(
                f"outcome-{index}-teach-back",
                "teach_back",
                f"Teach this outcome back in your own words: {outcome}",
                "Self-assess against the cited outcome and include the relevant source, boundary, target, and evidence.",
                "A strong answer explains the relationship and names evidence without claiming more than the source proves.",
                "explain_platform_architecture",
                outcome_citation,
            )
        )

    trace_citation = first_reference_containing(sections, "Reusable Beginner Trace")
    questions.extend(
        [
            make_question(
                "core-order-inbound",
                "ordering",
                "Order the reusable inbound runtime boundaries.",
                ["source", "SFTP", "S3", "Step Functions", "Glue", "Snowflake", "Model N"],
                "Trace the business object across each boundary and collect evidence at every handoff.",
                "trace_inbound_flow",
                trace_citation,
            ),
            make_question(
                "core-order-outbound",
                "ordering",
                "Order the reusable outbound delivery boundaries.",
                ["Model N", "Snowflake", "RODB when configured", "Glue", "S3", "SFTP", "target"],
                "Outbound processing selects data, optionally enriches it, constructs a file, and then delivers it.",
                "trace_outbound_acknowledgment_flow",
                trace_citation,
            ),
            make_question(
                "evidence-green-state",
                "evidence_judgment",
                "A Step Functions execution is green. Does this prove final business delivery?",
                "No. Confirm the generated object, transfer, and target receipt or acknowledgment.",
                "Technical success at one boundary is not proof of the downstream business outcome.",
                "classify_evidence",
                first_reference_containing(sections, "Observability and Failure Evidence"),
            ),
            make_question(
                "evidence-terraform",
                "evidence_judgment",
                "Terraform defines a resource. What does that prove?",
                "It proves source configuration, not current deployment, enablement, execution, or success.",
                "Keep configuration evidence separate from live environment proof.",
                "classify_evidence",
                outcome_citation,
            ),
            make_question(
                "unsafe-rerun-all",
                "unsafe_assumption",
                "Spot the unsafe assumption: a missing output means rerun every upstream job immediately.",
                "The failed boundary and idempotency effects are unproven; build the evidence packet first.",
                "A broad rerun can duplicate delivery or corrupt partial-set state.",
                "choose_safe_rerun_boundaries",
                first_reference_containing(sections, "Retry, Catch, Skip"),
            ),
            make_question(
                "unsafe-current-load",
                "unsafe_assumption",
                "Spot the unsafe assumption: current load means the latest successful live run.",
                "Current load is a data predicate whose exact meaning must be evidenced.",
                "Do not turn a configured or stored data boundary into an unsupported runtime claim.",
                "follow_data_lineage",
                first_reference_containing(sections, "Current-Load Selection"),
            ),
        ]
    )
    return questions


def build_worlds(chapters: list[Section], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions_by_chapter = {question["citation_id"]: question["id"] for question in questions}
    chapter_lookup = {chapter_number(chapter.title): chapter for chapter in chapters}
    worlds: list[dict[str, Any]] = []
    for world_id, title, numbers, description in WORLD_RANGES:
        missions = []
        for number in numbers:
            chapter = chapter_lookup[number]
            question_id = questions_by_chapter.get(chapter.identifier, questions[0]["id"])
            missions.append(
                {
                    "id": f"mission-{number:02d}",
                    "title": re.sub(r"^Chapter \d+\s+—\s+", "", chapter.title),
                    "chapter": number,
                    "summary": chapter.content.split("\n\n", 1)[0][:420],
                    "citation_id": chapter.identifier,
                    "beats": [
                        {"type": "brief", "title": "Why this matters"},
                        {"type": "explore", "title": "See the boundaries"},
                        {"type": "decide", "title": "Choose the next move"},
                        {
                            "type": "recall",
                            "title": "Retrieve from memory",
                            "question_ids": [question_id],
                        },
                        {"type": "debrief", "title": "Explain and connect"},
                    ],
                }
            )
        worlds.append(
            {"id": world_id, "title": title, "description": description, "missions": missions}
        )

    capstone_citation = first_reference_containing(chapters, "Symptom-Based Decision Trees")
    worlds.append(
        {
            "id": "incident-capstone",
            "title": "Incident Capstone",
            "description": "Apply the complete trace method under uncertainty.",
            "missions": [
                {
                    "id": "mission-capstone-0009343",
                    "title": "Package 0009343",
                    "chapter": 37,
                    "summary": "Separate confirmed facts from hypotheses and find the failed boundary.",
                    "citation_id": capstone_citation,
                    "beats": [
                        {"type": beat, "title": beat.replace("_", " ").title()}
                        for beat in ("brief", "explore", "decide", "recall", "debrief")
                    ],
                },
                {
                    "id": "mission-capstone-unfamiliar-fgi",
                    "title": "The Unfamiliar FGI",
                    "chapter": 37,
                    "summary": "Use the seven-step trace method without relying on memorized names.",
                    "citation_id": capstone_citation,
                    "beats": [
                        {"type": beat, "title": beat.replace("_", " ").title()}
                        for beat in ("brief", "explore", "decide", "recall", "debrief")
                    ],
                },
            ],
        }
    )
    return worlds


def build_simulations(sections: list[Section]) -> list[dict[str, Any]]:
    evidence_ref = first_reference_containing(sections, "Correlation IDs")
    rerun_ref = first_reference_containing(sections, "Retry, Catch, Skip")
    incident_ref = first_reference_containing(sections, "FGI 301 Package")
    return [
        {
            "id": "sim-missing-inbound",
            "title": "The Missing Inbound File",
            "start_state": "symptom",
            "states": [
                {
                    "id": "symptom",
                    "terminal": False,
                    "prompt": "The expected Model N input is missing. What comes first?",
                    "choices": [
                        {
                            "id": "identify",
                            "label": "Confirm FGI, source identity, and expected contract",
                            "next_state": "identity",
                            "score": 20,
                            "citation_id": evidence_ref,
                        },
                        {
                            "id": "rerun",
                            "label": "Rerun every Glue job",
                            "next_state": "unsafe",
                            "score": -20,
                            "citation_id": rerun_ref,
                        },
                    ],
                },
                {
                    "id": "identity",
                    "terminal": False,
                    "prompt": "Identity is confirmed. Which evidence narrows the failed boundary?",
                    "choices": [
                        {
                            "id": "boundaries",
                            "label": "Check source file, S3 object, workflow, job, output, and receipt",
                            "next_state": "safe",
                            "score": 30,
                            "citation_id": evidence_ref,
                        },
                    ],
                },
                {
                    "id": "safe",
                    "terminal": True,
                    "prompt": "You produced a scoped evidence packet before choosing a rerun.",
                    "choices": [],
                },
                {
                    "id": "unsafe",
                    "terminal": True,
                    "prompt": "The broad rerun risked duplicate or partial processing.",
                    "choices": [],
                },
            ],
        },
        {
            "id": "sim-package-0009343",
            "title": "FGI 301 Package 0009343",
            "start_state": "missing-fields",
            "states": [
                {
                    "id": "missing-fields",
                    "terminal": False,
                    "prompt": "Two RODB-derived fields are absent. What is known?",
                    "choices": [
                        {
                            "id": "facts",
                            "label": "Keep missing enrichment and likely joins as separate fact and hypothesis",
                            "next_state": "inspect",
                            "score": 25,
                            "citation_id": incident_ref,
                        },
                        {
                            "id": "blame",
                            "label": "Declare the RODB service failed",
                            "next_state": "unsafe",
                            "score": -15,
                            "citation_id": incident_ref,
                        },
                    ],
                },
                {
                    "id": "inspect",
                    "terminal": False,
                    "prompt": "Which next check protects the evidence boundary?",
                    "choices": [
                        {
                            "id": "pair",
                            "label": "Trace claim/product lookup inputs and join cardinality",
                            "next_state": "safe",
                            "score": 35,
                            "citation_id": incident_ref,
                        },
                    ],
                },
                {
                    "id": "safe",
                    "terminal": True,
                    "prompt": "You narrowed the null boundary without overstating the root cause.",
                    "choices": [],
                },
                {
                    "id": "unsafe",
                    "terminal": True,
                    "prompt": "The conclusion exceeded the available evidence.",
                    "choices": [],
                },
            ],
        },
    ]


def extract_outcomes(markdown: str) -> list[str]:
    match = re.search(
        r"^## Weekend Outcomes\s*(.*?)^## Reading Map", markdown, re.MULTILINE | re.DOTALL
    )
    if not match:
        raise ValueError("Weekend Outcomes section was not found")
    return [
        sanitize_text(item)
        for item in re.findall(
            r"^\d+\.\s+(.+?)(?=\n\d+\.|\Z)", match.group(1), re.MULTILINE | re.DOTALL
        )
    ]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build(source_root: Path, output_dir: Path) -> tuple[Path, Path]:
    guide_path = source_root / "ModelN-Complete-End-to-End-New-Hire-Study-Guide.md"
    inventory_root = source_root / "inventories"
    markdown = guide_path.read_text(encoding="utf-8")
    sections = parse_sections(markdown)
    chapters = [section for section in sections if chapter_number(section.title) is not None]
    outcomes = extract_outcomes(markdown)
    if [chapter_number(section.title) for section in chapters] != list(range(1, 41)):
        raise ValueError("Guide must contain exactly Chapters 1 through 40")
    if len(outcomes) != 8:
        raise ValueError("Guide must contain exactly eight weekend outcomes")

    fgi = [compact_fgi(item) for item in read_json(inventory_root / "fgi-lineage.json")]
    workflows = [
        compact_workflow(item) for item in read_json(inventory_root / "step-functions.json")
    ]
    glue = [compact_glue(item) for item in read_json(inventory_root / "glue-jobs.json")]
    dynamodb = [compact_dynamodb(item) for item in read_json(inventory_root / "dynamodb.json")]

    references = {
        section.identifier: {
            "id": section.identifier,
            "title": sanitize_text(section.title),
            "content": section.content,
            "evidence_class": evidence_for(section),
        }
        for section in sections
    }
    questions = build_questions(chapters, sections, fgi, workflows, glue, dynamodb, outcomes)
    course = {
        "metadata": {
            "id": "modeln-complete-new-hire",
            "version": "1.0.0",
            "title": "ModelN Systems Adventure",
            "chapter_count": len(chapters),
            "weekend_outcome_count": len(outcomes),
            "source_kind": "sanitized_evidence_backed_training_bundle",
        },
        "evidence_legend": EVIDENCE_LEGEND,
        "coverage": {
            "chapters": {str(chapter_number(item.title)): item.identifier for item in chapters},
            "weekend_outcomes": outcomes,
        },
        "worlds": build_worlds(chapters, questions),
        "questions": questions,
        "simulations": build_simulations(sections),
        "atlas": {
            "fgi_source_pairs": fgi,
            "workflow_families": workflows,
            "glue_jobs": glue,
            "dynamodb_tables": dynamodb,
        },
        "references": references,
    }

    search_documents = [
        {
            "id": f"reference:{identifier}",
            "reference_id": identifier,
            "title": reference["title"],
            "text": f"{reference['title']}\n{reference['content']}",
            "kind": "guide_section",
        }
        for identifier, reference in references.items()
    ]
    for category, records in course["atlas"].items():
        for record in records:
            search_documents.append(
                {
                    "id": f"atlas:{category}:{slugify(str(record.get('id') or record.get('name')))}",
                    "reference_id": first_reference_containing(
                        sections,
                        str(record.get("file_group_id") or record.get("name") or "Evidence Legend"),
                    ),
                    "title": str(
                        record.get("name") or record.get("business_object") or record.get("id")
                    ),
                    "text": json.dumps(record, ensure_ascii=False),
                    "kind": category,
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    course_path = output_dir / "course-v1.json"
    search_path = output_dir / "search-v1.json"
    course_path.write_text(
        json.dumps(course, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    search_path.write_text(
        json.dumps(
            {"version": "1.0.0", "documents": search_documents}, indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    return course_path, search_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "dist")
    args = parser.parse_args()
    course_path, search_path = build(args.source_root, args.output_dir)
    print(f"Built {course_path} and {search_path}")


if __name__ == "__main__":
    main()
