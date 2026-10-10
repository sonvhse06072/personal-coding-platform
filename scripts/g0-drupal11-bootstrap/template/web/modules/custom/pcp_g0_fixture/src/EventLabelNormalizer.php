<?php

/**
 * @file
 * Provides the deliberately minimal initial label normalizer.
 */

namespace Drupal\pcp_g0_fixture;

/**
 * Normalizes a fixture label without external dependencies.
 *
 * Internal whitespace normalization is NOT part of this initial baseline.
 * It is reserved for the later G0D-T01 benchmark task.
 */
final class EventLabelNormalizer {

  /**
   * Removes surrounding ASCII whitespace without changing inner spacing.
   */
  public function normalize(string $label): string {
    return trim($label);
  }

}
