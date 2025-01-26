import os
from unittest import TestCase
from py_ballisticcalc import (basicConfig, PreferredUnits, Unit, loadMixedUnits, loadMetricUnits, loadImperialUnits,
                              reset_globals)

ASSETS_DIR = os.path.join(
    os.path.dirname(
        os.path.dirname(__file__)
    ), 'assets')


class TestConfigLoader(TestCase):

    def test_preferred_units_load(self):
        with self.subTest("env"):
            basicConfig()
            self.assertEqual(PreferredUnits.distance, Unit.Yard)

        with self.subTest("manual"):
            basicConfig(preferred_units={
                'distance': Unit.Meter
            })
            self.assertEqual(PreferredUnits.distance, Unit.Meter)

        with self.subTest("imperial"):
            loadImperialUnits()
            self.assertEqual(PreferredUnits.distance, Unit.Foot)

        with self.subTest("metric"):
            loadMetricUnits()
            self.assertEqual(PreferredUnits.distance, Unit.Meter)

        with self.subTest("mixed"):
            loadMixedUnits()
            self.assertEqual(PreferredUnits.velocity, Unit.MPS)

        basicConfig()
        reset_globals()
        PreferredUnits.defaults()
