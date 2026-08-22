# OKF Community Guide — FAQ, Comparisons & Practical Tips

Compiled from community sources: WitsCode, Flowtivity, GitBook, The Menon Lab, MarkTechPost.

---

## FAQ

### What is the Open Knowledge Format?

OKF is an open specification from Google Cloud (v0.1, June 2026) for
representing knowledge as a directory of markdown files with YAML
frontmatter. It formalizes the LLM-wiki pattern into a portable,
vendor-neutral format that humans can read and AI agents can parse
without an SDK. Its only required field is `type`.

### Who created OKF?

Google Cloud's Data Cloud team, led by Sam McVeety and Amir Hormati.
The specification lives in the public `GoogleCloudPlatform/knowledge-catalog`
repository on GitHub. It is an open, vendor-neutral format.

### Is OKF an SEO ranking signal?

**No.** OKF is not a ranking signal and Google's search systems do not
read a bundle from your site to rank it. It is an internal knowledge
format for AI agents, not a web publishing signal.

### What does an OKF bundle look like?

A directory of `.md` files. Each concept file has YAML frontmatter
(with at minimum a `type` field) followed by a markdown body. Reserved
files `index.md` and `log.md` list contents and record changes.
Internal links turn the directory into a graph.

### How do I add OKF to my website?

Write key knowledge as markdown concept files with `type` in the
frontmatter, link them together, add an `index.md`, and host the
bundle at a stable path (e.g., `/okf/` or a git repo).

### How does OKF differ from llms.txt?

`llms.txt` is a single file at your site root that points an agent at
pages worth reading. OKF is a whole directory of cross-linked, typed
concepts that hands the agent the knowledge itself. They are
complementary; a site can ship both.

### Is OKF worth adopting yet?

OKF v0.1 is an early, experimental spec. The honest case for adopting
now mirrors schema markup a decade ago: it's cheap to ship, it makes
your knowledge legible to the agents that are starting to answer
questions about you, and early movers learn the format before it
matters.

---

## Comparisons

### OKF vs. RAG

| OKF | RAG |
|-----|-----|
| Stores curated, cross-linked concepts | Stores raw document chunks |
| Relationships are explicit (links) | Relationships are inferred (similarity) |
| Agent traverses deliberately | Agent receives whatever the retriever returns |
| Knowledge compounds over time | Knowledge re-derived on every query |
| Version-controlled, diffable | Embedding drift, stale vectors |

### OKF vs. Other Agent Files

| Format | What it is | Scope | Who reads it |
|--------|-----------|-------|-------------|
| **OKF** | Directory of typed, linked markdown concepts | Whole knowledge base | Any agent or tool, across orgs |
| **llms.txt** | Single file listing URLs | One pointer list | Web crawlers and LLMs |
| **AGENTS.md / CLAUDE.md** | Instructions in a repo | One repo or agent | Coding agent in that repo |

---

## Practical Tips

### Use Cases

- **Data teams:** Auto-document BigQuery/Snowflake tables as OKF concepts
- **Engineering:** Self-updating incident runbooks
- **Cross-org:** Ship OKF bundles with APIs so clients' agents can consume them
- **Consultancies:** Deliver OKF bundles alongside AI systems

### Common Pitfalls

- Auto-generating bundles without meaningful `type` values or relationships
- Treating OKF as an SEO tactic (it isn't)
- Letting agents write from untrusted input (prompt injection risk)
- Over-structuring: OKF is minimalist by design — don't fight it

### Security Note

An agent-updated knowledge base introduces attack surface. If an agent
writes from untrusted input, the bundle becomes a vector for indirect
prompt injection. Control what writes into your bundle.

### Validation

Use the community-maintained OKF conformance validator to check bundles:

```
node validator/okf-validate.mjs ./your-bundle
```

It returns pass/fail, names every rule a file tripped, and exits with a
code you can gate CI on.
