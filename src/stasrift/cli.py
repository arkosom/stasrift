#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
import difflib
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

VERDICTS = ["UNCHANGED", "NARROWED", "WIDENED", "INCOMPATIBLE"]
SEVERITY = {v: i for i, v in enumerate(VERDICTS)}

TIME_AXES = {
    "event_time", "processing_time", "ingestion_time",
    "valid_time", "transaction_time", "snapshot_time", "not_temporal",
}
ABSENT_MEANINGS = {
    "unknown", "not_applicable", "withheld",
    "zero_equivalent", "not_yet_computed",
}

class StasriftError(Exception):
    pass

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StasriftError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise StasriftError(f"non-finite JSON number: {value}")


if yaml is not None:
    class UniqueSafeLoader(yaml.SafeLoader):
        pass

    def _unique_yaml_mapping(loader, node):
        # Check explicitly written keys before SafeLoader expands merge defaults.
        # YAML merge precedence and explicit overrides remain backward compatible.
        seen = set()
        merge_seen = False
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                if merge_seen:
                    raise StasriftError("duplicate YAML merge key")
                merge_seen = True
                continue
            key = loader.construct_object(key_node, deep=True)
            try:
                if key in seen:
                    raise StasriftError(f"duplicate YAML key: {key}")
                seen.add(key)
            except TypeError as exc:
                raise StasriftError("YAML mapping keys must be hashable") from exc
        return loader.construct_mapping(node, deep=True)

    UniqueSafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_yaml_mapping)


def load_any(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        raise StasriftError(f"cannot read {path}: {e}") from e
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text, object_pairs_hook=_unique_json_object, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as e:
            raise StasriftError(f"invalid JSON in {path}: {e}") from e
    if yaml is None:
        raise StasriftError("PyYAML is required for YAML files. Install with: pip install PyYAML")
    try:
        return yaml.load(text, Loader=UniqueSafeLoader)
    except Exception as e:
        raise StasriftError(f"invalid YAML in {path}: {e}") from e

def dump_yaml(data):
    if yaml is None:
        raise StasriftError("PyYAML is required for YAML output.")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

def normalize_contract(data, source="<memory>"):
    if not isinstance(data, dict):
        raise StasriftError(f"{source}: contract root must be an object")
    _ensure_supported_contract_format(data, source)
    is_v1 = data.get("stasrift_format") == "stasrift-contract-v1"
    if is_v1 and not isinstance(data.get("fields"), list):
        raise StasriftError(f"{source}: v1 requires a fields list")
    raw_fields = None
    if isinstance(data.get("fields"), list):
        raw_fields = data["fields"]
    elif isinstance(data.get("properties"), list):
        raw_fields = data["properties"]
    elif isinstance(data.get("schema"), dict) and isinstance(data["schema"].get("properties"), list):
        raw_fields = data["schema"]["properties"]
    if raw_fields is None:
        raise StasriftError(f"{source}: expected a 'fields' list or ODCS-like 'properties' list")
    out = {}
    original_fields = {}
    for idx, item in enumerate(raw_fields):
        if not isinstance(item, dict):
            raise StasriftError(f"{source}: field #{idx+1} must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise StasriftError(f"{source}: field #{idx+1} missing valid 'name'")
        if is_v1 and "sem" in item and not isinstance(item["sem"], dict):
            raise StasriftError(f"{source}: v1 sem must be an object")
        sem = item.get("sem")
        if sem is None:
            cp = item.get("customProperties")
            if isinstance(cp, dict):
                sem = cp.get("sem")
        if name in out:
            if item == original_fields[name]:
                continue  # An exact repeated declaration carries no new meaning.
            raise StasriftError(f"{source}: conflicting duplicate field name '{name}'")
        original_fields[name] = item
        if sem is None:
            sem = {}
        if not isinstance(sem, dict):
            raise StasriftError(f"{source}: field '{name}' sem must be an object")
        unknown = set(sem) - {"time_axis", "unit", "absent"}
        if unknown:
            raise StasriftError(f"{source}: field '{name}' unsupported semantic attributes: {sorted(map(str, unknown))}")
        if is_v1 and "nullable" in item and not isinstance(item["nullable"], bool):
            raise StasriftError(f"{source}: nullable must be boolean")
        if is_v1:
            for attr, value in sem.items():
                if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                    raise StasriftError(f"{source}: v1 {attr} must be an array of strings")
                if len(value) != len(set(value)):
                    raise StasriftError(f"{source}: v1 {attr} values must be unique")
        nsem = {}
        if "time_axis" in sem:
            nsem["time_axis"] = normalize_modes(sem["time_axis"], "time_axis", name, source, TIME_AXES)
        if "unit" in sem:
            nsem["unit"] = normalize_modes(sem["unit"], "unit", name, source, None)
        if "absent" in sem:
            nsem["absent"] = normalize_modes(sem["absent"], "absent", name, source, ABSENT_MEANINGS)
        out[name] = nsem
    return out

def normalize_modes(value, attr, field, source, allowed):
    vals = [value] if isinstance(value, str) else value
    if not isinstance(vals, list) or not vals:
        raise StasriftError(f"{source}: field '{field}' attribute '{attr}' must be a non-empty string/list")
    clean = []
    for v in vals:
        if not isinstance(v, str) or not v.strip():
            raise StasriftError(f"{source}: field '{field}' attribute '{attr}' contains invalid value")
        v = v.strip()
        if allowed is not None and v not in allowed:
            raise StasriftError(f"{source}: field '{field}' attribute '{attr}' invalid value '{v}'")
        clean.append(v)
    return sorted(set(clean))

def load_contract(path):
    return normalize_contract(load_any(path), str(path))

def compare_modes(old, new):
    if old is None and new is None: return "UNCHANGED"
    if old is None and new is not None: return "NARROWED"
    if old is not None and new is None: return "WIDENED"
    a, b = set(old), set(new)
    if a == b: return "UNCHANGED"
    if b < a: return "NARROWED"
    if a < b: return "WIDENED"
    return "INCOMPATIBLE"

def fmt_modes(v):
    return "{any}" if v is None else "{" + ", ".join(v) + "}"

def reason_for_change(field, attr, old, new, verdict):
    old_s, new_s = fmt_modes(old), fmt_modes(new)
    if verdict == "NARROWED":
        return f"{field}.{attr} narrowed from {old_s} to {new_s}; new promise is stronger"
    if verdict == "WIDENED":
        return f"{field}.{attr} widened from {old_s} to {new_s}; consumers may require coordination"
    if verdict == "INCOMPATIBLE":
        return f"{field}.{attr} changed from {old_s} to {new_s}; neither version substitutes for the other"
    return f"{field}.{attr} unchanged"

def compare_contracts(old, new):
    fields = sorted(set(old) | set(new))
    results = []
    for field in fields:
        if field not in old:
            results.append({"name": field, "verdict": "NARROWED",
                            "reason": "field added; semantic layer treats addition as non-breaking"})
            continue
        if field not in new:
            results.append({"name": field, "verdict": "INCOMPATIBLE",
                            "reason": "field removed; shape-level break requires coordination"})
            continue
        attrs = sorted(set(old[field]) | set(new[field]))
        if not attrs:
            results.append({"name": field, "verdict": "UNCHANGED"})
            continue
        changes = []
        for attr in attrs:
            ov, nv = old[field].get(attr), new[field].get(attr)
            verdict = compare_modes(ov, nv)
            if verdict != "UNCHANGED":
                changes.append({
                    "attribute": attr, "verdict": verdict, "old": ov, "new": nv,
                    "reason": reason_for_change(field, attr, ov, nv, verdict),
                })
        if not changes:
            results.append({"name": field, "verdict": "UNCHANGED"})
        else:
            fv = max((c["verdict"] for c in changes), key=lambda v: SEVERITY[v])
            results.append({"name": field, "verdict": fv, "changes": changes})
    overall = max((r["verdict"] for r in results), key=lambda v: SEVERITY[v], default="UNCHANGED")
    counts = {v.lower(): sum(r["verdict"] == v for r in results) for v in VERDICTS}
    return {"verdict": overall, "fields": results, "counts": counts}

def print_human(result):
    print(result["verdict"])
    for f in result["fields"]:
        if f["verdict"] == "UNCHANGED":
            continue
        print(f"\n{f['name']}: {f['verdict']}")
        if "reason" in f:
            print(f"  {f['reason']}")
        for ch in f.get("changes", []):
            print(f"  {ch['attribute']}: {fmt_modes(ch.get('old'))} -> {fmt_modes(ch.get('new'))} [{ch['verdict']}]")
            print(f"    {ch['reason']}")
    c = result["counts"]
    print(f"\nSummary: {c['unchanged']} unchanged, {c['narrowed']} narrowed, "
          f"{c['widened']} widened, {c['incompatible']} incompatible")

# ---------- v0.2 scan/suggest ----------

NAME_RULES = [
    (re.compile(r"(processed|processing)(_at)?$", re.I), "processing_time", "field name indicates processing semantics"),
    (re.compile(r"(ingested|ingestion)(_at)?$", re.I), "ingestion_time", "field name indicates ingestion semantics"),
    (re.compile(r"(occurred|event|happened|ship|shipped)(_at)?$", re.I), "event_time", "field name indicates event semantics"),
    (re.compile(r"(valid)(_at|_time)?$", re.I), "valid_time", "field name indicates valid-time semantics"),
    (re.compile(r"(transaction|committed|commit)(_at|_time)?$", re.I), "transaction_time", "field name indicates transaction-time semantics"),
    (re.compile(r"(snapshot)(_at|_time)?$", re.I), "snapshot_time", "field name indicates snapshot semantics"),
]

def contract_field_names(data):
    n = normalize_contract(data)
    return sorted(n.keys())


# ---------- structured SQL lineage parsing (v0.5) ----------

def _split_top_level_csv(text):
    """Split a SQL SELECT list on top-level commas, respecting parentheses/quotes."""
    parts = []
    buf = []
    depth = 0
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                # Handle doubled SQL quotes: '' or ""
                if i + 1 < len(text) and text[i + 1] == quote:
                    buf.append(text[i + 1])
                    i += 1
                else:
                    quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def _extract_ctes(sql_text):
    """
    Extract simple WITH name AS (...) CTE bodies.
    Returns dict name -> body. Handles nested parentheses conservatively.
    """
    text = sql_text
    lower = text.lower()
    m = re.search(r"\bwith\b", lower)
    if not m:
        return {}
    i = m.end()
    ctes = {}
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        nm = re.match(r"([A-Za-z_][\w$]*)", text[i:])
        if not nm:
            break
        name = nm.group(1)
        i += nm.end()
        while i < len(text) and text[i].isspace():
            i += 1
        if not lower.startswith("as", i):
            break
        i += 2
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text) or text[i] != "(":
            break
        depth = 1
        start = i + 1
        i += 1
        quote = None
        while i < len(text) and depth:
            ch = text[i]
            if quote:
                if ch == quote:
                    if i + 1 < len(text) and text[i+1] == quote:
                        i += 2
                        continue
                    quote = None
                i += 1
                continue
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = text[start:i-1]
        ctes[name.lower()] = body
        while i < len(text) and text[i].isspace():
            i += 1
        if i < len(text) and text[i] == ",":
            i += 1
            continue
        break
    return ctes

def _sql_code(text):
    """Mask comments and string literals so prose cannot become lineage evidence."""
    pattern = r"--[^\n]*|/\*[\s\S]*?\*/|'(?:''|[^'])*'"
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text)


