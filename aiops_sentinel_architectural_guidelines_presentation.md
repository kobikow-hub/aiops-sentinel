# AIOps Sentinel: Architectural Guidelines & System Doctrine

### *Speed Without Catastrophe: Deterministic Safety, Governance & Mathematical Proof for Autonomous Operations*

---

## Slide 1: Executive Thesis — The Sentinel Doctrine

### The Core Conviction: Structure Over Intelligence

#### The Problem: The Danger of Autonomous AI
* **Unbounded Intelligence:** Operations teams need the rapid analysis and speed of AI to triage production incidents, but handing raw infrastructure keys (SSH, Cloud APIs, K8s credentials) to an LLM creates an unacceptable corporate risk.
* **The Fundamental Fallacy:** An AI's intelligence can never be trusted to evaluate its own safety. An LLM optimizes for plausibility, coherence, and satisfaction—not formal correctness or policy enforcement.

#### The Sentinel Thesis
* **Structure Is the Safety Mechanism:** We do not constrain AI by asking it politely in natural language prompts; we build rigid, mathematical, and unbypassable computational cages around it.
* **The Core Formula:**
  
  $$\text{Chaotic AI Proposal} \xrightarrow{\text{Gate 1 (EBNF)}} \text{Formal Multi-Engine Verification} \xrightarrow{\text{Live Z3 Math}} \text{Judgment-Free Execution}$$

#### Core Architecture Spec Files
* `dsl/remediation.ebnf` — The immutable Domain-Specific Language grammar.
* `audit/trace.schema` — Formal JSON Schema for the immutable append-only audit diary.

> **Speaker Note / Analogy:**  
> "Think of an autonomous LLM as a brilliant intern who knows every programming book by heart but has zero impulse control. You want their fast reading ability and incident suggestions, but you never give them the master key to the data center. Instead, they write an order slip on a tiny pre-printed form, and four separate inspectors and a site engineer verify the math before anyone turns a wrench."

---

## Slide 2: The Overarching Map — The Whole System in One Breath

### A Rigid, Forward-Only Assembly Line

```
 ┌──────────────┐     ┌──────────────┐     ┌────────────────────────────────────────────────────────┐
 │ 1. INTAKE    │     │ GATE 1       │     │ 2. THE FOUR INDEPENDENT GUARDS                         │
 │ Alert Intake │ ──► │ Syntax EBNF  │ ──► │ OPA (Policy) ──► Datalog (Blast) ──► Prolog (Risk)    │
 │ Redactor L11 │     │ Type Check   │     │                    │                                   │
 └──────────────┘     └──────────────┘     └────────────────────┼───────────────┬───────────────────┘
                                                                │               │
                                              ┌─────────────────┘               ▼
                                              │                       LTL (Temporal History)
                                              ▼                                 │
                            ┌──────────────────────────────────┐                │
                            │ 3. DECIDING (Arbiter + OPA)      │ ◄──────────────┘
                            │ Low Risk  ──► Autonomous Route   │
                            │ High Risk ──► Signed 1-Time Slip │
                            └─────────────────┬────────────────┘
                                              │
                                              ▼
                            ┌──────────────────────────────────┐
                            │ 4. DEPLOYING (Live Invariants)   │
                            │ Z3 Solver (Live Snapshot Math)   │
                            │ Tool Gateway (Zero-Opinion Actor)│
                            └─────────────────┬────────────────┘
                                              │
                                              ▼
                            ┌──────────────────────────────────┐
                            │ 5. VERIFY & CLOSE                │
                            │ Live Health SLI Probe ──► Diary  │
                            └──────────────────────────────────┘
```

