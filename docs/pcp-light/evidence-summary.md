# PCP Light evidence summary

`scripts/pcp-light-evidence-summary.py` is a standard-library-only, read-only
CLI. It accepts one JSON file containing an array of evidence records and emits
deterministic counts. It does not fetch evidence, authenticate it, mutate
Runtime or a database, or make authority decisions. A `FIXTURE` record remains
fixture evidence; counts never promote it to `LIVE`.

Each record must have exactly these fields:

```json
{
  "id": "observe-smoke-1",
  "class": "FIXTURE",
  "outcome": "PASS",
  "source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

`class` is one of `SOURCE`, `FIXTURE`, `PHYSICAL`, or `LIVE`. `outcome` is one
of `PASS`, `FAIL`, or `NOT_TESTED`. `id` is a nonempty string and must be unique
in the input. Every `source_sha` must be the same full, lowercase 40-character
hexadecimal SHA. The top-level JSON value must be an array; an empty array is
valid. Invalid JSON or records produce a JSON error on stdout and a nonzero
exit status.

Example:

```sh
python3 scripts/pcp-light-evidence-summary.py evidence.json
```

Empty input example:

```sh
printf '[]\n' > /tmp/empty-evidence.json
python3 scripts/pcp-light-evidence-summary.py /tmp/empty-evidence.json
```

The output includes total count, the common source SHA (or `null` for no
records), counts by class and outcome, and the constant
`fixture_evidence_is_live: false`.
