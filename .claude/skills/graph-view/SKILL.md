---
name: graph-view
description: Draw the repository dependency graph that /crucible:graph computes — god nodes, reference edges, and any import running against the declared layering — as one self-contained HTML page in artifacts/. Use when orienting in the codebase, before a refactor, or when explaining the architecture to someone.
argument-hint: [--focus <file>] [--no-tests] [--top N]
---

Render the dependency graph for: **$ARGUMENTS**

```
python3 scripts/graph_view.py --open $ARGUMENTS
```

That refreshes graphify's index, borrows its own `build_graph` and `pagerank`
(the picture shows the same numbers `/crucible:graph` prints — not a second
ranking), and writes `artifacts/<today>/graph.html`.

## How to read it

- **Distance from the centre is rank.** The middle is where the load-bearing
  modules are; the rim is leaf code. A file drifting inward over time is
  acquiring responsibility that nobody decided to give it.
- **Angle is layer**, labelled around the rim. The architecture reads as sectors.
- **Node size is PageRank share** — how much of the graph flows through it.
- **Ember-coloured edges run against the declared layering.** They come from
  `scripts/layer_check.py`; the count is in the footer.

## When the picture is the wrong tool

For "what does this change reach", use `/crucible:graph impact` — it answers in
text, in one turn, and does not need a browser. Draw the graph when the question
is about *shape*: what carries the weight, what is isolated, whether the layering
still holds. The page is a deliverable in `artifacts/`, so it is gitignored by
convention; regenerate rather than commit it.

The layout is seeded, so the same repository state draws the same picture.
