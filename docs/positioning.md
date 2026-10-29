# Product positioning — facts vs hypotheses

This category is not empty. Existing tools include:

- **backcheck** (VectorInstitute): coding-agent session transcript and claim checking.
- **claimcheck** (ojuschugh1): local claim verification against filesystem and session evidence.
- **Prove It** (Pablo-aps): adversarial verification workflow as an Agent Skill.
- **aga-verify-agent** (agakadela): compares task, agent claims, code and proof.

RAEE-Lite is **not unique** merely because it compares claims to tests. The product hypothesis is that a local, deterministic evidence ledger with distinct roles is useful across providers and in automated checks.

## Scope decisions

1. **Never infer that test pass proves a task:** auto-discovered checks are reported separately from user-authored acceptance criteria.
2. **Code-bound freshness:** rerun after source fingerprint changes, or report stale evidence.
3. **Local-first:** never upload source by default; optional adapter parsing is future work, not implied as built.
4. **Unknown is not pass:** missing commands and incomplete fingerprints have explicit status.
5. **No invented AI scoring:** deterministic checks first; eventual agent-specific adapters must retain raw evidence provenance.

## Where competitors may be better

Existing agent transcript analyzers can already extract natural-language claims, while RAEE-Lite v0.2 cannot. Some also inspect tests being weakened. Integrated CI/patch replay services offer stronger execution isolation. This project does not claim parity with those functions.

## Product validation milestones (not current results)

- Test the tool on 20 public Node/Python repos with permission and review false positives.
- Show 10 developers a 30-second demo; measure install-to-first-report completion.
- Compare workflow coverage vs the alternatives in comparable, published tasks.
- Record issue-to-resolution time and repeated local usage, not only Star counts.
