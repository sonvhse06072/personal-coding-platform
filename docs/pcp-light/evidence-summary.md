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
in the input. JSON object member names must also be unique in every object,
including nested objects; duplicate names are rejected before schema validation
instead of silently taking the last value. Every `source_sha` must be the same
full, lowercase 40-character hexadecimal SHA. The top-level JSON value must be
an array; an empty array is valid. Invalid JSON or records produce a sanitized
JSON error on stdout and a nonzero exit status. The error does not include input
contents, and validation failures emit no partial summary counts. The CLI reads
the input without modifying its bytes on success or error.

Example:

```sh
python3 scripts/pcp-light-evidence-summary.py evidence.json
```

For example, if the file contains one `SOURCE/PASS` and one `FIXTURE/FAIL`
record with the same source SHA, the CLI returns:

```json
{"by_class":{"FIXTURE":1,"LIVE":0,"PHYSICAL":0,"SOURCE":1},"by_class_and_outcome":{"FIXTURE":{"FAIL":1,"NOT_TESTED":0,"PASS":0},"LIVE":{"FAIL":0,"NOT_TESTED":0,"PASS":0},"PHYSICAL":{"FAIL":0,"NOT_TESTED":0,"PASS":0},"SOURCE":{"FAIL":0,"NOT_TESTED":0,"PASS":1}},"by_outcome":{"FAIL":1,"NOT_TESTED":0,"PASS":1},"count":2,"fixture_evidence_is_live":false,"source_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

`by_class_and_outcome` always contains every class and outcome, including
zero counts. Its counts agree with the existing totals and remain unchanged
when input records are reordered.

Empty input example:

```sh
printf '[]\n' > /tmp/empty-evidence.json
python3 scripts/pcp-light-evidence-summary.py /tmp/empty-evidence.json
```

The output includes total count, the common source SHA (or `null` for no
records), counts by class and outcome, a complete class/outcome cross-tab, and
the constant `fixture_evidence_is_live: false`. For an empty array all count
fields are zero and `source_sha` is `null`.
