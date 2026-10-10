# PCP G0 Drupal 11 — isolated benchmark seed

This private, non-production fixture was created under the explicitly scoped Owner approval in PCP #595. No data or code from Chợ Nhạc or any existing personal project is permitted. The source seed is intentionally **not** the benchmark task: G0D-T01 internal whitespace collapsing has not been implemented.

## Baseline checks

From this exact fixture DDEV directory:

```bash
ddev composer validate --strict
ddev exec bash -lc "export SIMPLETEST_DB='mysql://db:db@db/db'; export SIMPLETEST_BASE_URL='http://web'; vendor/bin/phpunit -c web/core/phpunit.xml.dist web/modules/custom/pcp_g0_fixture/tests/src/Unit"
ddev exec bash -lc "export SIMPLETEST_DB='mysql://db:db@db/db'; export SIMPLETEST_BASE_URL='http://web'; vendor/bin/phpunit -c web/core/phpunit.xml.dist web/modules/custom/pcp_g0_fixture/tests/src/Kernel"
ddev exec vendor/bin/phpcs --standard=Drupal web/modules/custom/pcp_g0_fixture
```

No live quality success is claimed until these commands and the repository's GitHub CI actually complete. Never commit credentials, database dumps, or generated test results. The seed must be reviewed and registered in PCP with its exact source commit before any PCP benchmark execution. Two benchmark refs must share that exact source commit; their checkouts and databases must remain separate.
