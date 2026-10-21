"""
generate_dev_plan.py
====================
Builds "AIOps_Sentinel_Development_Plan.pdf" — the step-by-step,
phase-based development plan for the AIOps Sentinel project,
written for Danny & Kobi (AI Architects in training).

How this script is organized (so you can read it too!):
  1. FONTS      — we try to load Calibri (a Windows font that knows
                  special symbols like the arrow ->). If that fails,
                  we fall back to a built-in font and plain ASCII text.
  2. PlanPDF    — a small helper class that knows how to draw the
                  pieces of our document: headings, yellow "Big idea"
                  boxes, and step cards.
  3. CONTENT    — all the words of the plan, kept as simple Python
                  data (lists and dictionaries), separate from layout.
  4. main()     — walks through the content and builds the PDF.

Run it with:
  C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe generate_dev_plan.py
"""

import os
import sys

from fpdf import FPDF

# ---------------------------------------------------------------------------
# 1. FONTS — Unicode if we can, ASCII-safe if we must
# ---------------------------------------------------------------------------

FONT_DIR = r"C:\Windows\Fonts"
FONT_FILES = {
    "": "calibri.ttf",      # regular
    "B": "calibrib.ttf",    # bold
    "I": "calibrii.ttf",    # italic
    "BI": "calibriz.ttf",   # bold italic
}

# Characters we use that only a Unicode font understands, and their
# plain-ASCII stand-ins for the fallback font.
ASCII_FALLBACK = {
    "\u2192": "->",   # right arrow
    "\u2713": "OK",   # check mark
    "\u2717": "X",    # cross mark
    "\u2014": "--",   # em dash
    "\u2013": "-",    # en dash
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2022": "*",    # bullet
    "\u00b7": "-",    # middle dot
}


def load_fonts(pdf):
    """Try to register Calibri. Return the family name we ended up with."""
    try:
        for style, filename in FONT_FILES.items():
            path = os.path.join(FONT_DIR, filename)
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            pdf.add_font("Calibri", style, path)
        return "Calibri", True
    except Exception as exc:  # any font trouble -> safe fallback
        print(f"[warn] Unicode font unavailable ({exc}); using Helvetica + ASCII text.")
        return "Helvetica", False


def sanitize(text, unicode_ok):
    """If we could not load a Unicode font, swap fancy symbols for ASCII."""
    if unicode_ok:
        return text
    for fancy, plain in ASCII_FALLBACK.items():
        text = text.replace(fancy, plain)
    # last resort: drop anything else non-latin-1
    return text.encode("latin-1", "replace").decode("latin-1")


# ---------------------------------------------------------------------------
# 2. PlanPDF — layout helpers
# ---------------------------------------------------------------------------

INK = (35, 46, 60)          # near-black blue-grey for body text
HEAD = (13, 92, 99)         # dark teal for headings (like the guide)
ACCENT = (233, 168, 38)     # amber for the "Big idea" boxes
BOX_FILL = (255, 249, 231)  # pale yellow callout background
STEP_FILL = (238, 244, 246) # pale teal step-card header
STOP_RED = (176, 58, 46)    # STOP marker
GREY = (120, 128, 136)


