# Methodology

## Approach

**Control actions, not words.** We don't try to make the language model safe, because no prompt or filter makes a model reliably resistant to instructions hidden in what it reads. We assume the model will sometimes be fooled. We make sure that what it is fooled into doing either isn't allowed for its role, or waits for a person, or is refused by the system it targets.

This splits the work into four layers. Each is checked separately, and each holds if the one before it fails:

| Layer | What it does | Where |
|---|---|---|
| 1. The model's instructions | Treat forwarded text as data, stay nonpartisan, don't guess procedures | `agent.py`, the system prompts |
| 2. The policy gate | Decide each tool call by the agent's role, its arguments and the time. Hold what's consequential for a person, and record everything | ConsequenceOS, [config/consequence.yaml](../config/consequence.yaml) |
| 3. The receiving systems | Run a call only with the gate's receipt for exactly that call. Refuse arguments no schema names. Suppress small survey groups whatever is asked | `server.py`, `tools.py` |
| 4. The record | Hash-chained audit log with signed heads (the gate), and the collation ledger with each action's receipt (the tools) | ConsequenceOS, `.run/ledger.jsonl` |

Layer 1 is the only one a model can talk its way past, and nothing depends on it.

## Design choices

- **The roles** are voter assistant, results officer, communications officer and analyst. These are the jobs an election body would actually give an assistant, each with the least access it needs. Roles are bound to API keys on the gate's side, so a prompt can't change them.
- **Human oversight where the rules require it:** "Tools flag, assist or inform. They do not declare results, decide eligibility or auto-sanction people."
  - Publishing and escalating always ask a person.
  - Declaring results is denied to every agent.
  - A result sheet that fails a check is recorded and queued for review, never refused or corrected by software.
  - A burst of more than 30 transmissions in an hour from one officer asks a person too: a polling unit sends once.
- **The result checks** are fixed rules, the same as the template's `integrity_flags`, applied to each sheet as it arrives:
  - accredited voters above the registered voters;
  - votes plus rejected ballots not equal to accredited voters;
  - all-round numbers;
  - identical to the previous sheet;
  - registered voters not matching the register;
  - negative counts;
  - a second transmission for the same unit.
  
  Rules can be explained to a returning officer, and nothing was trained on the held-out labels.
- **Privacy:** the survey's quasi-identifiers (state, age band, gender, disability type) are released only as aggregates over groups of at least five. That's the k-anonymity threshold from the Track 4 starter notebook. It's enforced twice: the gate refuses smaller requests, and the tool suppresses small groups anyway.
- **Signed receipts** are dual-signed with Ed25519 and ML-DSA-87, so they stay sound if quantum computers break today's signatures. They're single-use and bound to the exact tool and arguments. Only the gate can produce one, so the receiving systems need no knowledge of the policy to enforce it.
- **A local model.** The agent runs a small open model on the laptop (Qwen2.5-3B via Ollama). Voters' questions never leave the machine, and it works without connectivity. A small model is also more easily fooled, which tests the design honestly.

## Data used

Only the hackathon's synthetic starter pack (see [DATASHEET.md](DATASHEET.md)):

| File | Used for |
|---|---|
| Voter-information FAQ (5 languages) | `faq.answer` |
| Polling units | `units.lookup`, and the register figure for each result check |
| Results | `results.unit`, `results.flags`, and the sheets transmitted in the evaluation |
| Held-out anomaly labels | Only to measure the result checks |
| Misinformation claims | `claims.check` |
| Incident reports | `incidents.summary`, `incident.escalate` |
| Accessibility survey | `survey.aggregate` (and `survey.respondents`, which the policy denies) |

## Evaluation method

1. **Scripted scenarios** (`python -m guarded_assistant.scenarios`) run the real stack: gate, tool server and tap. They make 33 checks in four groups, each with an expected outcome:
   - everyday work that must be allowed;
   - policy violations that must be stopped;
   - human-oversight paths, held then approved or declined;
   - network attacks between the gate and the tool server. A tap captures, replays and alters real traffic.

   They also check the audit log's chain and that attacks leave the collation ledger untouched. There's no model in the loop, so the outcomes repeat exactly.
2. **Result checks against held-out labels:** precision and recall over the 900 synthetic result sheets, per anomaly type.
3. **The model in the loop:** the agent is tested against a scripted model that follows an injected instruction, to show the refusal reaches the model and the voter. A live small model is run on the same injection message for the demo; [EVALUATION.md](EVALUATION.md) says what it did.
4. **Unit tests** (`pytest`) cover the tools, checks, server and agent loop. The policy itself has 21 policy tests in ConsequenceOS (`examples/policies/elections.test.yaml`), covering every rule.

The policy pack and the roles feature were also checked by deliberately breaking them in 12 ways, each still compiling. The tests caught every break.
