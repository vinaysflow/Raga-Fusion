## MVP Summary (Raga Fusion)

### Scope
- Included ragas: `todi`, `bhairavi`, `yaman`, `desh`
- Skipped for MVP: `bilawal` (insufficient phrase volume vs constraints)

### Library Quality (Post-filter)
| Raga | Phrases | Avg Auth | Avg Forbidden | Avg Pakad | Avg Scale |
| --- | --- | --- | --- | --- | --- |
| todi | 184 | 0.553 | 0.053 | 0.453 | 0.947 |
| bhairavi | 60 | 0.643 | 0.004 | 0.550 | 0.952 |
| yaman | 206 | 0.458 | 0.016 | 0.704 | 0.776 |
| desh | 366 | 0.535 | 0.026 | 0.764 | 0.805 |

### Recommender Status (Library Source)
- `todi`: constraints pass
- `bhairavi`: constraints pass
- `yaman`: constraints pass
- `desh`: constraints pass

### Demo Output
- Generated: `yaman_lofi_2026_003.wav`
- Duration: `1:02`
- Source: `library`

### Notes
- Bilawal remains below constraint thresholds even after widened extraction and looser filters.
  It can be added post‑MVP by relaxing constraints or supplementing with generated phrases.