class PlanPDF(FPDF):
    def __init__(self, family, unicode_ok):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.family = family
        self.unicode_ok = unicode_ok
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(16, 16, 16)
        self.alias_nb_pages()

    # -- small conveniences ------------------------------------------------
    def txt(self, s):
        return sanitize(s, self.unicode_ok)

    def multi_cell(self, w, h=None, text="", **kw):
        # fpdf2's default leaves the cursor at the RIGHT edge after a
        # full-width block, which breaks the next full-width block.
        # We always want: back to the left margin, move down one line.
        kw.setdefault("new_x", "LEFT")
        kw.setdefault("new_y", "NEXT")
        return super().multi_cell(w, h, text, **kw)

    def font(self, style="", size=10.5):
        self.set_font(self.family, style, size)

    # -- running header / footer -------------------------------------------
    def header(self):
        if self.page_no() == 1:
            return
        self.font("", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, self.txt("AIOps Sentinel — Development Plan"),
                  align="L")
        self.ln(8)
        self.set_text_color(*INK)

    def footer(self):
        self.set_y(-14)
        self.font("", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, self.txt(f"Page {self.page_no()} / {{nb}}"), align="C")
        self.set_text_color(*INK)

    # -- building blocks -----------------------------------------------------
    def h1(self, number, title):
        self.ln(2)
        self.font("B", 17)
        self.set_text_color(*HEAD)
        self.cell(0, 10, self.txt(f"{number}  {title}"))
        self.ln(11)
        self.set_draw_color(*HEAD)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(*INK)

    def h2(self, title):
        self.ln(1)
        self.font("B", 12.5)
        self.set_text_color(*HEAD)
        self.multi_cell(0, 7, self.txt(title))
        self.ln(1)
        self.set_text_color(*INK)

    def para(self, text, size=10.5, style=""):
        self.font(style, size)
        self.multi_cell(0, 5.6, self.txt(text))
        self.ln(1.5)

    def bullets(self, items, size=10.5):
        self.font("", size)
        for item in items:
            x = self.get_x()
            self.cell(5, 5.6, self.txt("\u2022"))
            self.multi_cell(0, 5.6, self.txt(item))
            self.set_x(x)
        self.ln(1.5)

    def big_idea(self, title, text):
        """Yellow callout box, like the guide's 'THE BIG IDEA' boxes."""
        if self.get_y() > 240:          # keep box away from the page edge
            self.add_page()
        self.set_fill_color(*BOX_FILL)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        y0 = self.get_y()
        self.font("B", 9)
        self.set_text_color(*ACCENT)
        self.cell(0, 6, self.txt("  " + title.upper()), fill=True, border="LTR")
        self.ln(6)
        self.set_text_color(*INK)
        self.font("", 10.5)
        self.multi_cell(0, 5.6, self.txt("  " + text), fill=True, border="LR")
        # bottom edge
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.ln(4)

    def step_card(self, step):
        """One numbered step: id + name header, then labeled rows."""
        if self.get_y() > 225:
            self.add_page()
        # header bar
        self.set_fill_color(*STEP_FILL)
        self.font("B", 11)
        self.set_text_color(*HEAD)
        self.cell(0, 7.5, self.txt(f"  Step {step['id']} — {step['name']}"),
                  fill=True)
        self.ln(8.5)
        self.set_text_color(*INK)

        rows = [
            ("What we build", step["what"]),
            ("Why (the analogy)", step["why"]),
            ("Files touched", step["files"]),
            ("How we know it works", step["done"]),
        ]
        for label, value in rows:
            self.font("B", 9.5)
            self.set_text_color(*GREY)
            self.cell(42, 5.4, self.txt(label))
            self.set_text_color(*INK)
            self.font("", 10)
            x = self.get_x()
            self.multi_cell(0, 5.4, self.txt(value))
            self.ln(0.4)
        # STOP marker
        self.font("B", 9.5)
        self.set_text_color(*STOP_RED)
        self.multi_cell(0, 5.4, self.txt(
            "[ STOP ] — explain it back in your own words, then say "
            "\"I understand and approve\" before we write the next step."))
        self.set_text_color(*INK)
        self.ln(3)


# ---------------------------------------------------------------------------
# 3. CONTENT — the whole plan as data
# ---------------------------------------------------------------------------

WORKFLOW_RULES = [
    "Phase-based: we follow the guide's five phases in order — Intake, "
    "Checking, Deciding, Deploying, Verify & Close. We never jump ahead.",
    "5th-grader explanations: every step is explained in plain words with a "
    "real-world analogy BEFORE any code appears.",
    "One step, then stop: your mentor presents exactly one step, explains it, "
    "and stops. Nothing continues until you say \"I understand and approve\".",
]

PIPELINE_RECAP = (
    "An alert arrives (\"something is broken!\"). The AI reads it and writes ONE "
    "suggestion in a tiny strict language (the DSL). Four checkers inspect the "
    "suggestion one after another: OPA (the rule book) \u2192 Datalog (the "
    "\"who breaks?\" finder) \u2192 Prolog (the logic judge, the ONLY one who "
    "decides risk) \u2192 LTL (the time-order checker). Then the system decides: "
    "low risk may go alone; high risk must wait for a human's signed permission "
    "slip. Right before acting, Z3 (the math checker) takes a live photo of the "
    "machines and does the safety math one last time. Only then does the Tool "
    "Gateway — the only component with the passwords — do the action. Every "
    "event is written into an append-only diary, and nothing may close until "
    "the diary is complete."
)

