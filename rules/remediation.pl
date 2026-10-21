% AIOps Sentinel — permission, risk and explanation (SWI-Prolog).
% Queried at Rule_Inference (T9/T10), AFTER Datalog, so derived topology facts are available.
%   allowed(Agent, Verb, Target)      Gate 2 — may this agent run this verb on this target?
%   risk_level(Verb, Target, Level)   the ONLY place risk is computed (v5 Fix #7)
%   why_refused(Agent, Verb, Target, Reason)   explainable refusal

:- dynamic stateful/1, tier/2, change_frozen/1,             % snapshot
           sensitive_target/1, critical_in_blast/2,          % Datalog (T7)
           proposal_confidence/2,                            % DSL program [Lo, Hi]
           rejected_before/2.                                % human rejections (T16)

% ---- principals ----------------------------------------------------------------
role(sentinel_agent, agent).
role(alert_advisor,  advisor).

% ---- verb classes (mirror the DSL grammar, §5.2) --------------------------------
remediation_verb(restart_pod).
remediation_verb(restart_service).
remediation_verb(scale_out).
remediation_verb(rollback).
remediation_verb(restart_master_db).

read_only_verb(list_services).
read_only_verb(get_metrics).

destructive_verb(delete_volume).
destructive_verb(drop_database).
destructive_verb(disable_monitoring).
destructive_verb(exfiltrate).

known_verb(V) :- remediation_verb(V).
known_verb(V) :- read_only_verb(V).
known_verb(V) :- destructive_verb(V).

state_changing(V) :- remediation_verb(V).
state_changing(V) :- destructive_verb(V).

% ---- what each role may do ------------------------------------------------------
permits(agent,   V) :- remediation_verb(V).
permits(agent,   V) :- read_only_verb(V).
permits(advisor, V) :- read_only_verb(V).

% ---- prohibitions -----------------------------------------------------------------
prohibited(V, _) :- destructive_verb(V).
prohibited(V, T) :- state_changing(V), change_frozen(T).

% ---- permission --------------------------------------------------------------------
allowed(Agent, Verb, Target) :-
    role(Agent, Role),
    known_verb(Verb),
    permits(Role, Verb),
    \+ prohibited(Verb, Target).

% ---- risk: single authority ---------------------------------------------------------
high_risk(_, T) :- stateful(T).
high_risk(_, T) :- tier(T, production_critical).
high_risk(_, T) :- sensitive_target(T).                    % from Datalog
high_risk(_, T) :- critical_in_blast(T, _).                % from Datalog
high_risk(rollback, _).
high_risk(restart_master_db, _).
high_risk(_, _) :- proposal_confidence(Lo, _), Lo < 0.6.   % conservative: the lower bound decides
high_risk(V, T) :- rejected_before(V, T).                  % a human said no to this before

risk_level(V, T, L) :- remediation_verb(V), ( high_risk(V, T) -> L = high ; L = low ).
risk_level(V, _, none) :- read_only_verb(V).

% ---- explanations: why was it refused? -----------------------------------------------
why_refused(Agent, _, _, no_role(Agent))            :- \+ role(Agent, _).
why_refused(_, V, _, unknown_verb(V))               :- \+ known_verb(V).
why_refused(Agent, V, _, not_permitted(Role, V))    :- role(Agent, Role), known_verb(V), \+ permits(Role, V).
why_refused(_, V, _, destructive(V))                :- destructive_verb(V).
why_refused(_, V, T, change_frozen(T))              :- state_changing(V), change_frozen(T).
