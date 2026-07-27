from __future__ import annotations

import unittest

from nautobot_intent_catalog import compute_conformance as conformance
from nautobot_intent_catalog import compute_contract as contract


class ComputeConformanceTests(unittest.TestCase):
    def test_every_public_owner_symbol_has_a_case_or_constant(self) -> None:
        rules = {case["rule"] for case in conformance.CASES}
        self.assertTrue(set(conformance.PUBLIC_SYMBOLS) <= rules | {"ComputeContractError"})
        self.assertTrue(set(conformance.CONSTANTS) <= set(conformance.build_fixture()["constants"]))

    def test_constants_resolve_to_live_owner_attributes(self) -> None:
        for name, value in conformance.build_fixture()["constants"].items():
            self.assertEqual(value, getattr(contract, name))

    def test_fixture_is_byte_stable(self) -> None:
        self.assertEqual(conformance.dumps_fixture(), conformance.dumps_fixture())


if __name__ == "__main__":
    unittest.main()