PHASES = [
    # ----------------------------------------------------------------- P0
    {
        "number": "Phase 0",
        "title": "Setting up the workshop (before Phase 1)",
        "idea_title": "The big idea",
        "idea": "Before building LEGO, you lay all the pieces on the table and "
                "sort them. Phase 0 is exactly that: folders, tools and the "
                "official rule files — so every later phase finds its parts "
                "ready. This phase is preparation, not one of the guide's five "
                "phases; that is why we call it Phase 0.",
        "steps": [
            {
                "id": "P0.1", "name": "Create the project skeleton",
                "what": "The folder tree for the whole project: sentinel/ with "
                        "dsl/, policy/sentinel/, rules/, ltl/, constraints/, "
                        "audit/, gateway/, board/, web/, tests/.",
                "why": "A tidy toolbox: every drawer is labeled before we put "
                       "tools in it, so nothing gets lost later.",
                "files": "New folders only (plus empty __init__.py files).",
                "done": "The tree is visible in the file explorer and matches "
                        "the guide's Part 17.1 file list.",
            },
            {
                "id": "P0.2", "name": "Install the Python helpers",
                "what": "pip install z3-solver, lark, python-statemachine, "
                        "pytest into our existing .venv (fpdf2 and FastAPI are "
                        "already there).",
                "why": "Buying the missing tools for the workbench: the math "
                       "checker (z3), the grammar reader (lark), the game "
                       "board (python-statemachine) and the test runner "
                       "(pytest).",
                "files": "No project files — only the virtual environment "
                         "changes.",
                "done": "python -c \"import z3, lark, statemachine, pytest\" "
                        "prints no errors.",
            },
            {
                "id": "P0.3", "name": "Download the OPA program",
                "what": "The single-file OPA rule-book engine "
                        "(opa_windows_amd64.exe) saved into a tools/ folder.",
                "why": "OPA is a referee we hire from outside: one small .exe, "
                       "no installer, it just needs a seat at the table.",
                "files": "tools/opa.exe",
                "done": "Running \"tools\\opa.exe version\" prints a version "
                        "number.",
            },
            {
                "id": "P0.4", "name": "Install SWI-Prolog",
                "what": "The SWI-Prolog Windows installer (the logic judge's "
                        "engine). We only need its command line, swipl.",
                "why": "The judge needs a courtroom. SWI-Prolog is the "
                       "courtroom where our permission-and-risk rules will be "
                       "heard.",
                "files": "None in the project — a normal Windows install.",
                "done": "Running \"swipl --version\" in a fresh terminal "
                        "prints a version number.",
            },
            {
                "id": "P0.5", "name": "Copy in the five official rule files",
                "what": "The spec files exactly as printed in the guide: "
                        "dsl/remediation.ebnf (grammar), "
                        "policy/sentinel/authz.rego (OPA rules), "
                        "rules/topology.dl (Datalog spec), "
                        "rules/remediation.pl (Prolog rules), "
                        "audit/trace.schema (diary format).",
                "why": "These are the LAW BOOKS. We copy them in first and "
                       "unchanged, so every component we build later is "
                       "checked against the same official text.",
                "files": "The five files above, plus a VERSIONS.md noting "
                         "owner, source and date for each (guide Part 15).",
                "done": "Each file's content matches the guide page it came "
                        "from, word for word.",
            },
        ],
    },
    # ----------------------------------------------------------------- P1
    {
        "number": "Phase 1",
        "title": "Intake — understand the alert, let the AI write ONE suggestion",
        "idea_title": "The big idea",
        "idea": "A letter arrives. First we check it is a real letter (not "
                "junk), then we black out any secrets, then we let the AI read "
                "it and fill in a strict order form. The form is only accepted "
                "if every word is on the menu — that check is GATE 1, and "
                "nothing reaches any checker without passing it.",
        "steps": [
            {
                "id": "P1.1", "name": "Alert intake with a format check (T1)",
                "what": "A small module that receives an alert, checks it has "
                        "the right shape and comes from a known monitor, and "
                        "creates the incident with its unique id.",
                "why": "The mail slot: badly-shaped mail is thrown away and "
                       "logged, never opened.",
                "files": "sentinel/intake/alerts.py, tests/test_intake.py",
                "done": "A good alert moves the board Awaiting_Alert \u2192 "
                        "Alert_Parsed; a malformed one is rejected and logged.",
            },
            {
                "id": "P1.2", "name": "The secret remover / redactor (T2, rule L11)",
                "what": "Before any text goes to the AI, we collect the logs "
                        "and context and strip secrets (passwords, tokens, "
                        "personal data). Datalog's context query decides which "
                        "services the AI may even see.",
                "why": "Blacking out lines in a letter with a marker before "
                       "showing it to a stranger. Rule L11 says: secrets NEVER "
                       "leave our safe zone.",
                "files": "sentinel/intake/redactor.py, tests/test_redactor.py",
                "done": "Test: a log line containing a fake password comes out "
                        "with the password masked; the event logs_parsed "
                        "carries Redaction_Applied.",
            },
            {
                "id": "P1.3", "name": "MockLLM — the pretend AI with the fill-in form",
                "what": "A pretend AI that returns fixed, correct DSL "
                        "sentences for our three demo stories (and, on "
                        "purpose, some bad ones for tests). It receives the "
                        "fill-in-the-blanks prompt from guide Part 5.4. A real "
                        "AI (OpenRouter) can replace it later behind the same "
                        "interface.",
                "why": "A student actor who follows the script exactly, so "
                       "every class demo repeats the same way. The interface "
                       "is the costume — later a real actor can wear it.",
                "files": "sentinel/intake/llm.py (interface + MockLLM), "
                         "tests/test_llm.py",
                "done": "Asking MockLLM about story 1 always returns "
                        "\"propose restart_pod(web_frontend) because ... "
                        "confidence [0.72, 0.88];\".",
            },
            {
                "id": "P1.4", "name": "GATE 1 — DSL parser + type checker + fingerprint (T3/T4)",
                "what": "The Lark parser reads the AI's sentence against "
                        "dsl/remediation.ebnf. The type checker then verifies "
                        "every name is real (grounded), kinds match, numbers "
                        "are in range. Only then is the action_hash fingerprint "
                        "computed and the event llm_action_proposed sent — the "
                        "AI itself NEVER sends events. Bad output \u2192 "
                        "llm_output_invalid \u2192 Recovery with the exact "
                        "lesson.",
                "why": "The restaurant menu: you can only order dishes that "
                       "are printed on it — you cannot order a spaceship. And "
                       "the fingerprint is like a wax seal: every later check "
                       "refers to this exact order and no other.",
                "files": "sentinel/dsl/parser.py, sentinel/dsl/typecheck.py, "
                         "sentinel/dsl/fingerprint.py, tests/test_dsl_gate.py",
                "done": "All good/bad sentences from guide Part 5.3 behave "
                        "exactly as the table says (this is test P15).",
            },
        ],
    },
    # ----------------------------------------------------------------- P2
    {
        "number": "Phase 2",
        "title": "Checking — four checkers, in a fixed order",
        "idea_title": "The big idea",
        "idea": "Four security guards at four gates, always in the same order: "
                "OPA (is this allowed by company rules?) \u2192 Datalog (who "
                "breaks if we touch this?) \u2192 Prolog (is it permitted, and "
                "how risky? — the ONLY risk decider) \u2192 LTL (is the ORDER "
                "of steps okay over time?). Facts flow forward: each guard "
                "hands notes to the next, and no guard ever needs an answer "
                "from a later one.",
        "steps": [
            {
                "id": "P2.1", "name": "OPA adapter — the rule book (T5/T6)",
                "what": "A thin Python adapter that sends the proposed action "
                        "to the real OPA engine with our authz.rego rules, and "
                        "reads back allow / deny reasons. Plus the official "
                        "opa test suite from guide Part 10.1. Fails closed: if "
                        "OPA is missing or too slow, the answer is NO (T30).",
                "why": "The school rule book: 'no running in the halls' — "
                       "banned actions, change freezes and closed windows all "
                       "get a NO here, before anyone even studies the details.",
                "files": "sentinel/checkers/opa_adapter.py, "
                         "policy/sentinel/authz_test.rego, "
                         "tests/test_opa_adapter.py",
                "done": "\"opa test policy/ -v\" passes all tests from the "
                        "guide's table; a banned verb yields opa_denied with "
                        "the ban reason.",
            },
            {
                "id": "P2.2", "name": "Datalog module — the \"who breaks?\" finder (T7/T8)",
                "what": "A small, well-commented Python module implementing "
                        "the exact rules of rules/topology.dl: affected_by "
                        "chains, blast radius counting, secret-flow detection, "
                        "and the veto (NO if 10+ services break or secrets "
                        "would leak). The .dl file stays as the official spec "
                        "our code must mirror. It also hands two facts to "
                        "Prolog: sensitive_target and critical_in_blast.",
                "why": "The domino expert: 'if you push this piece, these 40 "
                       "fall'. We chose plain Python over installing the "
                       "Souffl\u00e9 engine (no native Windows build) — same "
                       "rules, simpler workshop.",
                "files": "sentinel/checkers/datalog.py, "
                         "tests/test_datalog.py (fixtures for veto, "
                         "dependents, sensitive_flow — part of test P17)",
                "done": "The Scenario 2 input from guide Part 10.2 (40 "
                        "services depend on master_db, limit 10) returns "
                        "datalog_sensitive_path with reason blast_radius.",
            },
            {
                "id": "P2.3", "name": "Prolog adapter — the logic judge, the ONLY risk authority (T9/T10)",
                "what": "An adapter that loads rules/remediation.pl into "
                        "SWI-Prolog and asks the three questions: allowed/3, "
                        "risk_level/3, why_refused/4. Risk is HIGH if any of "
                        "the 8 reasons hold (stateful target, "
                        "production-critical, secret data, critical service in "
                        "blast, rollback or DB restart, low confidence < 0.6, "
                        "a past human NO). NOBODY else in the whole system "
                        "computes risk.",
                "why": "A judge who must show their reasoning: not just "
                       "'guilty/innocent' but the written proof. And there is "
                       "only ONE judge for risk, so two parts of the system "
                       "can never disagree about how dangerous something is.",
                "files": "sentinel/checkers/prolog_adapter.py, "
                         "tests/test_prolog.py (allowed, risk_level, "
                         "why_refused cases — part of test P17)",
                "done": "Scenario 1 from guide Part 10.3 returns "
                        "prolog_allowed with risk low and a proof; the frozen "
                        "checkout example returns prolog_forbidden with "
                        "why_refused = change_frozen(checkout).",
            },
            {
                "id": "P2.4", "name": "LTL checker — the time-order guard (T11/T12)",
                "what": "The ltl/check.py evaluator from guide Part 8.5 with "
                        "the full rule list L1\u2013L15, each rule scoped "
                        "correctly (per action / per incident / per episode). "
                        "Used four ways: look-ahead at Temporal_Check, live "
                        "guard on every event, timers, and the end-of-diary "
                        "check.",
                "why": "Some rules are not about ONE step but about the ORDER "
                       "of steps: 'always wash your hands BEFORE eating'. Each "
                       "rule watches only the diary pages it is about, so one "
                       "action can never borrow another action's approval.",
                "files": "ltl/check.py, ltl/rules.py (L1\u2013L15), "
                         "tests/test_ltl.py",
                "done": "The allowed/forbidden order table from guide Part 8.7 "
                        "is reproduced exactly: story-1's order passes, "
                        "llm_action_proposed \u2192 execute is a violation of "
                        "L1.",
            },
        ],
    },
    # ----------------------------------------------------------------- P3
    {
        "number": "Phase 3",
        "title": "Deciding — alone, or ask a human?",
        "idea_title": "The big idea",
        "idea": "Prolog said HOW risky it is. Now OPA says what that risk "
                "MEANS: low risk \u2192 go alone; high or unknown risk \u2192 "
                "a human must sign. OPA never recomputes risk — it only maps "
                "Prolog's answer to a route, so the two can never disagree.",
        "steps": [
            {
                "id": "P3.1", "name": "The Arbiter + OPA risk routing (T13/T14)",
                "what": "The Arbiter reads Prolog's risk_level, asks OPA's "
                        "route query, and sends exactly one event: risk_low "
                        "(\u2192 straight to Constraint_Check) or risk_high "
                        "(\u2192 Human_Approval_Required). Missing or unknown "
                        "risk defaults to require_approval.",
                "why": "The teacher reads the thermometer (Prolog) and the "
                       "school policy (OPA) decides: below 38\u00b0C you stay "
                       "in class, above it your parents are called. The "
                       "teacher never invents a new temperature.",
                "files": "sentinel/decide/arbiter.py, tests/test_routing.py",
                "done": "risk low / high / missing route to autonomous / "
                        "require_approval / require_approval (OPA tests "
                        "test_route_low, test_route_high, test_route_missing).",
            },
            {
                "id": "P3.2", "name": "Approval service — one-time permission slips (T15/T16)",
                "what": "The approval screen's backend: shows the checkers' "
                        "own reasons (Datalog paths, Prolog proof, OPA route), "
                        "accepts Approve/Reject, and issues a one-time token "
                        "bound to this exact action_hash with an expiry. OPA "
                        "validates the approval: right role (sre/admin), same "
                        "fingerprint, not expired, never used before. A "
                        "rejection is saved as the fact rejected_before/2.",
                "why": "A permission slip signed for ONE exact field trip, "
                       "expiring at the end of the day. A slip for the zoo "
                       "does not work for the pool, a photocopy does not "
                       "count, and yesterday's slip is worthless.",
                "files": "sentinel/decide/approval.py, "
                         "tests/test_approval.py (viewer / other-hash / "
                         "expired / reused slips all refused — test P8)",
                "done": "Only a valid slip produces human_approved; every "
                        "broken slip produces nothing and the system keeps "
                        "waiting.",
            },
            {
                "id": "P3.3", "name": "The SLA timer — nobody waits forever (T17)",
                "what": "A waiting-time limit for human approval. When it "
                        "ends, the event approval_timeout fires and the "
                        "incident goes to Escalated — a person now owns it "
                        "and the system does nothing more alone (rule L4).",
                "why": "If you knock and nobody answers before dinner, you "
                       "don't stand at the door all night — you go find an "
                       "adult. Waiting must always END somehow: yes, no, or "
                       "time's up.",
                "files": "sentinel/decide/sla_timer.py, tests/test_sla.py",
                "done": "With no human answer inside the window, the board "
                        "moves Human_Approval_Required \u2192 Escalated.",
            },
        ],
    },
    # ----------------------------------------------------------------- P4
    {
        "number": "Phase 4",
        "title": "Deploying — Z3's last look, then the Gateway acts",
        "idea_title": "The big idea",
        "idea": "You asked at 2pm 'can I ride my bike?' and got a yes at 5pm. "
                "Before leaving you STILL look out the window — maybe it "
                "started raining! Z3 is that last look: it runs HERE, in "
                "Deploying, AFTER all decisions and approvals, on a live photo "
                "of the machines — never earlier. Then the Tool Gateway (the "
                "only one with passwords) acts, but only if the world hasn't "
                "changed since the photo.",
        "steps": [
            {
                "id": "P4.1", "name": "Z3 — the last gate, on live data (T18/T19)",
                "what": "constraints/deployment_gate.py from guide Part 11.4: "
                        "take a live snapshot (with a version number), check "
                        "the BEFORE rule (healthy enough to touch), apply the "
                        "action's effect from the DSL rule book (never from "
                        "the AI's words), then check all AFTER rules "
                        "(min_capacity, max_nodes, budget). sat \u2192 "
                        "Ready_For_Execution; unsat \u2192 Blocked with the "
                        "named unsat core — EVEN IF a human already approved.",
                "why": "Simple math on today's numbers: 'we have 4 machines, "
                       "a restart takes 1 away for a moment, 4\u22121=3, and "
                       "the rule says at least 3 must work — okay'. With only "
                       "3 machines, 3\u22121=2 fails the rule, so we stop.",
                "files": "constraints/deployment_gate.py, "
                         "tests/test_z3_gate.py (the sat and unsat examples "
                         "from guide Part 11.3 — tests P10 and P14)",
                "done": "Example A (4 machines) gives z3_sat; Example B (3 "
                        "machines, after human approval) gives z3_unsat with "
                        "post_min_capacity in the reasons.",
            },
            {
                "id": "P4.2", "name": "MockDriver + the pretend system map",
                "what": "A pretend infrastructure: a system map (services, "
                        "dependencies, node counts, which are stateful / "
                        "critical / sensitive) and a MockDriver that can "
                        "'restart' pretend pods, fail on purpose, or time "
                        "out — so we can rehearse every story safely.",
                "why": "A model railway: real signals, real switches, toy "
                       "trains. We practice emergencies without ever touching "
                       "a real city.",
                "files": "gateway/mockdriver.py, gateway/system_map.py, "
                         "tests/test_mockdriver.py",
                "done": "The driver can play: success, refuse, confirmed "
                        "failure, and timeout-then-really-done (needed for "
                        "P4.3 and test P4).",
            },
            {
                "id": "P4.3", "name": "Tool Gateway — compare-and-execute (T20\u2013T22)",
                "what": "The ONLY component that acts. It receives "
                        "{action_hash, program, snapshot_version, approval "
                        "token if any}, re-reads the world version and REFUSES "
                        "if it changed (stale_snapshot \u2192 Recovery). It "
                        "uses action_hash as the idempotency key (never the "
                        "same action twice), and on a timeout it reconciles — "
                        "asks the target what really happened before saying "
                        "'failed'.",
                "why": "The bus driver with the only keys. Before driving the "
                       "route the principal signed for, the driver checks the "
                       "road one more time; and if the radio cuts out "
                       "mid-trip, the office CALLS the school before sending a "
                       "second bus.",
                "files": "gateway/tool_gateway.py, tests/test_gateway.py",
                "done": "Changed world version \u2192 refused; duplicate slip "
                        "\u2192 refused (P11); timeout with no receipt \u2192 "
                        "reconcile first, then execution_failed only if truly "
                        "not done.",
            },
        ],
    },
    # ----------------------------------------------------------------- P5
    {
        "number": "Phase 5",
        "title": "Verify & Close — did it work, and is it in the diary?",
        "idea_title": "The big idea",
        "idea": "After the fix: check the patient's temperature, try again "
                "with a lesson if needed (at most 2 retries — and a checker's "
                "NO is NEVER retried), call a human when out of tries, and "
                "write everything in the diary. NOTHING may close until the "
                "diary is complete.",
        "steps": [
            {
                "id": "P5.1", "name": "Health probe — did the fix work? (T23/T24)",
                "what": "After the action, read the live health numbers "
                        "(SLIs): alert gone and metrics OK \u2192 "
                        "metrics_healthy; still broken \u2192 "
                        "metrics_still_degraded \u2192 Recovery.",
                "why": "The doctor takes your temperature again after the "
                       "medicine. 'We gave you the pill' is not the same as "
                       "'you are well'.",
                "files": "sentinel/verify/probe.py, tests/test_probe.py",
                "done": "Both outcomes drive the right board moves in a "
                        "story-1 rehearsal.",
            },
            {
                "id": "P5.2", "name": "Recovery + the retry counter (T25/T26)",
                "what": "The Recovery state: entering it REQUIRES a "
                        "recovery_reason and a counterexample (the exact "
                        "lesson). retry_count < 2 \u2192 back to AI_Analysis "
                        "with the lesson in the prompt, as a BRAND-NEW "
                        "suggestion with a new fingerprint, through ALL checks "
                        "again. retry_count \u2265 2 \u2192 Escalated. A NO "
                        "from a checker is never retried.",
                "why": "A teacher returning homework with the mistake circled: "
                       "you try again fresh (max twice), you don't erase-and-"
                       "resubmit the same page. And if the teacher said 'this "
                       "is against the rules', trying again is not allowed at "
                       "all — that is how sneaky retries are blocked.",
                "files": "sentinel/verify/recovery.py, "
                         "tests/test_recovery.py (P4, and the no-restart-loop "
                         "rule L12 in P13)",
                "done": "tool_failed retries at most twice then escalates; a "
                        "Blocked incident never re-enters the pipeline.",
            },
            {
                "id": "P5.3", "name": "Escalation + notifier (T27/T28)",
                "what": "The Blocked \u2192 Escalated path: the SRE receives "
                        "the checker's OWN explanation (OPA deny reasons, "
                        "Datalog paths, Prolog proof, Z3 unsat core), and "
                        "human_resolution_recorded says a person really fixed "
                        "the incident.",
                "why": "When the guard says NO, a grown-up takes over — and "
                       "the guard's exact reason is handed over, not a rumor. "
                       "The problem is only 'done' when the grown-up says the "
                       "problem itself is fixed.",
                "files": "sentinel/verify/escalation.py, "
                         "tests/test_escalation.py",
                "done": "Story 2's path (Blocked \u2192 escalation_notified "
                        "\u2192 Escalated \u2192 human_resolution_recorded) "
                        "runs end to end.",
            },
            {
                "id": "P5.4", "name": "Audit service — the append-only diary (T29)",
                "what": "The diary store: append-only JSONL in the exact "
                        "Trace/Event format of guide Part 13.1, every line "
                        "with phase, actor and action_hash. Before accepting "
                        "audit_log_created it checks the WHOLE diary against "
                        "all time rules L1\u2013L15. Incident_Resolved is "
                        "reachable ONLY through it (rule L7).",
                "why": "The class secretary writes minutes in PEN — you may "
                       "add lines, never tear pages out. And the meeting isn't "
                       "over until the minutes are read back and complete.",
                "files": "audit/audit_service.py, audit/trace.schema, "
                         "tests/test_audit.py (P5, P12)",
                "done": "A complete story-1 diary is accepted; a diary with "
                        "execution_succeeded jumping straight to "
                        "Incident_Resolved is refused (L6/L7).",
            },
            {
                "id": "P5.5", "name": "FastAPI + the simple web page",
                "what": "A small web page (FastAPI is already installed) with "
                        "three buttons — run Story 1, 2, 3 — plus the approval "
                        "screen (Approve / Reject with all the checkers' "
                        "reasons) and a diary viewer.",
                "why": "The stage for the class demo: one button per story, "
                       "and the audience can read the diary like a storybook "
                       "afterwards.",
                "files": "web/app.py, web/templates/, tests/test_web.py",
                "done": "All three demo stories run from the browser and end "
                        "in the exact final states the guide's Part 13 shows.",
            },
        ],
    },
]

