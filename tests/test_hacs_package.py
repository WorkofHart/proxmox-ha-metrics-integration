"""Check that a published GitHub release contains HACS-installable metadata."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "proxmox_metrics"


class HacsPackageTests(unittest.TestCase):
    def test_root_hacs_metadata(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(hacs["name"], "Proxmox Metrics")

    def test_manifest_required_fields(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        for key in ("domain", "documentation", "issue_tracker", "codeowners", "name", "version"):
            with self.subTest(key=key):
                self.assertTrue(manifest[key])
        self.assertEqual(manifest["domain"], INTEGRATION.name)

    def test_brand_icon_exists(self):
        icon = (INTEGRATION / "brand" / "icon.png").read_bytes()
        self.assertTrue(icon.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
