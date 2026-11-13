# Safety, Privacy and Limitations Statement

## 1. Compliance with hackathon rules

- [x] **No live or institutional system accessed or tested.** Everything runs on one machine, on the synthetic pack. The "network attacks" in the evaluation target only our own local tool server, through a tap we built.
- [x] **Only synthetic data**, from the hackathon's starter pack. The prototype adds none.
- [x] **Nonpartisan.** No persuasion and no targeting. Bulletins that tell people how to vote are refused by policy, and the assistant is told never to advise on voting choices.
- [x] **Human oversight for consequential decisions.** Publishing and escalating always wait for a duty officer. No agent can declare a result, and result sheets are flagged for people, never decided by software.

## 2. Risk register

| Risk | Who could be harmed | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|---|
| False positive: a correct result sheet flagged | Polling-unit officials, whose sheet waits for review | Low on this data (0 of 858 clean sheets); unknown on real sheets | Delay, not rejection: flagged sheets are still recorded | Flags only queue for review; the rules are explainable | Real sheets will flag more; reviewers need capacity |
| False negative: a wrong sheet not flagged | Voters, candidates | Real errors and fraud are subtler than the pack's injected anomalies | A wrong figure passes the automatic checks | Checks are a first screen; collation, observers and party agents remain | High for errors that keep the totals consistent, such as a transposition that still adds up |
| A legitimate action refused or held | Staff, voters | Low (0 of 12 everyday tasks refused) | Delay; the assistant says why | Rules are reviewed and tested (21 policy tests) | Wording rules can be too broad or too narrow (see §4) |
| Bias against a language or group | Voters who don't use English | Medium | Worse answers in Hausa, Yoruba, Igbo, Pidgin | The FAQ is matched in all five languages; the reply is in the voter's language | The pack's translations are community drafts, and a 3B model is weaker outside English; not tested with speakers |
| Privacy: survey respondents re-identified | Survey respondents, especially disabled respondents in small areas | Low | Exposure of disability status | Rows denied to every agent; aggregates need 5+ respondents, enforced twice | Many overlapping aggregates could narrow a group (differencing) |
| Misuse: a staff member's agent key stolen | The public | Low | Calls as that role | One key per role, so the damage is bounded; every call logged; consequential calls still need a person | Keys are bearer secrets; a deployment needs rotation and short-lived tokens |
| Adversarial manipulation: prompt injection | Voters, the election body | High that it's tried; medium that a small model follows it | A false notice or an unauthorised action | Actions bounded by role; publishing needs approval; the tool server refuses anything without a receipt | The model can still **say** something false in its reply; replies aren't checked, only actions |
| Over-reliance: staff approve without reading | The public | Medium | A bad bulletin approved | The approval page shows the exact text, the rule and why it was held; partisan text is refused before approval | Approval fatigue is a human-factors risk; needs training and limits on volume |
| The gate unavailable | Staff, results flow | Low | Agents stop: nothing passes unchecked | Fails closed; restarts in seconds; file or Postgres state | Paper processes must remain the fallback |

## 3. Privacy and data protection

- **Personal data:** none processed; the data pack is fictional. In a real deployment, voters' questions would be personal data under the NDPA 2023. They reach only the model on the device, and the gate's audit log records argument hashes and short summaries, not values.
- **Minimisation:** the assistant has no tool that returns a person's record. The survey is available only as aggregates over five or more respondents. That's a k-anonymity floor on the quasi-identifiers state, age band, gender and disability type.
- **Retention:** the audit log can be archived to a signed, independently checkable file and deleted from the live log past a retention date (`consequenced -archive-audit`). The collation ledger follows the election body's record-keeping rules.
- **Access:** role-based by API key. The audit log needs a separate admin token.
- **Lawful basis and consent** would have to be settled before any real data is used (see §5).

## 4. Known limitations

- **Replies aren't checked.** The gate controls what the assistant *does*, not what it *says*. A manipulated model could still tell a voter something false in its answer. The system prompt and `claims.check` reduce this; they don't prevent it.
- **The FAQ has no answers yet.** The pack's answers are placeholders, so the assistant can recognise a question in five languages but can't answer it from the data. It says so and refers to official channels. Real answers must come from the election body and be reviewed in each language.
- **Translations are drafts,** and the matching is word overlap, so paraphrases, spelling variants and code-switching match less well. The assistant was not tested with native speakers.
- **Result checks are simple rules.** They find all 42 anomalies injected into the synthetic pack, but those were designed to be findable. The one digit transposition was caught only because it also broke the sum; a transposition that keeps the totals consistent would pass. They are a first screen, not fraud detection.
- **Wording rules are blunt.** The nonpartisan rule refuses phrases like "vote for". It would miss a partisan message worded otherwise, which then still goes to a person for approval. It could also refuse a neutral sentence containing one of its phrases.
- **Before any agent lists the tools,** the gate can't hold calls to the tools' schemas; ConsequenceOS pins tools at first listing. The tool server refuses unknown arguments itself, which covers this, and a fix in ConsequenceOS is planned.
- **The collation ledger isn't hash-chained.** Each entry carries its receipt ID, which the gate's chained log also records, but the ledger alone could be edited.
- **Approvers are identified by their link,** not a strong login. Passkey-signed approvals are planned in ConsequenceOS.
- **One machine, plain HTTP.** A deployment needs TLS between components, key rotation, and more than one gate instance.
- **The model was tested only with a scripted stand-in, plus a live small model on the demo prompts.** There's no statistical measure of how often a model follows injections; the design doesn't depend on it.

## 5. Conditions for further testing

Before any test beyond synthetic data:

1. **Partner sign-off** from the election body, and its legal and data-protection review, under the NDPA 2023 and the Electoral Act.
2. **Real FAQ answers,** written and reviewed by the election body in all five languages, and testing with native speakers, including voters with disabilities and with low literacy.
3. **An independent security review** of the gate, the tool server and the deployment, including red-teaming of the assistant with injection attempts in all five languages.
4. **Validation of the result checks** on historical, authorised result sheets, with returning officers, measuring false-alarm rates and reviewer workload.
5. **Approver training and load testing:** how many approvals a duty officer can review well per hour, and what happens at peak.
6. **Deployment hardening:** TLS, key rotation, Postgres-backed state, monitoring, and a tested fallback to paper processes.

## 6. Statement

"This prototype is not approved for operational electoral deployment."

Signed: _team representative, to be completed_, 13 December 2026
