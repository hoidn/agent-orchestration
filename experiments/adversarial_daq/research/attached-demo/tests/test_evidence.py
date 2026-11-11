"""The evidence check: a quote must be copied from one line of the bundle, not rewritten.

  python3 tests/test_evidence.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from evidence import not_in_bundle, quotes  # noqa: E402

BUNDLE = """==== control.log ====
2026-10-22 02:13:44,920 tmo-control[4127]: <E> tmo_atmpiranha_0 did not respond to disable phase 2
2026-10-22 02:13:44,921 tmo-control[4127]: <E> tmo_atmopal_0 did not respond to disable phase 2
==== xpm.txt ====
   6  hsd 3E:B                    1          0     1.000
==== tmo.cnf ====
 { host: 'drp-srcf-cmp026', id:'tmo_atmopal_0', flags:'spu', env:epics_env, cmd:drp_cmd0+' -l 0x1 -D opal'},
"""


class Quotes(unittest.TestCase):
    def test_only_lines_marked_as_quotes_are_quotes(self):
        self.assertEqual(quotes("# Evidence\n> a quoted line\nprose\n>  another \n"), ["a quoted line", "another"])

    def test_a_whole_line_is_found(self):
        self.assertEqual(not_in_bundle(["2026-10-22 02:13:44,921 tmo-control[4127]: <E> tmo_atmopal_0 did not "
                                        "respond to disable phase 2"], BUNDLE), [])

    def test_a_line_without_its_trailing_comma_is_found(self):
        self.assertEqual(not_in_bundle(["{ host: 'drp-srcf-cmp026', id:'tmo_atmopal_0', flags:'spu', env:epics_env, "
                                        "cmd:drp_cmd0+' -l 0x1 -D opal'}"], BUNDLE), [])

    def test_a_table_row_with_its_columns_respaced_is_found(self):
        self.assertEqual(not_in_bundle(["6  hsd 3E:B             1          0     1.000"], BUNDLE), [])

    def test_the_models_own_reasoning_behind_the_marker_is_not_found(self):
        quote = "stuck_transitions (no deadtime): the XPM reports DeadFrac 1, so there is deadtime."
        self.assertEqual(not_in_bundle([quote], BUNDLE), [quote])

    def test_a_changed_timestamp_is_not_found(self):
        quote = "2026-10-22 02:13:44,920 tmo-control[4127]: <E> tmo_atmopal_0 did not respond to disable phase 2"
        self.assertEqual(not_in_bundle([quote], BUNDLE), [quote])

    def test_a_quote_joined_across_lines_is_not_found(self):
        quote = "disable phase 2 2026-10-22 02:13:44,921"
        self.assertEqual(not_in_bundle([quote], BUNDLE), [quote])

    def test_a_short_fragment_is_not_evidence(self):
        self.assertEqual(not_in_bundle(["phase 2"], BUNDLE), ["phase 2"])


if __name__ == "__main__":
    unittest.main()