#### Architectural Tenets
* **Fixed Sequence:** The order of the security guards never changes: $\text{Intake} \rightarrow \text{Gate 1} \rightarrow \text{OPA} \rightarrow \text{Datalog} \rightarrow \text{Prolog} \rightarrow \text{LTL} \rightarrow \text{Arbiter} \rightarrow \text{Z3} \rightarrow \text{Gateway}$.
* **Forward Fact Flow:** Facts flow forward only. No guard ever consults or awaits a verdict from a later component.
* **Governing Game Board:** The state machine (`board/`) enforces all 18 states and 30 moves ($T1\text{–}T30$). Illegal shortcuts are structurally impossible to express.

> **Speaker Note / Analogy:**  
> "Think of processing a municipal building permit. The architect submits plans. Zoning (OPA), structural engineering (Datalog), and the magistrate (Prolog) review in strict order. Right before pouring the concrete, a surveyor (Z3) inspects the actual dirt on-site. Only then does the bulldozer operator (the Gateway) turn the key."

---

## Slide 3: Doctrine 1 & 2 — The AI Only Suggests & Gate 1 Filters

### Phase 1: Bounding the Uncredentialed AI

#### Doctrine #1: The AI Only Suggests
* The LLM holds **zero credentials** and zero infrastructure access.
* The LLM writes **evidence awaiting judgment**, not executable commands or direct API payloads.
* The LLM outputs proposals strictly in a micro-DSL defined by `dsl/remediation.ebnf`.
* The LLM **never emits state machine events** and cannot move the system's state.

#### Doctrine #2: Gate 1 Before Everything
* A syntax parser (`lark`) and type checker (`typecheck.py`) sit directly between the AI and all four checkers.
* **Grounding Check:** Every target entity name must exist in the live infrastructure map snapshot (`system_map.py`). Hallucinations fail immediately.
* **Dangerous Verbs Flagged:** Verbs like `drop_table` or `rm_rf` are recognized by grammar as invalid remediation verbs and routed to recovery. *Known is not the same as allowed.*
* **Cryptographic Action Hash:** Gate 1 calculates an immutable SHA-256 fingerprint ($action\_hash$) binding all future checks, approvals, and logs to this exact text.

```
       Incoming Alert ──► [ Redactor (Rule L11) ] ──► Clean Alert ──► [ MockLLM / DSL Form ]
                                                                             │
                                                                       Raw Proposal
                                                                             │
                                                                             ▼
 [ Phase 2 Checkers ] ◄── Valid Proposal + action_hash ◄── [ GATE 1: Parser + Type Check ]
                                                                             │
                                                                         Invalid
                                                                             ▼
                                                                  [ Phase 5: Recovery ]
```

#### Code Artifacts
* `sentinel/intake/alerts.py` (Move $T1$)
* `sentinel/intake/redactor.py` (Move $T2$, Rule L11 secret scrubber)
* `sentinel/intake/llm.py` (MockLLM / Prompt Interface)
* `sentinel/dsl/parser.py` & `sentinel/dsl/typecheck.py` (Moves $T3/T4$)
* `sentinel/dsl/fingerprint.py` (Cryptographic $action\_hash$)

> **Speaker Note / Analogy:**  
> "Gate 1 is the restaurant bouncer checking the printed menu. Even if a customer speaks perfect grammatical English, if they order a spaceship, the waiter immediately rejects it. A sentence must be both syntactically valid and grounded in our actual pantry before the kitchen ever starts cooking."

---

## Slide 4: Doctrine 3 & 4 — The Four Independent Checkers

### Phase 2: Forward Inspection & One Boss Per Topic

#### The Four Independent Guards
| Checker | Engine / Implementation | Role & Responsibilities | Analogy |
| :--- | :--- | :--- | :--- |
| **OPA** | `tools/opa.exe` & `authz.rego` | Enforces corporate policy: banned action verbs, active change freezes, maintenance windows. **Fails Closed (Move $T30$).** | The School Rulebook (*"No running in hallways"*) |
| **Datalog** | `sentinel/checkers/datalog.py` (`rules/topology.dl`) | Traverses dependency graph chains ($affected\_by$). Issues a **Hard Veto** if $\ge 10$ services break or if secret data flows into public tiers. | The Domino Expert (*"If you touch this, 40 fall"*) |
| **Prolog** | SWI-Prolog (`rules/remediation.pl`) | **THE SOLE RISK AUTHORITY.** Evaluates facts against 8 strict rules to determine `risk_level(low | high)` with an explicit written proof chain. | The Courtroom Judge (*"Sentence with full written record"*) |
| **LTL** | `ltl/check.py` & `ltl/rules.py` | Linear Temporal Logic enforcing chronological ordering across rules $L1\text{–}L15$. Prevents borrowed approvals. | The Project Manager (*"Wash hands before eating"*) |