def _collect_cte_output_semantics(sql_text):
    """
    Infer simple alias semantics inside each CTE.
    Returns cte_name -> alias -> evidence summary.
    """
    sql_text = _sql_code(sql_text)
    result = {}
    for name, body in _extract_ctes(sql_text).items():
        aliases = {}
        for select_list, block_line in _find_select_blocks(body):
            for raw in _split_top_level_csv(select_list):
                expr, alias = _parse_select_item(raw)
                if not alias:
                    continue
                low = expr.lower()
                sem = set()
                if re.search(r"\b(current_timestamp|current_datetime|now\s*\(\s*\))\b", low):
                    sem.add(("time_axis", "processing_time"))
                if re.search(r"\b(source_)?(event|occurred)(?:_timestamp|_time|_at|_ts)?\b", low):
                    sem.add(("time_axis", "event_time"))
                if re.search(r"\b(ingest|ingested|ingestion)(?:_timestamp|_time|_at|_ts)?\b", low):
                    sem.add(("time_axis", "ingestion_time"))
                if re.search(r"/\s*100(?:\.0+)?\b", low):
                    sem.add(("unit", "question"))
                if re.search(r"\bcoalesce\s*\(", low):
                    sem.add(("absent", "question"))
                if sem:
                    aliases[alias.lower()] = sorted(sem)
        if aliases:
            result[name] = aliases
    return result

def _find_select_blocks(sql_text):
    """
    Lightweight structural SELECT parser.
    Extracts SELECT ... FROM blocks and preserves approximate source line.
    It is not a full SQL AST, but it reasons over expression structure rather
    than same-line string coincidence.
    """
    blocks = []
    # Strip line comments but keep line count stable.
    cleaned_lines = []
    for line in sql_text.splitlines():
        cleaned_lines.append(re.sub(r"--.*$", "", line))
    cleaned = "\n".join(cleaned_lines)

    # Conservative scanner for SELECT ... FROM at paren depth >= 0.
    lower = cleaned.lower()
    pos = 0
    while True:
        m = re.search(r"\bselect\b", lower[pos:])
        if not m:
            break
        s = pos + m.start()
        i = s + len("select")
        depth = 0
        quote = None
        from_pos = None
        while i < len(cleaned):
            ch = cleaned[i]
            if quote:
                if ch == quote:
                    if i + 1 < len(cleaned) and cleaned[i + 1] == quote:
                        i += 2
                        continue
                    quote = None
                i += 1
                continue
            if ch in ("'", '"', "`"):
                quote = ch
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0 and lower.startswith("from", i):
                before = lower[i - 1] if i > 0 else " "
                after = lower[i + 4] if i + 4 < len(lower) else " "
                if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                    from_pos = i
                    break
            i += 1
        if from_pos is None:
            pos = s + 6
            continue
        select_list = cleaned[s + len("select"):from_pos]
        line_no = cleaned[:s].count("\n") + 1
        blocks.append((select_list, line_no))
        pos = from_pos + 4
    return blocks

def _parse_select_item(expr):
    """Return (expression, alias). Alias may be None."""
    expr = expr.strip()
    # AS alias
    m = re.match(r"(?is)^(.*?)(?:\s+as\s+)([`\"\[]?[A-Za-z_][\w$]*[`\"\]]?)\s*$", expr)
    if m:
        return m.group(1).strip(), m.group(2).strip('`"[]')
    # Bare trailing alias, avoiding simple identifier-only expressions.
    m = re.match(r"(?is)^(.*\S)\s+([A-Za-z_][\w$]*)\s*$", expr)
    if m and not re.match(r"^[A-Za-z_][\w$.]*$", expr):
        return m.group(1).strip(), m.group(2)
    # Simple passthrough: table.field or field
    if re.match(r"^[A-Za-z_][\w$.]*$", expr):
        return expr, expr.split(".")[-1]
    return expr, None

