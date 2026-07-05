"""A/B testing — embedding-model bake-off (plan section 13, §5 note).

Compares two embedding models on the same labelled retrieval set
(ritaj.evaluation.RETRIEVAL_EVAL), scored by recall@1/3/5 + MRR over an in-memory
index built per model. The live Qdrant index is never touched.

This is how you decide whether to switch the embedder (e.g. e5 vs BGE-M3) on
evidence rather than vibes. Each model is downloaded on first use (multi-GB), so
this is a deliberate, offline experiment — not part of CI.

Usage:
  .venv/bin/python scripts/eval_ab.py                       # e5-large vs e5-base
  .venv/bin/python scripts/eval_ab.py A_MODEL B_MODEL       # any two HF models

e5 models want "query:"/"passage:" prefixes; BGE-M3 and most others don't — pass
the right prefixing by editing PREFIXED below or extend the CLI as needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentence_transformers import SentenceTransformer  # noqa: E402

from ritaj import arabic  # noqa: E402
from ritaj.evaluation import recall_for_embedder  # noqa: E402

# Models whose names contain "e5" need the query:/passage: prefixes; others don't.
DEFAULT_A = "intfloat/multilingual-e5-large"
DEFAULT_B = "intfloat/multilingual-e5-base"


def make_embedder(model_name: str):
    """Build (embed_passages_fn, embed_query_fn) for a sentence-transformers model."""
    model = SentenceTransformer(model_name)
    e5 = "e5" in model_name.lower()
    qpref, ppref = ("query: ", "passage: ") if e5 else ("", "")

    def passages(texts):
        prefixed = [ppref + arabic.normalize_light(t) for t in texts]
        return model.encode(prefixed, normalize_embeddings=True)

    def query(text):
        return model.encode([qpref + arabic.normalize_light(text)],
                            normalize_embeddings=True)[0]

    return passages, query


def main() -> None:
    a_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_A
    b_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_B

    print(f"A/B embedding bake-off (downloads each model on first use)\n"
          f"  A: {a_name}\n  B: {b_name}\n")

    results = []
    for label, name in (("A", a_name), ("B", b_name)):
        print(f"  scoring {label} ({name}) …")
        pas, qry = make_embedder(name)
        results.append((label, name, recall_for_embedder(pas, qry)))

    print(f"\n{'':>2}  {'r@1':>5} {'r@3':>5} {'r@5':>5} {'mrr':>5}  model")
    print("-" * 60)
    for label, name, m in results:
        print(f"{label:>2}  {m['r1']:>5} {m['r3']:>5} {m['r5']:>5} {m['mrr']:>5}  {name}")


if __name__ == "__main__":
    main()