GAME_BOARD = (
    "The state machine (python-statemachine) is the game board that makes "
    "illegal moves IMPOSSIBLE: 18 states, moves T1\u2013T30, each move allowed "
    "only when its guard is true. We build it incrementally: the skeleton "
    "(states + the happy-road moves as stubs) right after Phase 0, and then "
    "each phase 'switches on' its own moves as its checkers come alive — "
    "Phase 1 activates T1\u2013T4, Phase 2 activates T5\u2013T12 and T30, "
    "Phase 3 activates T13\u2013T17, Phase 4 activates T18\u2013T22, Phase 5 "
    "activates T23\u2013T29. The board is the only boss: components send "
    "events, the board decides what may happen next."
)

DEMOS_AND_TESTS = (
    "Exactly THREE demo stories (scope locked by the teacher): Story 1 — it "
    "works (restart web_frontend, low risk, no human); Story 2 — stopped "
    "(restart master_db, Datalog finds 40 dependents, limit is 10, blocked "
    "before anything changes); Story 3 — wrong order (something tries to "
    "execute right after the suggestion; the live guard refuses, rule L1). "
    "The approval-wait Z3 case, the restart loop and the DSL rejections are "
    "TESTS, not extra demos. All tests P1\u2013P18 from guide Part 16 start "
    "as 'planned' — per the teacher's rule v5-9, a test may only be called "
    "'passing' after it actually ran."
)