def _sql_lineage_evidence(sql_text, relpath, fields):
    """
    Produce field-targeted evidence from SELECT expressions.
    v0.7 adds simple CTE propagation in addition to alias-aware expressions.
    """
    sql_text = _sql_code(_strip_jinja(sql_text))
    out = {f: [] for f in fields}
    if re.search(r"\b(join|union)\b", sql_text, re.I):
        return out
    cte_sem = _collect_cte_output_semantics(sql_text)

    for select_list, block_line in _find_select_blocks(sql_text):
        items = _split_top_level_csv(select_list)
        running_line = block_line
        for raw in items:
            expr, alias = _parse_select_item(raw)
            if not alias or alias not in out:
                running_line += raw.count("\n")
                continue

            src = f"{relpath}:{running_line}"
            low = expr.lower()

            def add(attr, supports, desc):
                out[alias].append({
                    "type": "lineage",
                    "attribute": attr,
                    "supports": supports,
                    "description": desc,
                    "source": src,
                })

            if re.search(r"\b(current_timestamp|current_datetime|now\s*\(\s*\))\b", low):
                add("time_axis", "processing_time", "output expression is stamped with current pipeline time")

            if re.search(r"\b(source_)?(event|occurred)(?:_timestamp|_time|_at|_ts)?\b", low):
                add("time_axis", "event_time", "output expression derives from event/source-event time")

            if re.search(r"\b(ingest|ingested|ingestion)(?:_timestamp|_time|_at|_ts)?\b", low):
                add("time_axis", "ingestion_time", "output expression derives from ingestion time")

            if re.search(r"/\s*100(?:\.0+)?\b", low):
                add("unit", "question", "output expression scales by 100; unit and currency require human declaration")

            if re.search(r"\bcoalesce\s*\(", low):
                out[alias].append({
                    "type": "usage",
                    "attribute": "absent",
                    "supports": "question",
                    "description": "output expression applies COALESCE; null meaning affects behavior",
                    "source": src,
                })

            # Simple CTE passthrough propagation: cte_alias.field or bare field.
            refm = re.fullmatch(r"(?:(\w+)\.)?([A-Za-z_][\w$]*)", expr.strip())
            if refm:
                cte_name = (refm.group(1) or "").lower()
                ref_field = refm.group(2).lower()

                if cte_name and cte_name in cte_sem and ref_field in cte_sem[cte_name]:
                    for attr, supports in cte_sem[cte_name][ref_field]:
                        if attr == "absent":
                            out[alias].append({
                                "type": "usage",
                                "attribute": "absent",
                                "supports": "question",
                                "description": f"output inherits null-sensitive behavior from CTE {cte_name}.{ref_field}",
                                "source": src,
                            })
                        else:
                            add(attr, supports, f"output inherits {attr} semantics from CTE {cte_name}.{ref_field}")
                else:
                    # If bare field, propagate from any unique CTE that exposes it.
                    matches = []
                    for cn, amap in cte_sem.items():
                        if ref_field in amap:
                            matches.append((cn, amap[ref_field]))
                    if len(matches) == 1:
                        cn, semantics = matches[0]
                        for attr, supports in semantics:
                            if attr == "absent":
                                out[alias].append({
                                    "type": "usage",
                                    "attribute": "absent",
                                    "supports": "question",
                                    "description": f"output inherits null-sensitive behavior from CTE {cn}.{ref_field}",
                                    "source": src,
                                })
                            else:
                                add(attr, supports, f"output inherits {attr} semantics from CTE {cn}.{ref_field}")

            running_line += raw.count("\n")
    return out


# ---------- dbt/Jinja project support (v0.8) ----------

DBT_REF_RE = re.compile(r"\{\{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}")
DBT_SOURCE_RE = re.compile(
    r"\{\{\s*source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
)

def _strip_jinja(sql_text):
    """
    Replace common dbt/Jinja refs with stable SQL-ish identifiers so the
    structural SQL scanner can continue operating deterministically.
    Unknown template blocks are replaced with whitespace to preserve line count.
    """
    text = DBT_REF_RE.sub(lambda m: f"__dbt_ref_{m.group(1)}", sql_text)
    text = DBT_SOURCE_RE.sub(lambda m: f"__dbt_source_{m.group(1)}_{m.group(2)}", text)

    # Preserve newlines while removing remaining {{ ... }} and {% ... %}.
    def blank(m):
        s = m.group(0)
        return "".join("\n" if c == "\n" else " " for c in s)

    text = re.sub(r"\{\{.*?\}\}", blank, text, flags=re.S)
    text = re.sub(r"\{%.*?%\}", blank, text, flags=re.S)
    return text

def _dbt_model_name(path):
    return Path(path).stem

def _dbt_dependencies(sql_text):
    refs = sorted(set(DBT_REF_RE.findall(sql_text)))
    sources = sorted(set(".".join(x) for x in DBT_SOURCE_RE.findall(sql_text)))
    return {"refs": refs, "sources": sources}


