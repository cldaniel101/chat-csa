# LLM Wiki — Andrej Karpathy's Original Idea

Source: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

*This is the foundational concept that OKF formalizes. Karpathy published
this gist in April 2026. It accumulated 5,000+ stars and forks on GitHub
and directly inspired the Open Knowledge Format.*

---

## Core Idea

Most people's experience with LLMs and documents looks like RAG: you upload
a collection of files, the LLM retrieves relevant chunks at query time, and
generates an answer. This works, but the LLM is rediscovering knowledge
from scratch on every question. There's no accumulation. Ask a subtle
question that requires synthesizing five documents, and the LLM has to find
and piece together the relevant fragments every time. Nothing is built up.

The idea here is different. Instead of just retrieving from raw documents
at query time, the LLM incrementally builds and maintains a **persistent
wiki** — a structured, interlinked collection of markdown files that sits
between you and the raw sources.

When you add a new source, the LLM doesn't just index it for later
retrieval. It reads it, extracts the key information, and integrates it
into the existing wiki — updating entity pages, revising topic summaries,
noting where new data contradicts old claims, strengthening or challenging
the evolving synthesis. The knowledge is **compiled once** and then kept
current, not re-derived on every query.

> "LLMs don't get bored, don't forget to update a cross-reference, and can
> touch 15 files in one pass. The bookkeeping that causes humans to abandon
> personal wikis is exactly what LLMs are good at."

## Architecture

Three layers:

1. **Raw sources** — your curated collection of source documents (articles,
   papers, images, data files). Immutable — the LLM reads from them but
   never modifies them.

2. **The wiki** — a directory of LLM-generated markdown files. Summaries,
   entity pages, concept pages, comparisons, an overview, a synthesis.
   The LLM owns this layer entirely.

3. **The schema** (e.g., `CLAUDE.md` or `AGENTS.md`) — tells the LLM how
   the wiki is structured, what the conventions are, and what workflows to
   follow when ingesting sources, answering questions, or maintaining the
   wiki.

## Operations

- **Ingest.** Drop a new source into raw collection; LLM reads it, writes
  summaries, updates index, updates relevant entity/concept pages across
  the wiki, appends to log. A single source might touch 10-15 wiki pages.

- **Query.** Ask questions against the wiki. LLM searches for relevant
  pages, reads them, synthesizes an answer with citations. Good answers
  can be filed back into the wiki as new pages.

- **Lint.** Periodically health-check: contradictions, stale claims, orphan
  pages, missing cross-references, data gaps. The LLM is good at
  suggesting new questions to investigate.

## Indexing and Logging

Two special files help navigate the wiki:

- **index.md** — Content-oriented catalog of everything in the wiki. Each
  page listed with a link, one-line summary, and optionally metadata.
  Organized by category. Updated on every ingest.

- **log.md** — Chronological, append-only record of what happened and when.
  Entries with consistent prefixes (e.g., `## [2026-04-02] ingest | Title`)
  become parseable with simple Unix tools.

## Why This Works

> "The tedious part of maintaining a knowledge base is not the reading or
> the thinking — it's the bookkeeping. Updating cross-references, keeping
> summaries current, noting when new data contradicts old claims,
> maintaining consistency across dozens of pages. Humans abandon wikis
> because the maintenance burden grows faster than the value."

The human's job: curate sources, direct analysis, ask good questions, think
about what it all means. The LLM's job: everything else.
