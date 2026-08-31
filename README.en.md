# Book2Advisor — Turn a person's methodology into an AI advisor you can consult anytime

> **English** | [中文](README.md)

> Feed in a person's books, articles, speeches, interviews and cases — get back a **traceable, inferential** "Personal Methodology Advisor" as a web app.
> It answers not just *"what did this person say"* — but **"how would this person think, following their method."**

## The problem it solves

"Book Q&A" systems (RAG) can answer *what's written in the book*, but fail on two classes of questions:

1. **Novel questions** — not covered in the source material (e.g. *"How would this entrepreneur view AI replacing factory workers?"*)
2. **Decision consulting** — *"Following this person's method, what should I look at first?"*

Book2Advisor solves this with a **Person Method Model**: the corpus is first **compiled** into a structured methodology skeleton (principles / rules / cases / diagnostic paths / tensions / evolution over time). At runtime the skeleton drives **inference** — in-book dilemmas are answered by direct quotation, novel problems by method extrapolation — and every answer explicitly marks **"grounded in source vs. method inference"**, eliminating hallucinated attributions.

## Core strengths of the method

- **Method Transfer**: novel problems get traceable answers derived from a *structured understanding of the methodology* — not from the luck of the source text mentioning the topic. This is the ultimate acceptance criterion and what distinguishes this project from document Q&A
- **Evidence First**: every principle/rule is bound to source evidence (E1–E5 grading; E5 = corroborated across multiple sources). All quotes are verbatim and verifiable against the original text — **never fabricating "he said"**
- **Citation / inference separation**: "what he said" (with provenance) and "what follows from his method" (explicitly marked) are strictly separated
- **Handles intellectual evolution**: tensions + timeline (evolution) — conflicting views across time are answered in chronological context instead of flattened into contradiction
- **Switch person = swap corpus only**: the Method Model drives everything; changing the person requires **zero code changes** (validated with two people whose corpora are radically different: autobiography-style vs. internal-speeches-style)
- **Auditable reasoning chain**: every answer outputs an 8-section Method Trace (problem understanding → diagnostic path → method selection → relevant cases → evidence → inference annotation) — every step is reviewable
- **Thin skeleton design**: the model keeps only high-confidence directional content (16–28 principles per person); no full rule engine, no pure RAG — low cost, maintainable, auditable

## Comparison with other approaches

### vs. generic RAG book Q&A

| Dimension | Generic RAG | Book2Advisor |
|---|---|---|
| Novel (out-of-book) questions | No method to rely on; stitches similar passages | **Method Transfer**: extrapolates from the methodology |
| Citation reliability | Retrieves similar paragraphs; risks misquoting out of context | Principle↔evidence binding, E1–E5 grading, verbatim & traceable |
| Conflicting views | Flattens related paragraphs; self-contradiction unnoticed | tensions + evolution timeline handling |
| Decision consulting | Returns "what the book says", not "what to do" | Full decision chain: diagnostic path → method → advice |
| Person distinctiveness | Every author answers in the same encyclopedic tone | Diagnostic paths & principle combinations differ per person (**Method Differentiation**) |

### vs. stuffing the whole corpus into a long-context LLM

| Dimension | Long-context stuffing | Book2Advisor |
|---|---|---|
| Cost | Every question consumes the entire corpus | Corpus **pre-compiled** into a thin skeleton; runtime locates only relevant principles |
| Consistency | Output drift, forgetfulness, hallucination on long input | Schema constraints + evidence binding + forced citation/inference separation |
| Auditability | Black box; no explanation for answers | 8-section Method Trace, fully reviewable |

### vs. "book-to-skill" style projects

book-to-skill (the reference for our Book Compiler layer) compiles a book into agent-loadable skill files. Book2Advisor adds the three missing pieces for a *methodology advisor*:

1. **Person Method Compiler**: multi-source fusion (synonym merging / cross-source corroboration / conflict detection / intellectual evolution) — interviews, speeches and cases join the book in one model
2. **Method Runtime**: an 8-step inference chain (classification → diagnostic path → method selection → case retrieval → evidence gathering → inference → annotation) — upgrading "skill files" to a full inference engine
3. **Evaluation system**: a 40-question evaluation set with independently written rubrics (anti-circular-reasoning), version regression comparison, and Method Differentiation validation — methodology **quality is measurable and regressable**

## Architecture

```
                     ┌─────────────────────────────────────┐
  books / articles   │  Compilation channel (offline,      │
  / speeches /       │  deterministic pipeline)             │
  interviews / cases │  Package Compiler → Person Method    │
        ───────────► │  Compiler (merging / corroboration / │
                     │  conflict detection)                 │
                     └──────────────────┬──────────────────┘
                                        │ Person Method Model
                     ┌──────────────────▼──────────────────┐
                     │  Runtime (Method Runtime)            │
  user question ───► │  classification → diagnostic path →  │
                     │  method selection → case retrieval → │
                     │  evidence → inference → Method Trace │
                     │  (8 sections, LLM-driven)            │
                     └─────────────────────────────────────┘
```

## Quick start (Web)

```bash
# 1. Clone & install
git clone https://github.com/jweokk/Book2Advisor.git
cd Book2Advisor
pip install -r web/requirements.txt
#    Optional: fallback document converter (used by convert.py when anydoc is unavailable)
#    pip install markitdown

# 2. Configure environment
cp .env.example .env
#    Edit .env: DEEPSEEK_API_KEY (DeepSeek, OpenAI-compatible)
#              METHOD_MODEL (path to the compiled method model — required, see steps 3/4)

# 3. Convert corpus (book/document → markdown)
python3 scripts/convert.py <your-book.pdf> --person jack-welch --type book

# 4. Validate the method model (must pass before use)
python3 scripts/validate_schema.py data/methods/<person>/<model>.yaml

# 5. Launch the web advisor
cd web && uvicorn app.main:app --host 0.0.0.0 --port 8000
# or Docker: docker compose -f web/docker-compose.yml up -d --build

# 6. Open http://localhost:8000 in a browser and ask
```

## Export as a Skill (let Claude Code / Hermes agents consult the person directly)

```bash
python3 scripts/export_skill.py --model data/methods/<person>/<model>.yaml --out ~/.claude/skills/<person>-method
# Output: SKILL.md + references/{principles,rules,cases,diagnostics}.md
# Install: copy to ~/.claude/skills/ (Claude Code), ~/.hermes/skills/ (Hermes), ~/.copilot/skills/, etc.
# Try instantly: python3 scripts/export_skill.py --model data/methods/example/person-example-v0.1.yaml --out /tmp/example-method
```

The agent auto-loads the skill when you ask "how would <person> view this problem", answering with a strict "cited evidence vs. method extrapolation" split (see docs/SKILL-EXPORT.md).

**Two distillation paths** (when compiling a person model):
- **Script fast path**: `scripts/extract_candidates.py` → `scripts/merge_candidates.py` (scripts call the LLM automatically; DeepSeek by default, switchable via env vars) — docs/COMPILING.md
- **Agent-driven distillation**: use your own agent + any LLM for extraction & fusion (no dependency on our LLM scripts) — docs/AGENT-DISTILLATION.md, or let an agent load the `skills/book2advisor-compiler` generator skill



> CLI mode: `python3 scripts/ask.py "your question"` (loads METHOD_MODEL or the default model).
> Corpus admission standards and compilation methodology: see [docs/CORPUS-STANDARD.md](docs/CORPUS-STANDARD.md).

## Directory layout

