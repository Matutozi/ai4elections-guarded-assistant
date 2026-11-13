# System Card: Guarded Election Assistant

## Summary

An AI assistant for an election body's staff and voters. A small local language model chooses tool calls, and a policy gate (ConsequenceOS) decides what each call may do. The gate decides by the agent's role, holds consequential calls for a person, and records every decision in a tamper-evident log.

- **Components:**
  - the language model: Qwen2.5-3B-Instruct via Ollama, any tool-calling model works;
  - the policy: 13 rules, [config/consequence.yaml](../config/consequence.yaml);
  - the result checks: 7 fixed rules, `checks.py`;
  - the election-data tools: 12 MCP tools, `tools.py`.
- **Version:** 0.1, prototype, December 2026.
- **Authors:** Matutozi (team). The code and documents were written with AI assistance (see the README).

## Intended use

- **Users:** election-body staff in four roles (voter assistant, results officer, communications officer, analyst), and voters who talk to the voter assistant.
- **Tasks:**
  - answer voters' questions from the official FAQ in five languages;
  - check forwarded messages against fact-checks;
  - transmit result sheets, with consistency flags for review;
  - draft bulletins for approval;
  - summarise incidents and survey aggregates.
- **Out of scope, and prevented where possible:**
  - declaring or certifying results (denied to every agent);
  - deciding eligibility, sanctions or anything about a person;
  - persuasion or advice on how to vote (partisan bulletins refused; the model is instructed against it);
  - profiling respondents (row-level survey reads denied);
  - answering procedural questions the official FAQ doesn't answer (the tool abstains).

## Training and data

Nothing was trained. The language model is used as published. The policy and the result checks are hand-written rules. All data is the hackathon's synthetic pack ([DATASHEET.md](DATASHEET.md)): 100% synthetic, in English, Pidgin, Hausa, Yoruba and Igbo (the FAQ) and English and Pidgin (the claims).

## Evaluation

[EVALUATION.md](EVALUATION.md) has the full report. In summary:

| Slice | n | Result | Notes |
|---|---|---|---|
| Everyday tasks, 4 roles, 5 languages | 12 | 12 allowed (0 false refusals) | Scripted |
| Policy violations | 11 | 11 stopped | Roles, privacy, partisan content, declarations, smuggled arguments (including from a client that never lists the tools) |
| Human oversight paths | 4 | 4 as required | Held; approved and done exactly once; declined and never done |
| Network attacks | 6 | 6 refused; ledger untouched | Gate skipped, forged receipt, replay, votes altered in flight, tool swapped in flight |
| Result checks vs held-out labels | 900 sheets (42 anomalous) | Precision 1.0, recall 1.0 | Upper bound: the injected anomalies are simple |

**Baseline (measured):** without the gate, 7 of the 11 policy violations are carried out by the tools on their own; their safeguards stop only 4. Without the receipt check, none of the 6 network attacks would be refused.

## Error analysis

- **The reply channel is unguarded.** A model fooled by an injection can't publish, but it can still repeat the false claim in its answer to the voter. Who bears it: the voter. Mitigation: `claims.check` and the system prompt; not prevented.
- **Wording rules miss rephrasings.** The nonpartisan rule catches "vote for", not every partisan phrasing. A missed one still needs a duty officer's approval. Who bears it: the approver's attention.
- **Result checks miss consistent errors.** A sheet altered so that its totals still add up raises no flag. Who bears it: the integrity of collation, which still has human and observer checks.
- **FAQ matching by word overlap** misses paraphrases and spelling variants, especially in drafts with diacritics. Who bears it: non-English speakers, who get "no match" more often.

## Fairness and bias

The FAQ is matched in all five languages, and the answer uses the voter's language. We have not measured matching accuracy per language with native speakers, so we can't claim parity. A 3B model is weaker outside English and Pidgin. The claims data has no Hausa, Yoruba or Igbo fact-checks. Results checks treat every polling unit alike: the rules don't depend on location or party.

## Uncertainty and abstention

- **The FAQ tool abstains** when fewer than two words of the question match any FAQ entry, and always when the pack has no verified answer. It then refers the voter to official channels.
- **The agent stops** after six tool calls and refers the person to staff.
- **The result checks give no confidence score.** A flag is binary and only ever means "a person should look".

## Human oversight

- **Who reviews:** duty officers approve or decline every bulletin and escalation on the gate's approval page, and reviewers look at flagged result sheets.
- **Recorded:** every decision is in the gate's audit log, a hash chain with signed heads, verifiable with `consequenced -verify-audit`. Each action in the collation ledger carries the receipt of the decision that allowed it, naming the rule or the approver.
- **No agent can override a person.** A declined call is refused if the agent retries it.

## Ethical and legal considerations

- **Nonpartisan by design:** no tool takes a side, and partisan bulletins are refused.
- **Data protection:** the design follows the NDPA 2023's minimisation principle. There are no personal-record tools, aggregates have a k ≥ 5 floor, and the audit log stores hashes, not values. The model runs locally, so questions stay on the device.
- **Electoral law:** results are declared only by the returning officer. The system can't, and its checks don't decide anything.
- **Misuse risks:** a stolen role key acts as that role, bounded by its rules and logged. Using the gate to censor legitimate bulletins is possible for whoever writes the policy, so the policy file belongs under change control, and its tests run in CI.

## Maintenance

- **Policy changes:** changes to `config/consequence.yaml` are tested with `consequenced -test` (21 cases in ConsequenceOS's elections pack).
- **Integrity:** the audit chain is checked with `consequenced -verify-audit`.
- **Scenarios:** `python -m guarded_assistant.scenarios` reruns the whole evaluation in seconds.
- **Issues:** report them through the repository's issue tracker.
