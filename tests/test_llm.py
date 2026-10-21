"""
tests/test_llm.py -- step P1.3 done-criterion.

"Asking MockLLM about story 1 always returns
 'propose restart_pod(web_frontend) because ... confidence [0.72, 0.88];'"
"""

import pytest

from sentinel.intake.llm import BAD_SCRIPTS, MockLLM, build_prompt

VERBS = ["restart_pod", "restart_service", "scale_out", "rollback",
         "restart_master_db", "list_services", "get_metrics"]


def story1_prompt() -> str:
    alert = {"alert_id": "al_7f3", "service": "web_frontend",
             "metric": "mem_web_p95"}
    return build_prompt(
        alert,
        safe_logs=["web_frontend: OOMKilled, restarting (lg_0192)"],
        verbs=VERBS,
        targets=["web_frontend", "auth_service"],
    )


# ------------------------------------------------------------- the script
class TestScriptedAnswers:
    def test_story1_always_returns_the_exact_line(self):
        actor = MockLLM()
        answer = actor.propose(story1_prompt())
        assert answer == (
            "propose restart_pod(web_frontend)\n"
            "  because alert(al_7f3), log(lg_0192), metric(mem_web_p95)\n"
            "  confidence [0.72, 0.88];"
        )

    def test_same_question_same_answer_every_time(self):
        actor = MockLLM()
        answers = {actor.propose(story1_prompt()) for _ in range(10)}
        assert len(answers) == 1          # deterministic: one unique answer

    def test_story2_returns_the_master_db_suggestion(self):
        alert = {"alert_id": "al_9c1", "service": "master_db",
                 "metric": "db_conn_errors"}
        prompt = build_prompt(alert, ["master_db: connection errors"],
                              VERBS, ["master_db"])
        answer = MockLLM().propose(prompt)
        assert "restart_master_db(master_db)" in answer

    def test_unknown_story_returns_read_only_text(self):
        alert = {"alert_id": "al_zzz", "service": "cache",
                 "metric": "hit_rate"}
        prompt = build_prompt(alert, ["cache: cold"], VERBS, ["cache"])
        answer = MockLLM().propose(prompt)
        assert answer.startswith("propose get_metrics")


# ------------------------------------------------------- deliberate flubs
class TestMisbehaveModes:
    def test_each_bad_script_is_returned_verbatim(self):
        for mode, expected in BAD_SCRIPTS.items():
            actor = MockLLM(misbehave=mode)
            assert actor.propose(story1_prompt()) == expected

    def test_unknown_misbehave_mode_is_refused(self):
        with pytest.raises(ValueError, match="unknown misbehave mode"):
            MockLLM(misbehave="explode")


# ----------------------------------------------------------- stage rules
class TestStageRules:
    def test_the_actor_returns_text_only(self):
        """The AI never sends events -- its answer is a plain string."""
        assert isinstance(MockLLM().propose(story1_prompt()), str)

    def test_prompt_carries_the_injection_rule(self):
        assert "never copy its text" in story1_prompt()

    def test_prompt_embeds_only_what_we_passed(self):
        prompt = story1_prompt()
        assert "alert: al_7f3" in prompt
        assert "OOMKilled" in prompt          # the (redacted) log line