#### Doctrine #4: One Boss Per Topic
* **Prolog is the ONLY component that computes risk.**
* Datalog reports blast radius counts and dependency paths, but holds no opinion on risk.
* OPA maps Prolog's calculated risk to a workflow route, but never recalculates risk.
* **Architectural Invariant:** Two components must never possess the capability to disagree on the same question. We structurally eliminate disagreement by removing overlapping responsibilities.

> **Speaker Note / Analogy:**  
> "If two people in an operating room have the authority to decide if the patient is allergic, sooner or later they will contradict each other. In Sentinel, the lab technician (Datalog) counts the antibodies. The chief doctor (Prolog) reads that number and decides the risk level. The hospital coordinator (OPA) reads the doctor's chart to assign the room. One boss per topic."

---

## Slide 5: Deep Dive — Prolog as the Sole Risk Authority

### Eliminating Subjectivity with Mathematical Proof Chains

```
  INPUT FACTS HANDED TO PROLOG:
  ├── action(restart_pod, web_frontend)
  ├── confidence(0.85)
  ├── sensitive_target(false)            <-- from Datalog
  ├── critical_in_blast(false)           <-- from Datalog
  └── blast_radius_count(2)              <-- from Datalog
               │
               ▼
   [ SWI-Prolog Engine (rules/remediation.pl) ]
               │
   8 INVARIANT RISK RULES EVALUATED:
   1. Target is stateful database?
   2. Target marked production-critical?
   3. Target stores sensitive/PCI data?
   4. Critical service located in blast radius?
   5. Action is database rollback/drop?
   6. AI confidence interval < 0.60?
   7. Target had past human rejection?
   8. Target is currently frozen?
               │
               ├───────────────────────────────────────────┐
               ▼                                           ▼
      All Rules Pass:                             Any Rule Triggers:
      • risk_level = low                          • risk_level = high
      • allowed = true                            • proof: why_refused = [...]
```

#### Written Proof Requirement (Doctrine #12)
* Prolog never returns a bare "no". It returns the exact predicate chain:
  `why_refused = [critical_service_in_blast(master_db), blast_radius_exceeded(40, 10)]`
* The state machine passes this raw proof chain directly to the human engineer and immutable diary. AI is never allowed to summarize or invent explanations after the fact.

#### Code Artifacts
* `rules/remediation.pl` (Official Prolog Rulebook)
* `sentinel/checkers/prolog_adapter.py` (SWI-Prolog subprocess interface - Moves $T9/T10$)
* `tests/test_prolog.py` (Verification test harness)

---

## Slide 6: Doctrine 6 — Human-in-the-Loop Done Right

### Phase 3: Routing, One-Time Permission Tokens & SLA Timers

#### The Arbiter Router (Moves $T13/T14$)
* Reads Prolog's `risk_level` and consults OPA route policy:
  * `risk_level(low)` $\longrightarrow$ Routes autonomously to `Constraint_Check` (Z3).
  * `risk_level(high)` $\longrightarrow$ Routes to `Human_Approval_Required`.
  * `risk_level(missing | unknown)` $\longrightarrow$ **Fails safe:** Defaults to `Human_Approval_Required`.

