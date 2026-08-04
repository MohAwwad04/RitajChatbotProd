# data/raw — superseded

This folder used to be the corpus: `ingest.build_index()` scanned it and indexed
every Markdown/PDF it found. A folder scan cannot express provenance, so
anything dropped here became a citable "source" with no canonical URL, no
approval and no hash.

The corpus is now defined by **`data/sources.yaml`** and the snapshots it points
at under `data/snapshots/<corpus-version>/`. `scripts/check_corpus_policy.py`
fails the build if an indexable file appears here.

- Old corpus, and why each file was excluded: `data/quarantine/README.md`
- Policy implementation: `src/ritaj/source_policy.py`
- Build: `python scripts/build_index.py --publish`
