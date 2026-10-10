<?php

namespace Drupal\Tests\pcp_g0_fixture\Unit;

use Drupal\pcp_g0_fixture\EventLabelNormalizer;
use Drupal\Tests\UnitTestCase;
use PHPUnit\Framework\Attributes\Group;

/**
 * Tests the isolated normalizer on ordinary labels only.
 *
 * @coversDefaultClass \Drupal\pcp_g0_fixture\EventLabelNormalizer
 */
#[Group('pcp_g0_fixture')]
final class EventLabelNormalizerTest extends UnitTestCase {

  /**
   * Tests a normal label.
   */
  public function testOrdinaryLabel(): void {
    self::assertSame('Acoustic', (new EventLabelNormalizer())->normalize('Acoustic'));
  }

  /**
   * Tests surrounding whitespace without internal normalization.
   */
  public function testTrimsOuterWhitespace(): void {
    self::assertSame('Jazz Band', (new EventLabelNormalizer())->normalize(" \tJazz Band\n "));
  }

}