#### Doctrine #6: One-Time Action-Bound Tokens
* **No Blanket Admin Passes:** Approvals are cryptographically bound to the unique $action\_hash$. A permission slip for `restart_pod(auth)` cannot be recycled for `restart_pod(db)`.
* **Four-Point Token Guardrails (`sentinel/decide/approval.py`):**
  1. **Role Check:** Must belong to `sre` or `admin` role (validated by OPA).
  2. **Fingerprint Match:** Token hash must match current proposal's $action\_hash$ byte-for-byte.
  3. **Freshness:** Strict expiration window (e.g., 15 minutes).
  4. **Single-Use Enforcement:** Token is consumed and burned upon gateway receipt.

#### The SLA Watchdog (Move $T17$)
* **Silence is Never Consent:** A system waiting for human review must never stall indefinitely.
* When the SLA timer expires, the state machine triggers `approval_timeout` (Rule L4) and moves directly to `Escalated`. An on-call human becomes the incident owner.

```
       [ Prolog Risk Level ]
                 │
                 ▼
        [ Arbiter (OPA) ]
                 │
        ─────────┴─────────
       │                   │
  (Low Risk)          (High Risk)
       │                   │
       ▼                   ▼
 [ Phase 4: Z3 ]    [ Human Approval Screen ] ──► (SLA Timeout) ──► [ Escalated ]
                           │
                     (Valid Token)
                           │
                           ▼
                    [ Phase 4: Z3 ]
```

> **Speaker Note / Analogy:**  
> "A parental permission slip allows a child to go on the zoo field trip on Tuesday. You cannot use that same slip to go to the waterpark, you cannot photocopy it for a friend, and it is completely invalid next week."

---

## Slide 7: Doctrine 7 & 8 — Live Math & Paranoid Gateway

### Phase 4: Mathematical Solvers & Separation of Powers

#### Doctrine #7: The Last Gate Runs on Live Data (Moves $T18/T19$)
* **Z3 Constraint Solver (`constraints/deployment_gate.py`):** Runs *last*, immediately before execution, after all decisions and human approvals.
* **Why? The World Drifts:** If an SRE approves an action at 2:00 PM, and clicks submit at 2:15 PM, other pods may have died in the interim.
* **Live Invariant Check:**
  
  $$\text{Pre-Condition}(\text{Live Snapshot}) \wedge \text{Action Effect}(\text{Spec Rules}) \implies \text{Post-Condition}(\text{Invariants})$$

* **Math Overrides Humans:** If Z3 computes `unsat` (e.g., $N - 1 < \text{min\_capacity}$), the deployment is **Blocked immediately**. Mathematical truth outranks an executive's permission slip.

#### Doctrine #8: The Paranoid, Judgment-Free Gateway (Moves $T20\text{–}T22$)
* **Keys and Judgment Never Live Together:** The Tool Gateway (`gateway/tool_gateway.py`) is the **only** component with root infrastructure credentials. It possesses **zero risk logic and zero opinions**.
* **Three Gateway Guardrails:**
  1. **Compare-and-Execute:** Re-reads the infrastructure snapshot version. If the live version changed between Z3's check and execution, it refuses ($stale\_snapshot$).
  2. **Idempotency Key:** Records executed $action\_hash$ in a local ledger. Never executes the exact same proposal twice.
  3. **Reconcile-on-Timeout:** A network timeout is missing information, not a failure. The Gateway polls the target system for state before declaring failure.

```
 [ Approved Proposal ] ──► [ Z3 Solver ] ──( sat )──► [ Tool Gateway ] ──► [ Production Infrastructure ]
                                │                            │
                             ( unsat )                  ( Version Stale )
                                │                            │
                                ▼                            ▼
                          [ Blocked ]                   [ Recovery ]
```

> **Speaker Note / Analogy:**  
> "You ask your parents at 2:00 PM if you can ride your bicycle, and they say yes. At 4:00 PM you walk out the door. You still look out the window to see if it is pouring rain. Z3 is that final look out the window. And the Gateway is the armored car driver: he has the keys, but he only drives if the signed manifests match the exact millisecond invoice."