TESTS_BY_PHASE = [
    "Runnable after Phase 1: P15 (the DSL gate works).",
    "Runnable after Phase 2: P9 (a tricked AI is contained), P17 for OPA / "
    "Datalog / Prolog / LTL rule files, P18 (a broken checker means NO).",
    "Runnable after Phase 3: P3 (high risk never acts without approval), "
    "P8 (only real approvers count).",
    "Runnable after Phase 4: P10 (Z3 both answers), P11 (fingerprint "
    "everywhere), P14 (Z3 checks at deployment on fresh data), P16 (stages "
    "in the right place).",
    "Runnable after Phase 5: P1 (happy road), P2 (every NO \u2192 Blocked, "
    "nothing changed), P4 (failure \u2192 Recovery/Escalated), P5 (no close "
    "without diary), P12 (diary format), P13 (time rules / no restart loop), "
    "plus P6\u2013P7 if we build the Advisor extension later.",
]

CHECKPOINTS = [
    "(a) The DSL parser + type checker is GATE 1: it stands BEFORE all four "
    "checkers, and nothing the AI writes reaches OPA, Datalog, Prolog or LTL "
    "without passing it first (Phase 1, step P1.4).",
    "(b) Prolog is the ONLY component that calculates risk. OPA, Datalog, Z3 "
    "and the Arbiter never compute a risk level of their own (Phase 2, step "
    "P2.3).",
    "(c) OPA maps Prolog's risk to a ROUTE — autonomous or human approval. It "
    "reads the risk, it never re-decides it (Phase 3, step P3.1).",
    "(d) Z3 runs LAST, in the Deploying phase, on a live snapshot taken after "
    "all decisions and approvals — never early in the Checking phase (Phase "
    "4, step P4.1).",
]