def _top_level_contains(sql_text, keyword):
    """
    Return True when keyword appears at top level outside quotes/parens.
    Used to conservatively detect UNION/JOIN ambiguity.
    """
    lower = sql_text.lower()
    depth = 0
    quote = None
    i = 0
    kw = keyword.lower()
    while i < len(sql_text):
        ch = sql_text[i]
        if quote:
            if ch == quote:
                if i + 1 < len(sql_text) and sql_text[i+1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and lower.startswith(kw, i):
            before = lower[i-1] if i > 0 else " "
            after = lower[i+len(kw)] if i+len(kw) < len(lower) else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                return True
        i += 1
    return False

def _count_top_level_refs(sql_text):
    """Count top-level dbt ref() occurrences after Jinja preservation."""
    return len(set(DBT_REF_RE.findall(sql_text)))

def _field_sources_from_select(sql_text):
    """
    Map output alias -> simple source expression for final SELECT.
    Used only for ambiguity checks, not semantic inference.
    """
    cleaned = _strip_jinja(sql_text)
    blocks = _find_select_blocks(cleaned)
    if not blocks:
        return {}
    select_list, _ = blocks[-1]
    out = {}
    for raw in _split_top_level_csv(select_list):
        expr, alias = _parse_select_item(raw)
        if alias:
            out[alias.lower()] = expr.strip()
    return out

def _collect_model_output_semantics(sql_text):
    """
    Collect semantics for the final SELECT outputs in one model.

    v0.9 restraint rules:
    - top-level UNION disables semantic propagation for the whole model
    - multi-ref models only emit direct local semantics, never inherited ones
    - ambiguous bare passthroughs are not inferred
    """
    if _top_level_contains(_strip_jinja(sql_text), "union"):
        return {}

    cleaned = _sql_code(_strip_jinja(sql_text))
    if re.search(r"\b(join|union)\b", cleaned, re.I):
        return {}
    cte_sem = _collect_cte_output_semantics(cleaned)
    outputs = {}

    blocks = _find_select_blocks(cleaned)
    if not blocks:
        return outputs

    select_list, block_line = blocks[-1]
    for raw in _split_top_level_csv(select_list):
        expr, alias = _parse_select_item(raw)
        if not alias:
            continue
        low = expr.lower()
        sem = set()

        # Direct local evidence is always allowed.
        if re.search(r"\b(current_timestamp|current_datetime|now\s*\(\s*\))\b", low):
            sem.add(("time_axis", "processing_time"))
        if re.search(r"\b(source_)?(event|occurred)(?:_timestamp|_time|_at|_ts)?\b", low):
            sem.add(("time_axis", "event_time"))
        if re.search(r"\b(ingest|ingested|ingestion)(?:_timestamp|_time|_at|_ts)?\b", low):
            sem.add(("time_axis", "ingestion_time"))
        if re.search(r"/\s*100(?:\.0+)?\b", low):
            sem.add(("unit", "question"))
        if re.search(r"\bcoalesce\s*\(", low):
            sem.add(("absent", "question"))

        # CTE passthrough is only safe when a unique source resolves.
        refm = re.fullmatch(r"(?:(\w+)\.)?([A-Za-z_][\w$]*)", expr.strip())
        if refm:
            cte_name = (refm.group(1) or "").lower()
            ref_field = refm.group(2).lower()
            if cte_name and cte_name in cte_sem and ref_field in cte_sem[cte_name]:
                sem.update(cte_sem[cte_name][ref_field])
            elif not cte_name:
                matches = []
                for cn, amap in cte_sem.items():
                    if ref_field in amap:
                        matches.append(amap[ref_field])
                if len(matches) == 1:
                    sem.update(matches[0])

        if sem:
            outputs[alias.lower()] = sorted(sem)
    return outputs

def _build_dbt_model_index(repo):
    """
    Build a small cross-file model index:
      model_name -> {path, deps, outputs}
    """
    repo = Path(repo)
    index = {}
    for p in sorted(repo.rglob("*.sql")):
        try:
            raw = p.read_text(encoding="utf-8", errors="strict")
        except Exception:
            continue
        name = _dbt_model_name(p)
        deps = _dbt_dependencies(raw)
        cleaned = _strip_jinja(raw)
        index[name] = {
            "path": str(p.relative_to(repo)),
            "deps": deps,
            "outputs": _collect_model_output_semantics(raw),
            "raw": raw,
            "uncertainty": {
                "top_level_union": _top_level_contains(cleaned, "union"),
                "multiple_refs": len(deps["refs"]) > 1,
            },
        }
    return index

def _propagate_dbt_semantics(index, max_rounds=8):
    """
    Propagate semantics across ref() boundaries conservatively.

    v0.9:
    - only exactly one upstream ref is eligible
    - any top-level UNION disables propagation
    - multi-ref joins do not propagate inherited semantics
    - simple passthrough same-name fields only
    """
    for _ in range(max_rounds):
        changed = False
        for model, info in index.items():
            refs = info["deps"]["refs"]

            if re.search(r"\b(join|union)\b", _sql_code(_strip_jinja(info["raw"])), re.I):
                continue

            if len(refs) != 1:
                continue

            upstream = index.get(refs[0])
            if not upstream:
                continue

            cleaned = _strip_jinja(info["raw"])
            blocks = _find_select_blocks(cleaned)
            if not blocks:
                continue
            select_list, _ = blocks[-1]

            for raw in _split_top_level_csv(select_list):
                expr, alias = _parse_select_item(raw)
                if not alias:
                    continue

                m = re.fullmatch(r"(?:(\w+)\.)?([A-Za-z_][\w$]*)", expr.strip())
                if not m:
                    continue

                src_field = m.group(2).lower()
                up_sem = upstream["outputs"].get(src_field)
                if not up_sem:
                    continue

                cur = set(tuple(x) for x in info["outputs"].get(alias.lower(), []))
                new = cur | set(tuple(x) for x in up_sem)
                if new != cur:
                    info["outputs"][alias.lower()] = sorted(new)
                    changed = True
        if not changed:
            break
    return index

def _dbt_cross_file_evidence(repo, fields):
    index = _propagate_dbt_semantics(_build_dbt_model_index(repo))
    evidence = {f: [] for f in fields}

    for model, info in sorted(index.items()):
        uncertain = info.get("uncertainty", {})
        if uncertain.get("top_level_union") or uncertain.get("multiple_refs"):
            reason = []
            if uncertain.get("top_level_union"):
                reason.append("top-level UNION")
            if uncertain.get("multiple_refs"):
                reason.append("multiple upstream refs")
            for field in fields:
                evidence[field].append({
                    "type": "uncertainty",
                    "attribute": "lineage",
                    "supports": "unknown",
                    "description": f"Stasrift refused inherited semantic inference in dbt model '{model}' due to " + " and ".join(reason),
                    "source": info["path"],
                })

        for field in fields:
            sems = info["outputs"].get(field.lower(), [])
            for attr, supports in sems:
                typ = "usage" if attr == "absent" else "lineage"
                desc = (
                    f"field semantics propagated through dbt model '{model}'"
                    if info["deps"]["refs"]
                    else f"field semantics observed in SQL model '{model}'"
                )
                evidence[field].append({
                    "type": typ,
                    "attribute": attr,
                    "supports": supports,
                    "description": desc,
                    "source": info["path"],
                })

    for field in evidence:
        uniq = {}
        for e in evidence[field]:
            key = (e["type"], e["attribute"], e["supports"], e["description"], e["source"])
            uniq[key] = e
        evidence[field] = sorted(
            uniq.values(),
            key=lambda x: (x["attribute"], x["type"], str(x["supports"]), x["source"])
        )
    return evidence


# ---------- dbt/model documentation evidence (rc4) ----------

def _walk_model_docs(data):
    """
    Yield (model_name, column_dict) from dbt-style YAML docs.
    Parsing only; never writes semantic declarations.
    """
    if not isinstance(data, dict):
        return
    models = data.get("models")
    if not isinstance(models, list):
        return
    for model in models:
        if not isinstance(model, dict):
            continue
        model_name = model.get("name")
        cols = model.get("columns")
        if not isinstance(cols, list):
            continue
        for col in cols:
            if isinstance(col, dict) and isinstance(col.get("name"), str):
                yield model_name, col

def _docs_evidence(repo, fields):
    """
    Extract conservative evidence from dbt/model YAML documentation.

    Rules:
    - explicit currency tokens (USD/EUR/GBP/AUD/CAD/JPY) may support a unit suggestion
    - phrases like 'timestamp ... placed/occurred' may support event_time
    - dbt semantic-layer 'dimension: type: time' proves temporal relevance only,
      so it asks for a human time-axis declaration rather than choosing one.
    """
    repo = Path(repo)
    out = {f: [] for f in fields}
    currencies = {"USD", "EUR", "GBP", "AUD", "CAD", "JPY"}

    for p in sorted(repo.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in {".yml", ".yaml"}:
            continue
        try:
            data = load_any(p)
        except Exception:
            continue

        rel = str(p.relative_to(repo))
        for model_name, col in _walk_model_docs(data):
            name = col.get("name")
            if name not in out:
                continue

            desc = col.get("description")
            desc_text = desc if isinstance(desc, str) else ""
            desc_upper = desc_text.upper()
            desc_lower = desc_text.lower()

            for cur in sorted(currencies):
                if re.search(rf"\b{re.escape(cur)}\b", desc_upper):
                    out[name].append({
                        "type": "documentation",
                        "attribute": "unit",
                        "supports": cur,
                        "description": f"dbt documentation explicitly names currency {cur}",
                        "source": rel,
                    })

            if (
                ("timestamp" in desc_lower or "time" in desc_lower)
                and any(w in desc_lower for w in ("placed", "occurred", "happened", "created by customer"))
            ):
                out[name].append({
                    "type": "documentation",
                    "attribute": "time_axis",
                    "supports": "event_time",
                    "description": "dbt documentation describes when the business event occurred",
                    "source": rel,
                })

            dim = col.get("dimension")
            if isinstance(dim, dict) and dim.get("type") == "time":
                out[name].append({
                    "type": "documentation",
                    "attribute": "time_axis",
                    "supports": "question",
                    "description": "dbt Semantic Layer marks this column as a time dimension; exact time axis is not declared",
                    "source": rel,
                })

    for field in out:
        uniq = {}
        for e in out[field]:
            key = (e["type"], e["attribute"], e["supports"], e["description"], e["source"])
            uniq[key] = e
        out[field] = sorted(
            uniq.values(),
            key=lambda x: (x["attribute"], x["type"], str(x["supports"]), x["source"])
        )
    return out

def scan_repo(repo, contract, out):
    repo = Path(repo).resolve()
    contract = Path(contract).resolve()
    if not repo.exists() or not repo.is_dir():
        raise StasriftError(f"repo root does not exist or is not a directory: {repo}")
    cdata = load_any(contract)
    fields = contract_field_names(cdata)
    evidence = {f: [] for f in fields}

    # Name evidence
    for field in fields:
        for rx, target, desc in NAME_RULES:
            if rx.search(field):
                evidence[field].append({
                    "type": "name",
                    "attribute": "time_axis",
                    "supports": target,
                    "description": desc,
                    "source": f"{contract.name}:{field}",
                })

        # Unit heuristics from field names; low-confidence only.
        low = field.lower()
        unit_support = None
        unit_desc = None
        if low.endswith("_usd"):
            unit_support, unit_desc = "USD", "field name suggests U.S. dollars"
        elif low.endswith("_eur") or low.endswith("_euros"):
            unit_support, unit_desc = "EUR", "field name suggests euros"
        elif low.endswith(("_cents", "_dollars")):
            unit_support, unit_desc = "question", "field name suggests a currency denomination; currency is not inferable"
        elif low.endswith("_ms") and not any(x in low for x in ("timestamp", "time", "latency", "duration")):
            unit_support, unit_desc = "ms", "field name suffix suggests milliseconds"
        if unit_support:
            evidence[field].append({
                "type": "name",
                "attribute": "unit",
                "supports": unit_support,
                "description": unit_desc,
                "source": f"{contract.name}:{field}",
            })

    # Structural nullability from contract, for human-only absent-semantics questions.
    raw_fields = cdata.get("fields") if isinstance(cdata.get("fields"), list) else cdata.get("properties", [])
    raw_map = {x.get("name"): x for x in raw_fields if isinstance(x, dict) and x.get("name")}
    for field in fields:
        item = raw_map.get(field, {})
        nullable = False
        t = item.get("type")
        if isinstance(t, list) and "null" in t:
            nullable = True
        if item.get("required") is False or item.get("nullable") is True:
            nullable = True
        if nullable:
            evidence[field].append({
                "type": "structure",
                "attribute": "absent",
                "supports": "question",
                "description": "field is nullable; null meaning may matter downstream",
                "source": f"{contract.name}:{field}",
            })

    # SQL evidence: structured SELECT-list parsing.
    # Python remains a conservative lexical fallback.
    source_files = sorted([
        p for p in repo.rglob("*")
        if p.is_file() and p.suffix.lower() in {".sql", ".py"}
    ])
    parse_errors = []
    for p in source_files:
        try:
            raw_text = p.read_text(encoding="utf-8", errors="strict")
        except Exception as e:
            parse_errors.append({"file": str(p.relative_to(repo)), "error": str(e)})
            continue

        rel = str(p.relative_to(repo))

        if p.suffix.lower() == ".sql":
            structured = _sql_lineage_evidence(raw_text, rel, fields)
            for field, items in structured.items():
                evidence[field].extend(items)
            continue

        # Python fallback: conservative same-line references only.
        for lineno, line in enumerate(raw_text.splitlines(), 1):
            lowline = line.lower()
            for field in fields:
                if field.lower() not in lowline:
                    continue
                if re.search(r"\b(datetime\.now|datetime\.utcnow|time\.time)\b", lowline):
                    evidence[field].append({
                        "type": "lineage",
                        "attribute": "time_axis",
                        "supports": "processing_time",
                        "description": "field appears assigned from current runtime time",
                        "source": f"{rel}:{lineno}",
                    })

    # Documentation evidence (dbt/model YAML).
    docs_evidence = _docs_evidence(repo, fields)
    for field, items in docs_evidence.items():
        evidence[field].extend(items)

    # Cross-file dbt/Jinja-aware evidence.
    dbt_evidence = _dbt_cross_file_evidence(repo, fields)
    for field, items in dbt_evidence.items():
        evidence[field].extend(items)

    for f in evidence:
        # Deduplicate before sorting.
        uniq = {}
        for e in evidence[f]:
            key = (
                e.get("attribute",""), e.get("type",""),
                str(e.get("supports","")), e.get("source",""),
                e.get("description","")
            )
            uniq[key] = e
        evidence[f] = sorted(
            uniq.values(),
            key=lambda x: (
                x.get("attribute",""),
                x["type"],
                str(x.get("supports","")),
                x["source"],
                x["description"],
            ),
        )

    bundle = {
        "format": "stasrift-evidence-v2",
        "repo": ".",
        "contract": contract.name,
        "contract_sha256": sha256_text(contract.read_text(encoding="utf-8")),
        "fields": [{"name": f, "evidence": evidence[f]} for f in sorted(fields)],
        "parse_errors": parse_errors,
    }
    Path(out).write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle

def _confidence_for(evidence, target):
    types = set(e["type"] for e in evidence if e.get("supports") == target)
    # High only when two independent evidence types converge and one is structural/lineage.
    if len(types) >= 2 and ("lineage" in types or "structure" in types):
        return "high"
    if "lineage" in types:
        return "medium"
    return "low"

def suggestion_for_field(item):
    field = item["name"]
    ev = item.get("evidence", [])
    out = []

    # time_axis: suggest or conflict
    all_tev = [e for e in ev if e.get("attribute") == "time_axis"]
    tev = [e for e in all_tev if e.get("supports") not in (None, "question")]
    time_questions = [e for e in all_tev if e.get("supports") == "question"]
    contenders = sorted(set(e.get("supports") for e in tev if e.get("supports")))
    if len(contenders) > 1:
        out.append({
            "field": field,
            "kind": "conflict",
            "attribute": "time_axis",
            "proposed": None,
            "confidence": None,
            "contenders": contenders,
            "allowed_actions": ["decide", "skip"],
            "for_evidence": {c: [e for e in tev if e.get("supports") == c] for c in contenders},
            "evidence": tev,
        })
    elif len(contenders) == 1:
        target = contenders[0]
        conf = _confidence_for(tev, target)
        actions = ["confirm", "edit", "skip"] if conf in {"high","medium"} else ["choose", "skip"]
        out.append({
            "field": field,
            "kind": "suggestion",
            "attribute": "time_axis",
            "proposed": [target],
            "confidence": conf,
            "allowed_actions": actions,
            "rule_id": "time-axis-evidence-v3",
            "evidence": tev,
        })
    elif time_questions:
        out.append({
            "field": field,
            "kind": "question",
            "attribute": "time_axis",
            "proposed": None,
            "confidence": None,
            "choices": sorted(TIME_AXES),
            "allowed_actions": ["answer", "skip"],
            "rule_id": "time-axis-human-only-v1",
            "evidence": time_questions,
        })

    # unit: concrete evidence may suggest; cents conversion alone can only ask.
    all_uev = [e for e in ev if e.get("attribute") == "unit"]
    uev = [e for e in all_uev if e.get("supports") not in (None, "question")]
    unit_questions = [e for e in all_uev if e.get("supports") == "question"]
    units = sorted(set(e.get("supports") for e in uev if e.get("supports")))
    if len(units) > 1:
        out.append({
            "field": field,
            "kind": "conflict",
            "attribute": "unit",
            "proposed": None,
            "confidence": None,
            "contenders": units,
            "allowed_actions": ["decide", "skip"],
            "for_evidence": {c: [e for e in uev if e.get("supports") == c] for c in units},
            "evidence": uev,
        })
    elif len(units) == 1:
        target = units[0]
        conf = "medium" if len(set(e["type"] for e in uev)) >= 2 else "low"
        actions = ["confirm", "edit", "skip"] if conf == "medium" else ["choose", "skip"]
        out.append({
            "field": field,
            "kind": "suggestion",
            "attribute": "unit",
            "proposed": [target],
            "confidence": conf,
            "allowed_actions": actions,
            "rule_id": "unit-evidence-v2",
            "evidence": uev,
        })
    elif unit_questions:
        out.append({
            "field": field,
            "kind": "question",
            "attribute": "unit",
            "proposed": None,
            "confidence": None,
            "choices": [],
            "allowed_actions": ["answer", "skip"],
            "rule_id": "unit-human-only-v1",
            "evidence": unit_questions,
        })

    # absent: always a human-only question if nullable + downstream null-sensitive use,
    # or at least explicit nullability evidence exists.
    aev = [e for e in ev if e.get("attribute") == "absent"]
    if aev:
        out.append({
            "field": field,
            "kind": "question",
            "attribute": "absent",
            "proposed": None,
            "confidence": None,
            "choices": sorted(ABSENT_MEANINGS),
            "allowed_actions": ["answer", "skip"],
            "rule_id": "absent-human-only-v1",
            "evidence": aev,
        })

    return out

def _validate_bundle_items(items, name_key):
    if not isinstance(items, list):
        raise StasriftError("bundle items must be a list")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get(name_key), str):
            raise StasriftError("bundle item requires a string field name")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            raise StasriftError("evidence must be a list")
        for entry in evidence:
            if not isinstance(entry, dict) or any(
                not isinstance(entry.get(key), str)
                for key in ("type", "attribute", "supports", "description", "source")
            ):
                raise StasriftError("malformed evidence entry")
            attr, support = entry["attribute"], entry["supports"]
            if attr == "time_axis" and support not in TIME_AXES | {"question"}:
                raise StasriftError("unsupported time-axis evidence")


def suggest_from_bundle(bundle, out=None, skip_file=None):
    if not isinstance(bundle, dict) or bundle.get("format") not in ("stasrift-evidence-v1", "stasrift-evidence-v2"):
        raise StasriftError("malformed or unsupported evidence bundle")

    _validate_bundle_items(bundle.get("fields", []), "name")
    skipped = {}
    if skip_file and Path(skip_file).exists():
        try:
            skipped = json.loads(Path(skip_file).read_text(encoding="utf-8"))
        except Exception:
            skipped = {}

    if not isinstance(skipped, dict):
        raise StasriftError("skip state must be an object")
    suggestions = []
    for item in sorted(bundle.get("fields", []), key=lambda x: x.get("name", "")):
        for s in suggestion_for_field(item):
            key = f"{s['field']}::{s['attribute']}"
            ev_hash = sha256_text(canonical(s.get("evidence", [])))
            prev = skipped.get(key)
            s["new_evidence"] = not (isinstance(prev, dict) and prev.get("evidence_hash") == ev_hash)
            s["evidence_hash"] = ev_hash

            # Respect skip persistence unless new evidence appeared.
            if isinstance(prev, dict) and prev.get("evidence_hash") == ev_hash:
                continue
            suggestions.append(s)

    result = {
        "format": "stasrift-suggestions-v2",
        "source_contract_sha256": bundle.get("contract_sha256"),
        "suggestions": suggestions,
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    return result

def cmd_scan(args):
    bundle = scan_repo(args.repo, args.contract, args.out)
    if args.json:
        print(json.dumps(bundle, indent=2, sort_keys=True))
    else:
        n_ev = sum(len(f["evidence"]) for f in bundle["fields"])
        print(f"SCAN COMPLETE: {len(bundle['fields'])} fields, {n_ev} evidence items")
        print(f"Wrote {args.out}")
    return 0

def cmd_suggest(args):
    bundle = load_any(args.evidence)
    result = suggest_from_bundle(bundle, args.out, args.skip_file)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if not result["suggestions"]:
            print("No semantic suggestions or conflicts.")
        for s in result["suggestions"]:
            if s["kind"] == "conflict":
                print(f"{s['field']}: CONFLICT -> {', '.join(s['contenders'])}")
            elif s["kind"] == "question":
                print(f"{s['field']}: QUESTION -> declare {s['attribute']} manually")
            else:
                print(f"{s['field']}: suggest {s['attribute']}={s['proposed'][0]} ({s['confidence']})")
        print(f"Wrote {args.out}")
    return 0

def apply_decisions_to_contract(contract_data, decisions):
    # minimal fields-list only for v0.2 writer
    if not isinstance(contract_data, dict) or not isinstance(contract_data.get("fields"), list):
        raise StasriftError("review/write currently supports the minimal 'fields' contract shape")
    by_name = {}
    for field in contract_data["fields"]:
        if isinstance(field, dict):
            by_name.setdefault(field.get("name"), []).append(field)
    for d in decisions:
        if d.get("action") not in {"confirm", "decide"}:
            continue
        name = d["field"]
        value = d["value"]
        attr = d["attribute"]
        if name not in by_name:
            continue
        for field in by_name[name]:
            sem = field.setdefault("sem", {})
            sem[attr] = value if isinstance(value, list) else [value]
    return contract_data


# ---------- terminal review UI ----------

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}

def _color_enabled(args=None):
    if args is not None and getattr(args, "no_color", False):
        return False
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

def _c(text, color, enabled=True, bold=False):
    if not enabled:
        return str(text)
    prefix = ANSI["bold"] if bold else ""
    return f"{prefix}{ANSI[color]}{text}{ANSI['reset']}"

def _rule(title="", width=72):
    if title:
        pad = max(2, width - len(title) - 2)
        return f"─ {title} " + "─" * pad
    return "─" * width

def _progress(done, total):
    if total <= 0:
        return "[0/0]"
    width = 16
    filled = round(width * done / total)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {done}/{total}"

def _print_evidence(evidence, enabled):
    for e in evidence[:3]:
        src = e.get("source", "?")
        desc = e.get("description", "")
        print("  " + _c("•", "gray", enabled) + f" {desc}")
        print("    " + _c(src, "gray", enabled))

def _show_yaml_diff(old_text, new_text, enabled):
    diff = list(difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile="before",
        tofile="after",
        lineterm=""
    ))
    if not diff:
        print(_c("No file changes.", "gray", enabled))
        return
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            print(_c(line, "cyan", enabled))
        elif line.startswith("+"):
            print(_c(line, "green", enabled))
        elif line.startswith("-"):
            print(_c(line, "red", enabled))
        elif line.startswith("@@"):
            print(_c(line, "yellow", enabled))
        else:
            print(line)