---

## Slide 8: Doctrine 10 & 11 — Verification, Recovery & Audit

### Phase 5: Closing the Loop and the Immutable Diary

#### Doctrine #11: Verify Outcomes, Not Actions (Moves $T23/T24$)
* Running an automated command without error does not mean the system is healthy:
  
  $$\text{Action Succeeded} \neq \text{Incident Resolved}$$

* Post-execution, the Health Probe (`sentinel/verify/probe.py`) samples live telemetry (SLIs: HTTP 500 error rates, CPU latency, queue depths).
* Only when metrics recover does the system transition toward `Incident_Resolved`.

#### Doctrine #10: Bounded Recovery with Lessons (Moves $T25/T26$)
* If execution fails or metrics remain degraded, the incident enters `Recovery`.
* **Bounded Retries:** Strictly capped at **maximum 2 retries**.
* **Mandatory Counterexample:** Every retry payload carries the exact structured failure telemetry into the LLM prompt.
* **Full Gauntlet Re-Entry:** A retry generates a brand-new proposal with a new $action\_hash$ that must pass Gate 1, OPA, Datalog, Prolog, LTL, and Z3 from scratch.
* **Structural Lock:** A checker's **NO is NEVER retried**. Policy blocks enter `Blocked` $\rightarrow$ `Escalated`.

#### Doctrine #12: The Append-Only Diary (Move $T29$)
* `audit/audit_service.py` writes every state transition, actor, timestamp, and proof chain to an immutable JSONL ledger adhering to `audit/trace.schema`.
* **Gate to Completion (Rule L7):** `Incident_Resolved` cannot be reached directly from execution. The audit service must formally verify that the complete diary satisfies all temporal formulas $L1\text{–}L15$.

```
 [ Execution Done ] ──► [ Health Probe ] ────( Metrics Healthy )────► [ Append-Only Diary ] ──► [ Resolved ]
                              │                                              ▲
                     ( Metrics Degraded )                                    │
                              │                                        ( Human Fix )
                              ▼                                              │
                      [ Recovery Loop ] ──( Exhausted / Checker NO )──► [ Escalated ]
```

---

## Slide 9: Doctrine 5 — The State Machine is the Only Boss

### 18 Explicit States, 30 Guarded Transitions

```
 [ Awaiting_Alert ] ────(T1)────► [ Alert_Parsed ] ────(T2)────► [ Context_Collected ]
                                                                        │ (T3)
                                                                        ▼
 [ Temporal_Checked ] ◄───(T11)─── [ Logic_Judged ] ◄───(T9)─── [ AI_Analysis (DSL) ]
         │ (T12)                         │                             │ (T4)
         ▼                               ▼ (T10 - veto)                ▼
 [ Route_Decided ]               [ State: Blocked ]            [ Gate 1 Parsing ]
    │ (T13: low)    │ (T14: high)        ▲
    ▼               ▼                    │ (T19: unsat)
 [ Live_Snapshot ] [ Human_Approval ]    │
    │ (T18: sat)            │ (T15)      │
    ▼                       ▼            │
 [ Executing ] ◄────────── [ Approved ]  │
    │ (T20)                              │
    ▼                                    │
 [ Verifying ] ────(T24: degraded)────► [ Recovery ] ──(Cap Exhausted)──► [ Escalated ]
    │ (T23: healthy)
    ▼
 [ Audited ] ────(T29: diary valid)────► [ Incident_Resolved ]
```

#### Structural Governance Principles
* Built on `python-statemachine` (`board/state_machine.py`).
* **Components Emit Events Only:** Components have no direct references to one another. `parser.py` emits `llm_action_proposed`; the board verifies transition $T4$ and advances the game piece.
* **Shortcuts are Structurally Impossible:** There is no transition from `Alert_Parsed` directly to `Executing`. If an adversarial injection attempts an execution shortcut, the state machine raises an unhandled transition exception.
* **Unreachable States are Load-Time Bugs:** The entire directed graph is statically analyzed during CI/CD test execution (`tests/test_board.py`).

