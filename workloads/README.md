# workloads

gavel's EC pool workloads. gavel is an independent repository: under EC POLICY
`independent-repos`, EC runs one of these only after Nelson approved its
declaration entry (by the sha256 of the entry's canonical JSON), only at an
exact commit, and each run is EC's own dispatch. Tests, the judge and every
other engine load run only on the EC pool, never on the work machines
LAPTOP-01AGNPJU and LAPTOP-16NUA5I8 (decision D2(A), 2026-10-15); every script
here refuses to run on them.

**[Note 2026-10-15]** For gavel on LAPTOP-01AGNPJU, D2(A)'s venue part is
superseded by EC POLICY `gavel-pju-execution` (see AGENTS.md and
docs/DECISIONS.md). The scripts here are the EC pool route; they still refuse
to run on the work machines and are not the PJU route.

| Path | What |
|---|---|
| `../ec-workloads.json` | The declaration EC reads. It holds only `gavel-verify`. |
| `gavel_verify/` | `gavel-verify`: model-free tests, receipt verification and round-2 re-evaluation. Approval packet: `docs/proposals/gavel-verify-approval-packet.md`. |
| `ec-workloads.drafts.json` | DRAFTS, not for approval: `judge-host-prepare`, `judge-smoke`, `gavel-exam`. Same format as the declaration, but not at the repository root, so EC cannot register it as a declaration. An entry moves to `../ec-workloads.json` only after Nelson names the pool host and the scope, and approves the final entry. |
| `judge_common.py` | Shared draft code: the host gate (`NAMED_HOST` blank refuses), the Ollama pins (`<TO-PIN>` refuses), the cache layout and the private Ollama server. |
| `judge_host_prepare/` | Draft: pinned portable Ollama and the two approved model digests in the named host's workload cache; hardware readout; no judgment. |
| `judge_smoke/` | Draft: the synthetic smoke cases, primary arm, three runs each: timing, determinism, truncation. |
| `gavel_exam/` | Draft: one locked round-3 paper, once, with `gavel exam --manifest`; local arms only. |

EC starts the entry script with the pool generation's Python
(`python -E -s -B <entry>`, working directory = the checkout) and these
variables: `EC_WORKLOAD_REPOSITORY`, `EC_WORKLOAD_NAME`, `EC_WORKLOAD_SHA`,
`EC_WORKLOAD_SOURCE` (the checkout), `EC_WORKLOAD_OUT` (published as a private
receipt ref; `SUMMARY.md` there becomes the check-run text), `EC_WORKLOAD_WORK`
(scratch), `EC_WORKLOAD_PARAMETERS` (a JSON file), `EC_WORKLOAD_MODE`, and
`EC_WORKLOAD_CACHE` only when the entry declares `"cache": true`. The job
carries no token. See EC `tools/pool/workload.py`.
