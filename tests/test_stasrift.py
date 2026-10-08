import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "stasrift.py"

def run(*args, input_text=None):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=input_text,
    )

def test_diff_event_to_processing():
    p = run("diff", "--old", "fixtures/old_event.yaml",
            "--new", "fixtures/new_processing.yaml", "--json")
    assert p.returncode == 1
    assert json.loads(p.stdout)["verdict"] == "INCOMPATIBLE"

def test_scan_suggest_temporal_unit_absent_and_conflict(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skipped.json"
    assert run("scan", "--repo", "demo_repo", "--contract", "demo_repo/orders.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0
    data = json.loads(sg.read_text())
    by_key = {(x["field"], x["attribute"]): x for x in data["suggestions"]}
    assert by_key[("occurred_at","time_axis")]["kind"] == "suggestion"
    assert by_key[("processed_at","time_axis")]["kind"] == "suggestion"
    assert by_key[("ship_at","time_axis")]["kind"] == "conflict"
    assert by_key[("amount_usd","unit")]["kind"] == "suggestion"
    assert by_key[("discount_pct","absent")]["kind"] == "question"

def test_suggest_deterministic(tmp_path):
    ev = tmp_path / "evidence.json"
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    skip = tmp_path / "skip.json"
    assert run("scan", "--repo", "demo_repo", "--contract", "demo_repo/orders.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(a),
               "--skip-file", str(skip)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(b),
               "--skip-file", str(skip)).returncode == 0
    assert a.read_bytes() == b.read_bytes()

def test_skip_persistence_suppresses_same_evidence(tmp_path):
    ev = tmp_path / "evidence.json"
    sg1 = tmp_path / "s1.json"
    sg2 = tmp_path / "s2.json"
    skip = tmp_path / "skip.json"
    assert run("scan", "--repo", "demo_repo", "--contract", "demo_repo/orders.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(sg1),
               "--skip-file", str(skip)).returncode == 0
    data = json.loads(sg1.read_text())
    first = data["suggestions"][0]
    skip.write_text(json.dumps({
        f"{first['field']}::{first['attribute']}": {"evidence_hash": first["evidence_hash"]}
    }))
    assert run("suggest", "--evidence", str(ev), "--out", str(sg2),
               "--skip-file", str(skip)).returncode == 0
    data2 = json.loads(sg2.read_text())
    assert not any(x["field"] == first["field"] and x["attribute"] == first["attribute"]
                   for x in data2["suggestions"])


def test_version():
    p = run("--version")
    assert p.returncode == 0
    assert p.stdout.strip() == "stasrift 1.0.1"

def test_review_dry_run_no_color(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"

    assert run("scan", "--repo", "demo_repo",
               "--contract", "demo_repo/orders.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev),
               "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0

    # Inputs: amount choose USD, discount unknown, occurred choose event_time,
    # processed confirm, ship skip.
    user_input = "1\n3\n1\nevent_time\n1\n2\n"
    p = run("review",
            "--suggestions", str(sg),
            "--contract", "demo_repo/orders.yaml",
            "--skip-file", str(skip),
            "--dry-run",
            "--no-color",
            input_text=user_input)
    assert p.returncode == 0
    assert "WRITE PREVIEW" in p.stdout
    assert "Dry run: nothing written." in p.stdout


def test_structured_sql_alias_detection(tmp_path):
    contract = tmp_path / "contract.yaml"
    sql = tmp_path / "model.sql"
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"

    contract.write_text("""fields:
  - name: captured_at
  - name: amount
""")
    sql.write_text("""select
  current_timestamp as captured_at,
  raw_amount_cents / 100.0 as amount
from raw_orders
""")
    assert run("scan", "--repo", str(tmp_path), "--contract", str(contract),
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0
    data = json.loads(sg.read_text())
    by_key = {(x["field"], x["attribute"]): x for x in data["suggestions"]}
    assert by_key[("captured_at","time_axis")]["proposed"] == ["processing_time"]
    assert by_key[("amount","unit")]["kind"] == "question"
    assert by_key[("amount","unit")]["proposed"] is None

def test_incident_fixture_shape_passes_semantics_fail():
    baseline = subprocess.run(
        [sys.executable, str(ROOT / "baseline_shape_check.py"),
         "incident_fixture/schema_v1.yaml",
         "incident_fixture/schema_v2.yaml"],
        cwd=ROOT, capture_output=True, text=True
    )
    assert baseline.returncode == 0
    assert "PASS" in baseline.stdout

    semantic = run(
        "diff",
        "--old", "incident_fixture/schema_v1.yaml",
        "--new", "incident_fixture/schema_v2.yaml",
        "--json"
    )
    assert semantic.returncode == 1
    assert json.loads(semantic.stdout)["verdict"] == "INCOMPATIBLE"


def test_validate_contract():
    p = run("validate", "--contract", "incident_fixture/schema_v1.yaml", "--json")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert data["valid"] is True

def test_doctor_finds_contracts():
    p = run("doctor", "--repo", "incident_fixture", "--json")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert data["ready"] is True
    assert len(data["contracts"]) >= 2

def test_demo_returns_semantic_failure():
    p = run("demo", "--root", ".")
    assert p.returncode == 1
    assert "BASELINE SHAPE CHECK" in p.stdout
    assert "PASS" in p.stdout
    assert "INCOMPATIBLE" in p.stdout


def test_cte_lineage_propagation(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"
    assert run("scan", "--repo", "pipeline_fixture",
               "--contract", "pipeline_fixture/contract.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0
    data = json.loads(sg.read_text())
    by_key = {(x["field"], x["attribute"]): x for x in data["suggestions"]}
    assert by_key[("occurred_at","time_axis")]["proposed"] == ["event_time"]
    assert by_key[("processed_at","time_axis")]["proposed"] == ["processing_time"]
    assert by_key[("amount","unit")]["kind"] == "question"
    assert by_key[("amount","unit")]["proposed"] is None
    assert by_key[("discount_pct","absent")]["kind"] == "question"


def test_dbt_cross_file_ref_propagation(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"

    assert run("scan", "--repo", "dbt_fixture",
               "--contract", "dbt_fixture/contract.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev),
               "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0

    data = json.loads(sg.read_text())
    by_key = {(x["field"], x["attribute"]): x for x in data["suggestions"]}

    assert by_key[("occurred_at","time_axis")]["proposed"] == ["event_time"]
    assert by_key[("processed_at","time_axis")]["proposed"] == ["processing_time"]
    assert by_key[("amount","unit")]["kind"] == "question"
    assert by_key[("amount","unit")]["proposed"] is None

def test_dbt_refs_are_recorded_in_evidence(tmp_path):
    ev = tmp_path / "evidence.json"
    assert run("scan", "--repo", "dbt_fixture",
               "--contract", "dbt_fixture/contract.yaml",
               "--out", str(ev)).returncode == 0
    data = json.loads(ev.read_text())
    field = next(x for x in data["fields"] if x["name"] == "occurred_at")
    assert any("dbt model 'fct_orders'" in e["description"] or
               "dbt model 'mart_orders'" in e["description"]
               for e in field["evidence"])


def test_multi_ref_join_refuses_inherited_inference(tmp_path):
    ev = tmp_path / "evidence.json"
    assert run("scan", "--repo", "ambiguity_fixture",
               "--contract", "ambiguity_fixture/contract.yaml",
               "--out", str(ev)).returncode == 0
    data = json.loads(ev.read_text())
    occurred = next(x for x in data["fields"] if x["name"] == "occurred_at")
    assert any(
        e["type"] == "uncertainty" and "multiple upstream refs" in e["description"]
        for e in occurred["evidence"]
    )

def test_union_refuses_inherited_inference(tmp_path):
    ev = tmp_path / "evidence.json"
    assert run("scan", "--repo", "ambiguity_fixture",
               "--contract", "ambiguity_fixture/contract.yaml",
               "--out", str(ev)).returncode == 0
    data = json.loads(ev.read_text())
    amount = next(x for x in data["fields"] if x["name"] == "amount")
    assert any(
        e["type"] == "uncertainty" and "top-level UNION" in e["description"]
        for e in amount["evidence"]
    )

def test_dbt_simple_chain_still_works(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"
    assert run("scan", "--repo", "dbt_fixture",
               "--contract", "dbt_fixture/contract.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev),
               "--out", str(sg), "--skip-file", str(skip)).returncode == 0
    data = json.loads(sg.read_text())
    by_key = {(x["field"], x["attribute"]): x for x in data["suggestions"]}
    assert by_key[("occurred_at","time_axis")]["proposed"] == ["event_time"]
    assert by_key[("processed_at","time_axis")]["proposed"] == ["processing_time"]


def test_contract_schema_command_yaml():
    p = run("contract-schema")
    assert p.returncode == 0
    assert "stasrift_format: stasrift-contract-v1" in p.stdout

def test_contract_schema_command_json():
    p = run("contract-schema", "--json")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert data["stasrift_format"] == "stasrift-contract-v1"

def test_v1_contract_validates():
    p = run("validate", "--contract", "examples/orders.stasrift.yaml", "--json")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert data["valid"] is True

def test_unknown_contract_format_rejected(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("""stasrift_format: stasrift-contract-v2
fields:
  - name: occurred_at
""")
    p = run("validate", "--contract", str(f))
    assert p.returncode == 2
    assert "unsupported stasrift_format" in p.stderr


def test_cents_conversion_does_not_assume_usd(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"
    p = run("scan", "--repo", "public_pilot_jaffle_shop",
            "--contract", "public_pilot_jaffle_shop/contract.yaml",
            "--out", str(ev))
    assert p.returncode == 0

    p = run("suggest", "--evidence", str(ev), "--out", str(sg),
            "--skip-file", str(skip))
    assert p.returncode == 0

    data = json.loads(sg.read_text())
    unit_items = [x for x in data["suggestions"] if x["field"] == "amount" and x["attribute"] == "unit"]
    assert len(unit_items) == 1
    item = unit_items[0]
    assert item["kind"] == "question"
    assert item["proposed"] is None
    assert item["choices"] == []

def test_explicit_usd_suffix_can_still_suggest_usd(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = repo / "contract.yaml"
    contract.write_text("""fields:
  - name: amount_usd
""")
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"

    assert run("scan", "--repo", str(repo), "--contract", str(contract),
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0

    data = json.loads(sg.read_text())
    item = next(x for x in data["suggestions"] if x["field"] == "amount_usd" and x["attribute"] == "unit")
    assert item["kind"] == "suggestion"
    assert item["proposed"] == ["USD"]


def test_current_jaffle_docs_support_event_time_and_usd(tmp_path):
    ev = tmp_path / "evidence.json"
    sg = tmp_path / "suggestions.json"
    skip = tmp_path / "skip.json"

    assert run("scan", "--repo", "public_pilot_jaffle_shop_current",
               "--contract", "public_pilot_jaffle_shop_current/contract.yaml",
               "--out", str(ev)).returncode == 0
    assert run("suggest", "--evidence", str(ev), "--out", str(sg),
               "--skip-file", str(skip)).returncode == 0

    data = json.loads(sg.read_text())
    by_key = {(x["field"], x["attribute"]): x for x in data["suggestions"]}

    assert by_key[("ordered_at","time_axis")]["kind"] == "suggestion"
    assert by_key[("ordered_at","time_axis")]["proposed"] == ["event_time"]
    assert by_key[("order_total","unit")]["kind"] == "suggestion"
    assert by_key[("order_total","unit")]["proposed"] == ["USD"]
