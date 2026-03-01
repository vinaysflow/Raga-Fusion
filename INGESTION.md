# Raga Source Ingestion (First Principles)

This pipeline separates **discovery**, **rights**, **ingestion**, and **library building**
so we can scale to Top‑50 sources per raga without mixing reference‑only content into the
production phrase library.

## 1) Discovery (Collections + Candidates)
- Collections: `data/source_collections.json`
- Individual candidates: `data/recording_sources.json`

To expand playlists into candidate recordings:
```
python expand_collections.py --limit 50
```
This writes `data/recording_sources_expanded.json` for manual curation.

## 2) Rights & Download Metadata
For each candidate you approve for ingestion:
- Set `rights_status` to one of: `licensed`, `public_domain`, `cc_by`, `cc0`, `ingestible`
- Provide a direct `download_url` if possible (preferred)

## 2.5) QA Report (Candidate Health)
Generate a quick QA report before downloading:
```
python seed_qa_report.py
```
This writes `data/seed_qa_report.json` and `data/seed_qa_report.md` with coverage,
rights status counts, missing fields, and duplicates.

## 3) Download + Normalize
```
python ingest_sources.py --use-yt-dlp
```
Ingest manifests now include file sizes, raw checksums, and `ingest_warnings`
for duration outliers.

Only ingestible sources are downloaded by default. Use `--include-reference` only for
temporary research.

## 4) Phrase Extraction + Library Merge
```
python build_library.py --count 20 --min-dur 3 --max-dur 7 --make-gold --gold-count 100
```
This merges phrase metadata into `data/phrases/<raga>/` and optionally builds
`data/phrases/<raga>_gold/`.

## 5) Rebuild Phrase Index
```
python phrase_indexer.py --force
```

## 6) Supabase Export
```
python export_supabase.py
```

Apply schema in `data/supabase_schema.sql` and import the generated CSVs:
- `data/supabase_source_collections.csv`
- `data/supabase_recording_sources.csv`