```
core/                   # Core code
  runtime/              #   Runtime: 8-step inference chain (ask.py / llm.py / prompts.py)
schemas/                # Person Method Model Schema (JSON Schema, 9 entity types)
scripts/                # CLI: convert / validate_schema / ask / gen_triggers
skills/                 # Generator skill (book2advisor-compiler: agent-driven distillation)
templates/              # Consultation-flow template (rendered into every exported skill)
data/methods/example/   # Example method model (export demo + test fixture)
web/                    # Web advisor: FastAPI + vanilla frontend (Method Trace view)
tests/                  # pytest (14 cases: schema / runtime / localization)
docs/                   # Methodology docs (corpus admission standards, etc.)
data/
  methods/              # Method models (no models bundled (compile your own, see Quick start), with Chinese names & E1–E5 evidence)
  sources/              # Corpora (copyrighted content, not distributed with the repo)
evaluations/            # 40-question evaluation sets & scoring reports (runtime artifacts)
```


## Methodology influences and independent improvements

Book2Advisor absorbed methodology from two open-source "book/person → AI skill" projects and made independent improvements shaped by its own "traceable Web advisor" form:

**From [cangjie-skill](https://github.com/kangarooking/cangjie-skill) (RIA-TV++ pipeline)**

- **`principle.trigger` scene design** (scenes / signals / not_for) — fixes "wrong principle picked": method selection matches triggers first; `not_for` blocks "universal magnet" principles (name-only matches) from firing
- **Triple verification (V2 predictive power / V3 distinctiveness)** — explicit fusion-stage gate: rejects "can only repeat examples" and "any smart person would say this" candidates; single-pass candidates demote to rules instead of being discarded
- **Stress-test groups (lure / confusion questions)** — evaluation tests not just "answers well" but "does it over-fire, does it pick the wrong principle"

**From [nuwa-skill](https://github.com/alchaincyf/nuwa-skill)**

- **Edge honesty (out-of-scope questions)** — topics absent from the corpus must explicitly declare "this is a method-based extrapolation"; asserting the person's stance out of thin air scores 0
- **Dual-agent blind judging** — answering agent and scoring agent are separate (LLM self-evaluation accuracy is only ~46%); the judge model is independently configurable
- **General-question detection (GENERAL_QA classification)** — conceptual/chit-chat questions no longer get business principles forced onto them; the advisor politely guides the user to give a concrete decision scenario instead
- **Coverage declaration** — the reasoning prompt forces an explicit "corpus does not cover this topic" note for out-of-domain questions

**Independent improvements (beyond the referenced projects)**

- **Delivery form**: static skill file → traceable Web advisor (E1–E5 evidence grading, verbatim quotes linkable back to the source, strict separation of "cited" vs "inferred")
- **Method Transfer**: novel out-of-book questions are extrapolated structurally from the methodology, producing an auditable 8-section Method Trace
- **Intellectual evolution**: tensions + evolution timeline — conflicting early/late views are answered by period, not flattened
- **Corpus-only person switching**: Method Model driven, validated with two persons of completely different corpus shapes (autobiography vs. internal speeches) with zero code changes
- **Four-group evaluation**: core (positive quality) + lures (zero tolerance for misfires) + confusions (unique selection) + out-of-scope (edge honesty), with regression-comparable question sets and rubrics

## Acknowledgements

This project references the following open-source projects and tools:

- **[cangjie-skill](https://github.com/kangarooking/cangjie-skill)** — trigger scene design, triple-verification gate, lure/confusion stress tests (see above)
- **[nuwa-skill](https://github.com/alchaincyf/nuwa-skill)** — edge-honesty scoring, dual-agent blind judging, general-question detection, coverage declaration (see above)
- **[book-to-skill](https://github.com/virgiliojr94/book-to-skill)** — primary reference for the Book Compiler layer: `structure-not-summary` extraction, lightweight methodology skeleton, layered evidence storage
- **[anydoc](https://www.npmjs.com/package/anydoc)** — document converter (office/text PDF → markdown)
- **[markitdown](https://github.com/microsoft/markitdown)** — fallback converter
- **[MinerU](https://github.com/opendatalab/MinerU)** — scanned-PDF conversion
## License

MIT
