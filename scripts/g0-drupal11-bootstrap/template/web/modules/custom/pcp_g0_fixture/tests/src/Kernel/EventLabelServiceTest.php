<?php

/**
 * @file
 * Covers the real Drupal 11 service container integration.
 */

namespace Drupal\Tests\pcp_g0_fixture\Kernel;

use Drupal\KernelTests\KernelTestBase;
use Drupal\pcp_g0_fixture\EventLabelNormalizer;
use PHPUnit\Framework\Attributes\Group;
use PHPUnit\Framework\Attributes\RunTestsInSeparateProcesses;

/**
 * Tests the fixture normalizer as a Drupal Kernel service.
 */
#[Group('pcp_g0_fixture')]
#[RunTestsInSeparateProcesses]
final class EventLabelServiceTest extends KernelTestBase {

  /**
   * {@inheritdoc}
   */
  protected static $modules = ['pcp_g0_fixture'];

  /**
   * Tests actual service wiring and baseline behavior.
   */
  public function testServiceRegistration(): void {
    $service = $this->container->get('pcp_g0_fixture.event_label_normalizer');
    self::assertInstanceOf(EventLabelNormalizer::class, $service);
    self::assertSame('Stage', $service->normalize(' Stage '));
  }

}
