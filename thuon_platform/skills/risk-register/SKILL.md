---
name: risk-register
description: "Maintain and review a ranked risk register: likelihood, impact, velocity, mitigation, owner."
keywords: [risk, register, mitigation, velocity, impact, likelihood]
category: analysis
thuon:
  category: reporting

---

# Risk Register Skill

## Entry schema

For each risk: id, name, category (market/operational/regulatory/tech),
likelihood, impact, velocity (how fast it materializes), detection, mitigation,
owner, status.

## Likelihood × Impact grid (mitigation intensity)

- high × high → active mitigation, weekly review
- high/low → monitor
- low × low → accept

## Velocity priority

Velocity > impact when resources scarce. A high-velocity risk outpaces response
capacity even when its current impact is mid.

## Review discipline

- Re-rank monthly; archive done risks, don't delete (audit trail).
- Every new risk must cite its evidence (grade [A]/[B]/[C]).
- "New risk" requires a falsifier: what would tell us this is over-blown?

## Output

- Ranked table: ID, name, LxI, velocity, mitigation intensity
- Top-5 focus narratives
- Watch-list (velocity-driven medium risks)