def _load_skip_state(path):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_skip_state(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def cmd_review(args):
    props = load_any(args.suggestions)
    if not isinstance(props, dict) or props.get("format") not in ("stasrift-suggestions-v1", "stasrift-suggestions-v2"):
        raise StasriftError("unsupported suggestions file")

    contract_path = Path(args.contract)
    original_text = contract_path.read_text(encoding="utf-8")
    original_hash = sha256_text(original_text)
    contract_data = load_any(contract_path)
    normalize_contract(contract_data, str(contract_path))
    if props.get("source_contract_sha256") not in (None, original_hash):
        raise StasriftError("suggestions are stale: contract hash has changed; scan and suggest again")

    skip_state = _load_skip_state(args.skip_file)
    decisions = []
    items = props.get("suggestions", [])
    _validate_bundle_items(items, "field")
    known_fields = normalize_contract(contract_data)
    for item in items:
        attr = item.get("attribute")
        if item["field"] not in known_fields or attr not in ("time_axis", "unit", "absent"):
            raise StasriftError("suggestion targets unknown field or semantic attribute")
        if item.get("kind") not in ("suggestion", "question", "conflict"):
            raise StasriftError("unsupported suggestion kind")
        for key in ("allowed_actions", "choices", "contenders"):
            if not isinstance(item.get(key, []), list) or any(not isinstance(v, str) for v in item.get(key, [])):
                raise StasriftError(f"suggestion {key} must be a string list")
        if item["kind"] == "suggestion":
            if not isinstance(item.get("proposed"), list):
                raise StasriftError("proposed values must be a list")
            normalize_modes(item.get("proposed"), attr, item["field"], "suggestion", TIME_AXES if attr == "time_axis" else ABSENT_MEANINGS if attr == "absent" else None)
    total = len(items)
    done = 0
    enabled = _color_enabled(args)

    print(_rule("STASRIFT REVIEW"))
    print(_c("Semantic review", "cyan", enabled, bold=True))
    print(f"{contract_path}")
    print(_c("No semantic meaning is written until you approve the final diff.", "gray", enabled))
    print()

    for s in items:
        print(_rule())
        print(_progress(done, total))
        print()
        title = f"{s['field']} · {s['attribute']}"
        print(_c(title, "cyan", enabled, bold=True))

        kind = s["kind"]
        if kind == "suggestion":
            conf = s.get("confidence")
            conf_color = "green" if conf == "high" else "yellow" if conf == "medium" else "gray"
            print("Status: " + _c("SUGGESTION", "cyan", enabled) +
                  "   Confidence: " + _c(conf or "n/a", conf_color, enabled))
        elif kind == "conflict":
            print("Status: " + _c("CONFLICT", "red", enabled, bold=True))
        else:
            print("Status: " + _c("HUMAN DECISION", "yellow", enabled))

        _print_evidence(s.get("evidence", []), enabled)
        print()

        key = f"{s['field']}::{s['attribute']}"

        if kind == "suggestion":
            val = s["proposed"][0]
            actions = s.get("allowed_actions", [])
            print("Proposed: " + _c(f"{s['attribute']} = {val}", "green", enabled, bold=True))

            if "confirm" in actions:
                print("[1] Confirm   [2] Edit   [3] Skip   [q] Finish later")
                ans = input("> ").strip().lower()
                if ans == "q":
                    print(_c("Review paused. Nothing written.", "gray", enabled))
                    return 0
                if ans in {"1","y","yes"}:
                    decisions.append({"field": s["field"], "attribute": s["attribute"],
                                      "action": "confirm", "value": s["proposed"]})
                elif ans in {"2","e","edit"}:
                    newv = input(f"Choose value for {s['attribute']}: ").strip()
                    decisions.append({"field": s["field"], "attribute": s["attribute"],
                                      "action": "decide", "value": [newv]})
                else:
                    decisions.append({"field": s["field"], "attribute": s["attribute"], "action": "skip"})
                    skip_state[key] = {"evidence_hash": s.get("evidence_hash")}
            else:
                print(_c("Low confidence: Stasrift will not offer one-click confirmation.", "yellow", enabled))
                print("[1] Choose value   [2] Skip   [q] Finish later")
                ans = input("> ").strip().lower()
                if ans == "q":
                    print(_c("Review paused. Nothing written.", "gray", enabled))
                    return 0
                if ans in {"1","e","choose"}:
                    newv = input(f"Choose value for {s['attribute']}: ").strip()
                    decisions.append({"field": s["field"], "attribute": s["attribute"],
                                      "action": "decide", "value": [newv]})
                else:
                    decisions.append({"field": s["field"], "attribute": s["attribute"], "action": "skip"})
                    skip_state[key] = {"evidence_hash": s.get("evidence_hash")}

        elif kind == "conflict":
            print("Contenders: " + _c(" / ".join(s.get("contenders", [])), "red", enabled, bold=True))
            print(_c("Stasrift refuses to guess when evidence conflicts.", "gray", enabled))
            print("[1] Decide manually   [2] Skip   [q] Finish later")
            ans = input("> ").strip().lower()
            if ans == "q":
                print(_c("Review paused. Nothing written.", "gray", enabled))
                return 0
            if ans in {"1","d","decide"}:
                newv = input(f"Choose value for {s['attribute']}: ").strip()
                decisions.append({"field": s["field"], "attribute": s["attribute"],
                                  "action": "decide", "value": [newv]})
            else:
                decisions.append({"field": s["field"], "attribute": s["attribute"], "action": "skip"})
                skip_state[key] = {"evidence_hash": s.get("evidence_hash")}

        elif kind == "question":
            choices = s.get("choices", [])
            if choices:
                print("Choose one:")
                for i, choice in enumerate(choices, 1):
                    print(f"  [{i}] {choice}")
                print("  [s] Skip")
                print("  [q] Finish later")
                ans = input("> ").strip().lower()
                if ans == "q":
                    print(_c("Review paused. Nothing written.", "gray", enabled))
                    return 0
                if ans == "s":
                    decisions.append({"field": s["field"], "attribute": s["attribute"], "action": "skip"})
                    skip_state[key] = {"evidence_hash": s.get("evidence_hash")}
                else:
                    try:
                        selection = int(ans)
                        if not 1 <= selection <= len(choices):
                            raise ValueError("selection out of range")
                        choice = choices[selection-1]
                    except Exception:
                        raise StasriftError(f"invalid selection for {s['attribute']}")
                    decisions.append({"field": s["field"], "attribute": s["attribute"],
                                      "action": "decide", "value": [choice]})
            else:
                print(f"Human declaration required for {s['attribute']}.")
                ans = input("Enter value, [s]kip, or [q] finish later: ").strip()
                if ans.lower() == "q":
                    print(_c("Review paused. Nothing written.", "gray", enabled))
                    return 0
                if ans.lower() == "s":
                    decisions.append({"field": s["field"], "attribute": s["attribute"], "action": "skip"})
                    skip_state[key] = {"evidence_hash": s.get("evidence_hash")}
                elif ans:
                    decisions.append({"field": s["field"], "attribute": s["attribute"],
                                      "action": "decide", "value": [ans]})
                else:
                    raise StasriftError(f"empty value for {s['attribute']}")
        done += 1

    updated = apply_decisions_to_contract(contract_data, decisions)
    normalize_contract(updated, str(contract_path))
    new_text = (json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
                if contract_path.suffix.lower() == ".json" else dump_yaml(updated))

    print()
    print(_rule("WRITE PREVIEW"))
    _show_yaml_diff(original_text, new_text, enabled)
    print()
    print(_c(f"{len([d for d in decisions if d.get('action') != 'skip'])} decisions ready to write.",
             "cyan", enabled))

    if args.dry_run:
        print(_c("Dry run: nothing written.", "gray", enabled))
        return 0

    if sha256_text(contract_path.read_text(encoding="utf-8")) != original_hash:
        raise StasriftError("contract changed on disk during review; aborting write")

    print("[1] Write changes   [2] Cancel")
    ans = input("> ").strip().lower()
    if ans not in {"1","y","yes"}:
        print(_c("Nothing written.", "gray", enabled))
        return 0

    if sha256_text(contract_path.read_text(encoding="utf-8")) != original_hash:
        raise StasriftError("contract changed while awaiting approval; aborting write")
    contract_path.write_text(new_text, encoding="utf-8")
    _save_skip_state(args.skip_file, skip_state)
    print(_c(f"Wrote {contract_path}", "green", enabled, bold=True))
    return 0

def cmd_diff(args):
    result = compare_contracts(load_contract(args.old), load_contract(args.new))
    if args.json: print(json.dumps(result, indent=2, sort_keys=True))
    else: print_human(result)
    return 0 if result["verdict"] in {"UNCHANGED", "NARROWED"} else 1



# ---------- v1.0 contract format ----------

CONTRACT_FORMAT = "stasrift-contract-v1"

def _contract_format(data):
    if not isinstance(data, dict):
        return None
    return data.get("stasrift_format")

def _ensure_supported_contract_format(data, source):
    fmt = _contract_format(data)
    if fmt is None:
        return  # legacy v0.x contract, still accepted in rc1
    if fmt != CONTRACT_FORMAT:
        raise StasriftError(
            f"{source}: unsupported stasrift_format '{fmt}', expected '{CONTRACT_FORMAT}'"
        )

# ---------- v0.6 project validation / doctor ----------

def _find_contract_candidates(repo):
    repo = Path(repo)
    out = []
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".yaml", ".yml", ".json"}:
            continue
        try:
            data = load_any(p)
            if not isinstance(data, dict):
                continue
            # Generated evidence/suggestion bundles are artifacts, not contracts.
            if str(data.get("format", "")).startswith("stasrift-evidence-"):
                continue
            if str(data.get("format", "")).startswith("stasrift-suggestions-"):
                continue
            if (
                isinstance(data.get("fields"), list)
                or isinstance(data.get("properties"), list)
                or (isinstance(data.get("schema"), dict) and isinstance(data["schema"].get("properties"), list))
            ):
                out.append(p)
        except Exception:
            continue
    return out