STEP_NUMBERING = (
    "Every step in this plan has an ID like P2.3 — Phase 2, step 3. In any "
    "future session you can simply say 'we are on P2.3' and your mentor knows "
    "exactly where we stand. Each step card shows: What we build, Why (the "
    "analogy), Files touched, How we know it works, and the red STOP marker. "
    "The STOP marker is the heart of our workflow: after each step you "
    "explain it back in your own words, and only your explicit 'I understand "
    "and approve' unlocks the next step."
)


# ---------------------------------------------------------------------------
# 4. main() — build the document
# ---------------------------------------------------------------------------

def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "AIOps_Sentinel_Development_Plan.pdf")

    probe = FPDF()
    family, unicode_ok = load_fonts(probe)

    pdf = PlanPDF(family, unicode_ok)
    if unicode_ok:
        load_fonts(pdf)  # register on the real document too

    # ---------------- Cover page ----------------
    pdf.add_page()
    pdf.ln(40)
    pdf.font("B", 26)
    pdf.set_text_color(*HEAD)
    pdf.multi_cell(0, 12, pdf.txt("AIOps Sentinel"), align="C")
    pdf.font("B", 16)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 9, pdf.txt("The Step-by-Step Development Plan"), align="C")
    pdf.ln(4)
    pdf.font("", 11)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 6, pdf.txt(
        "For Danny & Kobi — AI Architects in training\n"
        "Built from: AIOps_Sentinel_Simple_Guide.pdf (v4 + v5 design)\n"
        "Date: 17 September 2026"), align="C")
    pdf.set_text_color(*INK)
    pdf.ln(14)
    pdf.big_idea(
        "How we will work together",
        "We build this project like a LEGO set with numbered bags: one bag "
        "at a time, in order, and we never open the next bag until the "
        "current one is built, understood and approved. Our three rules:")
    pdf.bullets(WORKFLOW_RULES)

    # ---------------- Section 1: the map ----------------
    pdf.add_page()
    pdf.h1("1", "The map of what we are building")
    pdf.big_idea(
        "The whole system in one breath",
        PIPELINE_RECAP)
    pdf.para(
        "The order of the guards never changes: "
        "AI suggests \u2192 GATE 1 (DSL) \u2192 OPA \u2192 Datalog \u2192 "
        "Prolog \u2192 LTL \u2192 risk route (alone / human) \u2192 Z3 last "
        "look \u2192 Tool Gateway acts \u2192 verify \u2192 diary \u2192 "
        "closed.", style="B")
    pdf.para(
        "Two choices we already made together: (1) the Datalog checker will "
        "be a tiny, well-explained Python module that mirrors the official "
        "rules/topology.dl spec — the Souffl\u00e9 engine has no native "
        "Windows build, and our rules are small; (2) the AI starts as a "
        "MockLLM (a pretend AI with fixed answers) so every class demo "
        "repeats identically — a real AI via OpenRouter can be plugged in "
        "later behind the same interface.")

    # ---------------- Phase sections ----------------
    for i, phase in enumerate(PHASES):
        pdf.add_page()
        pdf.h1(str(i + 2), f"{phase['number']} — {phase['title']}")
        pdf.big_idea(phase["idea_title"], phase["idea"])
        for step in phase["steps"]:
            pdf.step_card(step)

    # ---------------- Game board ----------------
    pdf.add_page()
    pdf.h1("8", "The game board — the state machine that rules them all")
    pdf.big_idea(
        "The big idea",
        "A board game: states are squares, events are dice rolls, and moves "
        "T1\u2013T30 say which rolls may move the piece from which square. "
        "Anything not on the board CANNOT HAPPEN — that is what makes "
        "illegal shortcuts impossible by design.")
    pdf.para(GAME_BOARD)

    # ---------------- Demos & tests ----------------
    pdf.h1("9", "The three demo stories and the tests P1\u2013P18")
    pdf.big_idea(
        "The teacher's rule",
        "Exactly three demo stories, no more. And we never say a test "
        "'passes' before it actually ran — every test below starts as "
        "'planned'.")
    pdf.para(DEMOS_AND_TESTS)
    pdf.h2("When each test becomes runnable")
    pdf.bullets(TESTS_BY_PHASE)

    # ---------------- Instructor checkpoints ----------------
    pdf.add_page()
    pdf.h1("10", "The instructor's four checkpoints")
    pdf.big_idea(
        "Put your architect hats on",
        "You are the bosses. At any moment you can check these four promises "
        "against what we have built — and you should, out loud, at the end "
        "of every phase.")
    pdf.bullets(CHECKPOINTS)

    # ---------------- Step numbering ----------------
    pdf.h1("11", "How the steps are numbered — and how we resume")
    pdf.para(STEP_NUMBERING)
    pdf.ln(4)
    pdf.font("B", 11)
    pdf.set_text_color(*STOP_RED)
    pdf.multi_cell(0, 6, pdf.txt(
        "[ FIRST STOP ]: read this whole plan. When you both understand "
        "it and approve it, we begin with step P0.1 — and not a moment "
        "sooner."))
    pdf.set_text_color(*INK)

    pdf.output(out_path)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"[ok] Wrote {out_path} ({size_kb:.0f} KB, {pdf.page_no()} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
