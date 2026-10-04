# plan/

Working context for whoever picks this up next — a person or Claude. Not the
website: `docs/` is published and written for users, this is written for
whoever has to do the work.

It lives in the repo on purpose. Claude's own memory is keyed to the
directory the repo sits in, and on 2026-10-03 the directory was renamed from
`redash` to `sqldesk` and every memory went quiet. Anything that matters
belongs here, where a rename cannot reach it.

| File | What it answers |
|---|---|
| [state.md](state.md) | Where the project is right now: released, in flight, not started |
| [conventions.md](conventions.md) | How a release is named and cut, how commits read, what gets tested |
| [local-dev.md](local-dev.md) | The minikube cluster, the Kafka demo stack, and the traps that cost hours |
| [scale.md](scale.md) | What breaks at 500 concurrent users, measured, and what it would cost to run |
| [0.7-nav.md](0.7-nav.md) | The nav restructure: why there is no vendor name in the bar, and what `Streaming` means next to `Live` |
| [0.8-plan.md](0.8-plan.md) | The next release: notebooks, and knowing what a query costs |
| [0.8-notebooks.md](0.8-notebooks.md) | Notebooks: why they exist, where user code is allowed to run, and the decisions still open |
| [open-questions.md](open-questions.md) | What is waiting on Iqbal |

## Keeping it true

A plan that describes something the code does not do is worse than no plan.
Two of these are held to the code by tests — `tests/test_docs.py` checks that
the permissions table and the chart defaults in `docs/` still match
`sqldesk/features.py` and `charts/sqldesk/values.yaml`. The rest are honest
because somebody updates them in the same commit as the change.

When a release ships, `state.md` and `0.8-plan.md` move on together: the
shipped list grows, the next plan becomes the current one, and a new one is
started. Do not leave a plan describing work that is finished.