def cmd_contract_schema(args):
    example = {
        "stasrift_format": CONTRACT_FORMAT,
        "fields": [
            {
                "name": "occurred_at",
                "type": "timestamp",
                "sem": {
                    "time_axis": ["event_time"]
                }
            },
            {
                "name": "amount",
                "type": "double",
                "sem": {
                    "unit": ["USD"]
                }
            },
            {
                "name": "discount_pct",
                "nullable": True,
                "sem": {
                    "absent": ["unknown"]
                }
            }
        ]
    }
    if args.json:
        print(json.dumps(example, indent=2, sort_keys=False))
    else:
        print(dump_yaml(example))
    return 0

def cmd_validate(args):
    contract = Path(args.contract)
    data = load_any(contract)
    normalized = normalize_contract(data, str(contract))

    problems = []
    notes = []

    # Ensure declared semantic values are valid by virtue of normalize_contract.
    for field, sem in normalized.items():
        if "time_axis" in sem and not sem["time_axis"]:
            problems.append(f"{field}.time_axis is empty")
        if "unit" in sem and not sem["unit"]:
            problems.append(f"{field}.unit is empty")
        if "absent" in sem and not sem["absent"]:
            problems.append(f"{field}.absent is empty")

    # Flag mixed modes that may be intentional but deserve review.
    for field, sem in normalized.items():
        for attr, vals in sem.items():
            if len(vals) > 1:
                notes.append(f"{field}.{attr} allows {len(vals)} modes: {', '.join(vals)}")

    result = {
        "valid": not problems,
        "fields": len(normalized),
        "problems": problems,
        "notes": notes,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("VALID" if result["valid"] else "INVALID")
        print(f"{result['fields']} fields checked")
        for n in notes:
            print(f"NOTE: {n}")
        for p in problems:
            print(f"ERROR: {p}")

    return 0 if result["valid"] else 2

def cmd_doctor(args):
    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        raise StasriftError(f"repo root does not exist or is not a directory: {repo}")

    candidates = _find_contract_candidates(repo)
    sql_files = sorted(repo.rglob("*.sql"))
    py_files = sorted(repo.rglob("*.py"))

    report = {
        "repo": str(repo),
        "contracts": [str(p.relative_to(repo)) for p in candidates],
        "sql_files": len(sql_files),
        "python_files": len(py_files),
        "ready": bool(candidates),
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("STASRIFT DOCTOR")
        print(f"Repo: {repo}")
        print(f"Contracts found: {len(candidates)}")
        for p in candidates[:10]:
            print(f"  - {p.relative_to(repo)}")
        print(f"SQL files: {len(sql_files)}")
        print(f"Python files: {len(py_files)}")
        if candidates:
            print("Ready: yes")
        else:
            print("Ready: no — no supported contract file found")
            print("Create a YAML/JSON contract with a 'fields:' list.")

    return 0 if candidates else 1

def _demo_paths(root):
    root = Path(root)
    return (
        root / "incident_fixture" / "schema_v1.yaml",
        root / "incident_fixture" / "schema_v2.yaml",
    )

def cmd_demo(args):
    base = Path(args.root).resolve()
    old, new = _demo_paths(base)
    if not old.exists() or not new.exists():
        raise StasriftError("incident fixture missing")
    old_data, new_data = load_any(old), load_any(new)
    normalize_contract(old_data, str(old))
    normalize_contract(new_data, str(new))
    old_shape = {f["name"]: f.get("type") for f in old_data["fields"]}
    new_shape = {f["name"]: f.get("type") for f in new_data["fields"]}
    print("BASELINE SHAPE CHECK")
    print("PASS: field names and physical types unchanged" if old_shape == new_shape
          else "FAIL: structural schema changed")
    print()
    print("STASRIFT")
    result = compare_contracts(load_contract(old), load_contract(new))
    print_human(result)
    return 1 if old_shape != new_shape or result["verdict"] in {"WIDENED", "INCOMPATIBLE"} else 0

def build_parser():
    p = argparse.ArgumentParser(prog="stasrift",
        description="Check whether declared data meaning stays compatible across versions.")
    p.add_argument("--version", action="version", version="stasrift 1.0.1")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("diff", help="compare two semantic contracts")
    d.add_argument("--old", required=True)
    d.add_argument("--new", required=True)
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("scan", help="gather deterministic local evidence")
    s.add_argument("--repo", default=".")
    s.add_argument("--contract", required=True)
    s.add_argument("--out", default=".semcheck/evidence.json")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    g = sub.add_parser("suggest", help="turn evidence into proposals/conflicts")
    g.add_argument("--evidence", required=True)
    g.add_argument("--out", default=".semcheck/suggestions.json")
    g.add_argument("--skip-file", default=".semcheck/skipped.json")
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_suggest)

    r = sub.add_parser("review", help="human review, diff preview, explicit write")
    r.add_argument("--suggestions", required=True)
    r.add_argument("--contract", required=True)
    r.add_argument("--skip-file", default=".semcheck/skipped.json")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-color", action="store_true")
    r.set_defaults(func=cmd_review)

    cs = sub.add_parser("contract-schema", help="print the canonical v1 contract example")
    cs.add_argument("--json", action="store_true")
    cs.set_defaults(func=cmd_contract_schema)

    v = sub.add_parser("validate", help="validate one semantic contract")
    v.add_argument("--contract", required=True)
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_validate)

    doc = sub.add_parser("doctor", help="inspect a repo for Stasrift readiness")
    doc.add_argument("--repo", default=".")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=cmd_doctor)

    demo = sub.add_parser("demo", help="run the built-in incident proof")
    demo.add_argument("--root", default=".")
    demo.set_defaults(func=cmd_demo)

    return p

def main():
    # Piped Windows output may use a legacy encoding. Escape unsupported glyphs
    # instead of failing a valid command; UTF-8 output is unchanged.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    p = build_parser()
    args = p.parse_args()
    try:
        # ensure parent output dirs
        for attr in ("out",):
            if hasattr(args, attr):
                Path(getattr(args, attr)).parent.mkdir(parents=True, exist_ok=True)
        return args.func(args)
    except (StasriftError, OSError, UnicodeError, EOFError, RecursionError) as e:
        print(f"stasrift: error: {e}", file=sys.stderr)
        return 2

