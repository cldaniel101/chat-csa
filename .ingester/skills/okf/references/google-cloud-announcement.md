# Google Cloud Announces Open Knowledge Format (OKF)

Source: https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing

**Date:** June 12, 2026
**Authors:** Sam McVeety (Tech Lead, Data Analytics) & Amir Hormati (Tech Lead, BigQuery)

---

## Summary

Google Cloud introduced the Open Knowledge Format (OKF), an open
specification that formalizes the LLM-wiki pattern into a portable,
interoperable format. OKF is a vendor-neutral, agent- and human-friendly
standard for representing the metadata, context, and curated knowledge
that modern AI systems need.

## The Problem

In most organizations, the information that foundation models need is
overwhelmingly internal knowledge: table schemas, metric definitions,
runbooks, join paths, API deprecation notices. These atoms of knowledge
live in fragmented systems:

- Metadata catalogs with their own APIs
- Wikis, third-party systems, or shared drives
- Code comments, docstrings, or notebook cells
- The heads of a few senior engineers

Every agent builder solves the same context-assembly problem from scratch.
Every catalog vendor reinvents the same data models. Knowledge is locked
behind whichever surface created it.

## The Solution: A Format, Not a Service

OKF is a directory of markdown files with YAML frontmatter:

- **Just markdown** — readable in any editor, renderable on GitHub
- **Just files** — shippable as a tarball, hostable in any git repo
- **Just YAML frontmatter** — for queryable structured fields

## Three Design Principles

1. **Minimally opinionated** — Only `type` is required. Content model is
   left to the producer.
2. **Producer/consumer independence** — Human-authored bundles consumed by
   agents, pipeline-generated exports browsed by humans, bundles written
   by one LLM queried by another.
3. **Format, not platform** — No proprietary account or SDK required.
   Published as an open standard (Apache 2.0).

## What Google Shipped

- **Enrichment agent** — Walks BigQuery datasets, drafts OKF concept
  documents, enriches with citations, schemas, and join paths.
- **Static HTML visualizer** — Turns OKF bundles into interactive graph
  views in a single self-contained HTML file.
- **Three sample bundles** — GA4 e-commerce, Stack Overflow, and Bitcoin
  public datasets.
- **Knowledge Catalog integration** — Google Cloud's Knowledge Catalog
  can now ingest OKF.
