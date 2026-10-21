STASRIFT 1.0.1 — REPRODUCIBLE DEMONSTRATION
Prepared October 20, 2026 for Jameson Green's Phase 3 recognition campaign.
Public reproduction package. Download and extract the ZIP before running commands.

THE RESULT
A timestamp can retain its field name and physical type while its declared
meaning changes from when an event occurred to when a system processed it.
The simple shape baseline sees no difference. Stasrift reports INCOMPATIBLE.
This checks declared meaning; it does not discover or certify real-world truth.

OBSERVED CASES — ALL NINE EXPECTATIONS MET
1. Version command identifies stasrift 1.0.1 (exit 0).
2. Well-formed contract validates (exit 0).
3. Identical declarations: UNCHANGED (exit 0).
4. Same timestamp type; event_time to processing_time: INCOMPATIBLE (exit 1).
5. Add another permitted time-axis value: WIDENED (exit 1).
6. Remove that additional permitted value: NARROWED (exit 0).
7. Change only physical type: UNCHANGED (exit 0). A demonstrated limitation.
8. Empty contract accepted (exit 0). Another demonstrated limitation.
9. Malformed JSON rejected (exit 2).
Exit 1 in cases 4 and 5 is the intended result, not a crashed demonstration.
Cases and stdout/stderr are preserved in observed-results.json.

HOW TO REPEAT
Requires Python 3.10+ and PyYAML 6+. No paid service or account required.
From this folder, run:
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install PyYAML==6.0.3
  .venv\Scripts\python.exe run_demo.py
On Linux/macOS replace .venv\Scripts\python.exe with .venv/bin/python.
Dependency installation can require network access. The demonstration itself
uses local files. It writes inputs/ and observed-results.json in this folder.
To keep the original captured record, copy the folder before rerunning.
Alternatively use an existing environment with the required dependency.

THIS RUN
Windows, bundled Python 3.12.14, PyYAML 6.0.3. This is a source-based CLI run,
not a fresh wheel-install or complete release test-suite certification.
The bundled runtime lacked PyYAML. A compatible Windows wheel was obtained
from official PyPI and extracted under workspace work/stasrift-deps after
the restricted installation environment blocked a normal dependency install.
No machine-wide installation or paid resource used. Readers may install it
normally in their own virtual environment. No private contracts were scanned.

SOURCE AND INTEGRITY
Official release: https://github.com/arkosom/stasrift/releases/tag/v1.0.1
Tag commit: ceeadec43a69790e6fa3dc11738892841add69b2
Official source archive URL:
https://github.com/arkosom/stasrift/releases/download/v1.0.1/stasrift-1.0.1-source.zip
Observed SHA256:
9cf9877c7b346f36ba0eb26bcadb0b6ad3fc0b90cc095f15ae07f5722110c3f9
Matched the digest returned by GitHub's release asset metadata.
Bundled stasrift-1.0.1 is extracted official release source; no code modified.
Apache-2.0 license and NOTICE are retained in that directory.
run_demo.py and its generated JSON contracts are demonstration additions,
not changes to the released product. Archive integrity is not proof of safety,
external validation or independent adoption.

WHAT THIS DOES NOT ESTABLISH
No comparison against all schema validators or competing products was made.
No business benefit, customer adoption, performance advantage or novel scientific
result has been demonstrated. The shape baseline compares names and types only.
The checker compares supported declarations; omitted or incorrect declarations
can leave meaning unexamined. Physical types need another check. This small
demonstration does not exercise every scanner, review workflow or SQL feature.
The release documents heuristic SQL coverage and human review requirements.
No external scholarly or reviewer endorsement is implied by this agent-run test.

PUBLIC DEMONSTRATION SCRIPT
Read the old timestamp declaration. Show the processing-time declaration.
Point out that the name and type have not changed. Show the incompatible verdict.
Then show the physical-type-only case returning unchanged and explain the limit.
Invite a reader to rerun the exact script and report a smallest reproducible
counterexample through the public repository's issue process. Do not submit
private customer contracts or assume an UNCHANGED verdict is certification.

PHASE 3 STATUS
Stasrift demonstration prepared and locally reproduced. Independent
reproduction, SNR scholarly-feedback work, a second essay and no-fee opportunity
research remain separate unfinished Phase 3 work. No fees incurred.
