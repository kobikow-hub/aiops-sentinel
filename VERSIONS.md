# VERSIONS.md — the official rule files and their provenance

Per guide Part 15: grammar, policies, rules and safety rules are saved in versions,
each with an owner, a source and a date, and marked as *rule* or an *assumption*.
Every change to any of these files must be released together and re-tested (P17).

| File | What it is | Kind | Source | Owner | Copied | Version |
|---|---|---|---|---|---|---|
| `sentinel/dsl/remediation.ebnf` | The DSL grammar — GATE 1 (recognition, checked at T3/T4) | rule | Simple Guide Part 5.1 (pages 10–11) | Danny & Kobi | 2026-09-19 | guide v4+v5 |
| `policy/sentinel/authz.rego` | OPA rules: permission (T5/T6), route (T13/T14), approval check (T15), Advisor | rule | Simple Guide Part 10.1 (pages 25–26) | Danny & Kobi | 2026-09-19 | guide v4+v5 |
| `rules/topology.dl` | Datalog spec: context, blast radius, secret flows, veto, Advisor gaps | rule | Simple Guide Part 10.2 (pages 28–29) | Danny & Kobi | 2026-09-19 | guide v4+v5 |
| `rules/remediation.pl` | Prolog: permission, risk (the ONLY risk authority), reasons for NO | rule | Simple Guide Part 10.3 (pages 30–31) | Danny & Kobi | 2026-09-19 | guide v4+v5 |
| `audit/trace.schema` | Diary format + the closed list of event names (validated by P12) | rule | Simple Guide Part 13.1 (page 38) | Danny & Kobi | 2026-09-19 | guide v4+v5 |

## Engines these files run on

| Engine | Version | Where |
|---|---|---|
| OPA (Rego v1) | 1.20.2 | `tools/opa.exe` |
| SWI-Prolog | 10.0.2 (x64-win64) | `C:\Program Files\swipl\bin\swipl.exe` |
| z3-solver (Python) | 5.1.0 | `.venv` |
| lark (Python) | 1.3.1 | `.venv` |
| python-statemachine | 3.2.1 | `.venv` |
| pytest | 9.1.1 | `.venv` |

## Notes / assumptions

- `rules/topology.dl` is the **official spec**; the runtime implementation will be a plain
  Python module (`sentinel/checkers/datalog.py`, step P2.2) that must mirror it exactly —
  the Soufflé engine has no native Windows build (decision recorded in the development plan).
- Any new action word enters `remediation.ebnf` only through a reviewed, versioned release,
  never automatically (guide Part 5.5).
