# Stasrift v1.0.1

Maintenance release under ARKOSOM LLC. The frozen v1 schema, CLI commands/options, verdicts, and offline runtime model remain unchanged. Python 3.10 and 3.12 on native Windows and Linux are release verification targets; publication waits for all four jobs to pass.

## Corrections

- Complete Apache-2.0 license and copyright notice.
- Fail safely on malformed YAML/JSON, duplicate explicit keys, invalid UTF-8, non-finite JSON values, and malformed review bundles.
- Refuse unsupported currency assumptions from cents/dollars names; preserve explicit USD evidence for human review.
- Ignore SQL comments/literals and conservatively refuse ambiguous JOIN/UNION lineage.
- Check stale contracts and human review decisions; preserve JSON contracts and update identical repeated declarations consistently.
- Keep dry runs, cancellations, and paused reviews free of contract/skip-state writes.
- Preserve YAML merge precedence; correct editable-install wrapper imports and limited console encodings.
- Verify demo shape results, shell line endings, quickstart exit handling, and public artifact membership.
- Cover 91 regression/adversarial/compatibility tests and isolated wheel/sdist installations.

## Migration boundaries

Complete backward compatibility is **not** claimed. Conflicting declarations with the same field name now fail instead of silently using the last entry. The frozen schema does not enforce name uniqueness, so some previously schema-valid contracts require reconciliation into one unambiguous field. Exact identical repeated declarations remain accepted.

Unsupported keys inside semantic declarations now fail instead of being silently discarded. Correct misspellings or move unsupported annotations into separate metadata. Supported attributes remain `time_axis`, `unit`, and `absent`.

Canonical v1 semantic values must be arrays, with unique values and schema-valid nullable/semantic structures. Legacy scalar semantics without a format marker remain supported. YAML merge defaults and explicit overrides retain normal precedence.

Before upgrading, validate contracts and compare important workflows using sanitized copies. No external customer-contract corpus was available for compatibility verification.

## Installation and integrity

Download the wheel and SHA256SUMS-1.0.1.txt from the official GitHub release:
https://github.com/arkosom/stasrift/releases/tag/v1.0.1

```bash
python -m venv .venv
# Activate: source .venv/bin/activate (Linux/macOS)
# Windows Command Prompt: .venv\Scripts\activate.bat
python -m pip install ./stasrift-1.0.1-py3-none-any.whl
stasrift --version
```

Expected: `stasrift 1.0.1`. PyYAML is the runtime dependency. Installation may need network access; analysis works locally. Stasrift is not published to PyPI.

On Linux use `sha256sum -c SHA256SUMS-1.0.1.txt` with all three assets present. On Windows compare `Get-FileHash -Algorithm SHA256` results with the manifest. Checksums establish integrity relative to the manifest, not signed authenticity.

## Limitations

`UNCHANGED` compares supported declarations; it does not certify implementation, missing assumptions, physical type compatibility, or all business meanings. SQL analysis is heuristic and can miss unsupported transformations. JOIN/UNION refusal limits coverage. Suggestions require human evidence and approval. Editable evidence bundles are not authenticated. Empty contracts remain valid under the frozen schema.

The original v1.0.0 release is preserved. Public distributions exclude internal verification logs, reports, and maintenance evidence.