---

## Slide 10: Instructor Checkpoints & Test Matrix

### Verifying the Architectural Doctrine

#### The Four Mandatory Checkpoints
| Checkpoint | Architectural Requirement | Verification Mechanism |
| :--- | :--- | :--- |
| **(a) Gate 1 First** | The Lark DSL parser + type checker stands BEFORE all checkers. No unparsed text reaches OPA or Datalog. | `tests/test_dsl_gate.py` (Test P15) verifies syntax and grounding rejection. |
| **(b) One Risk Authority** | Prolog is the ONLY component calculating risk. OPA, Datalog, and Z3 never calculate risk levels. | `tests/test_prolog.py` (Test P17) verifies SWI-Prolog produces explicit proof trees. |
| **(c) Route Mapping** | OPA reads Prolog's risk level and maps it to a workflow route; it never re-evaluates risk. | `tests/test_routing.py` (Test P3) validates route branching and fail-safe defaults. |
| **(d) Z3 on Live Data** | Z3 runs LAST in the Deploying phase on fresh snapshots, never early in Checking. Math overrides human approval. | `tests/test_z3_gate.py` (Test P10/P14) verifies `unsat` blocks deployment. |

#### The Three Core Class Demo Stories
1. **Story 1: The Autonomous Happy Road**
   * Alert arrives $\rightarrow$ AI suggests `restart_pod(web_frontend)` $\rightarrow$ 4 Guards approve $\rightarrow$ Prolog marks `low_risk` $\rightarrow$ Arbiter routes autonomous $\rightarrow$ Z3 proves $sat$ $\rightarrow$ Gateway executes $\rightarrow$ Probes confirm healthy $\rightarrow$ Diary verified $\rightarrow$ Closed.
2. **Story 2: The Topology Veto**
   * Alert arrives $\rightarrow$ AI suggests `restart_pod(master_db)` $\rightarrow$ OPA passes $\rightarrow$ Datalog calculates 40 dependent services (limit 10) $\rightarrow$ Prolog marks `high_risk` / `prolog_forbidden` $\rightarrow$ Pipeline halts at `Blocked` $\rightarrow$ Escalation notifier alerts SRE with checker proofs. Zero production changes occur.
3. **Story 3: Out-of-Order Execution Blocked**
   * Malicious payload attempts to call execution immediately following AI suggestion $\rightarrow$ State machine and LTL engine detect illegal shortcut ($L1$ rule violation) $\rightarrow$ Execution fails closed.

---

## Slide 11: Summary — The Architectural Scorecard

### The Paradigm Shift in Autonomous Engineering

```
 ┌──────────────────────────────────────┬──────────────────────────────────────┐
 │       THE BRITTLE AI APPROACH        │      THE SENTINEL ARCHITECTURE       │
 ├──────────────────────────────────────┼──────────────────────────────────────┤
 │ Natural language prompt guardrails   │ Formal EBNF grammar compiler (Gate 1)│
 │ AI self-evaluates safety & confidence│ Independent formal checkers (OPA/DL) │
 │ Multiple components calculate risk   │ Single Risk Authority (Prolog)       │
 │ Blanket human admin credentials      │ One-time, action-bound token slips   │
 │ Verification based on stale intake   │ Live snapshot math at execution (Z3) │
 │ Unbounded script execution retries   │ Bounded recovery with counterexamples│
 │ Ephemeral or AI-summarized logs      │ Immutable, LTL-checked JSONL ledger  │
 └──────────────────────────────────────┴──────────────────────────────────────┘
```

#### Final Architectural Takeaway
> **"An AI system is only as safe as the mathematical and structural invariants that govern its execution. In AIOps Sentinel, the AI is the eager apprentice who drafts suggestions, the state machine is the unyielding law, and mathematics is the ultimate gatekeeper."**