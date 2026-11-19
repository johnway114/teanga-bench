# Licences for `samples/`

The repository's top-level `LICENSE` (Apache-2.0) covers the harness code,
build scripts, and documentation. It does **not** cover the benchmark sample
text under `samples/`.

Every row in `samples/<suite>/<test>.jsonl` retains the licence named in its
`metadata.licence` field and summarised in the adjacent
`samples/<suite>/<test>.ATTRIBUTION.md` file:

- **Gaelg Manx corpus sentences** (`samples/blas/translation.jsonl` and
  `samples/blas/round_trip.jsonl`): licensed **GPL-3.0**. These sentences stay
  under GPL-3.0 and are outside the Apache-2.0 grant.
- **Tatoeba sentences**: licensed **CC BY 2.0 FR**.
- **Gaois Irish legislation** and **Ofis Publik ar Brezhoneg** parallel text:
  licensed **CC BY 4.0**.
- **Senedd Cymru / Welsh legislation**: licensed **Open Government Licence v3.0**.
- **Wikipedia / Wiktionary (Kaikki) derived items**: licensed **CC BY-SA 4.0**.
- **App excerpts (`private-blas`, `private-tonada`)**: copyright Blas / Tonada,
  published here as public benchmark sample rows only. Because `samples/` is
  public, these 20-item sample files are exposed to model training data; the
  held-out sets stay in git-ignored `data/private/`.
