import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "Scripts" / "audit_official_map_refs.py"
SPEC = importlib.util.spec_from_file_location("audit_official_map_refs", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class OfficialMapRefAuditTests(unittest.TestCase):
    def test_map_ref_transform_matches_official_2026_javascript(self) -> None:
        perspective = MODULE.MapPerspective()
        bridge = perspective.unproject(x=2198, y=1893)
        chans = perspective.unproject(x=2100, y=1086)

        self.assertEqual(bridge, (-93.17121846864647, 44.981333151668636))
        self.assertEqual(chans, (-93.17182200756324, 44.978456518823435))

    def test_exact_vendor_id_is_selected_from_multi_feature_page(self) -> None:
        page = '''
        <div data-geojson="[{&quot;type&quot;:&quot;Feature&quot;,&quot;properties&quot;:{&quot;id&quot;:&quot;5733.2&quot;,&quot;mapRef&quot;:&quot;1539-2304&quot;}},{&quot;type&quot;:&quot;Feature&quot;,&quot;properties&quot;:{&quot;id&quot;:&quot;5733.1&quot;,&quot;mapRef&quot;:&quot;1893-2198&quot;}}]"></div>
        '''
        feature, feature_count, exact_count = MODULE.exact_vendor_feature(page, "5733.1")

        self.assertEqual(feature_count, 2)
        self.assertEqual(exact_count, 1)
        self.assertEqual(feature["properties"]["mapRef"], "1893-2198")

    def test_map_ref_is_y_then_x(self) -> None:
        self.assertEqual(MODULE.parse_map_ref("1086-2100"), (2100.0, 1086.0))


if __name__ == "__main__":
    unittest.main()
