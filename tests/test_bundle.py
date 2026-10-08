import json
import shutil
import tempfile
import unittest
from pathlib import Path

from explainer.bundle.pack import pack_bundle
from explainer.bundle.schema import SCHEMA_ID, ValidationError, validate_bundle, validate_manifest
from explainer.util import REPO_ROOT

EXAMPLE = REPO_ROOT / "examples" / "how-natural-gas-gets-to-your-home"
TINY = REPO_ROOT / "tests" / "fixtures" / "tiny-bundle"


class ManifestTests(unittest.TestCase):
    def test_valid_minimal(self):
        man = validate_manifest({
            "schema": SCHEMA_ID,
            "title": "Hello",
            "slug": "hello-world",
        })
        self.assertEqual(man.voice, "kokoro:af_heart")
        self.assertEqual(man.output_name, "hello-world.mp4")
        self.assertEqual(man.size, (1920, 1080))

    def test_rejects_wrong_schema_and_slug(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_manifest({"schema": "nope", "title": "T", "slug": "Not Valid"})
        joined = " ".join(ctx.exception.errors)
        self.assertIn("schema", joined)
        self.assertIn("slug", joined)

    def test_rejects_bad_voice(self):
        with self.assertRaises(ValidationError):
            validate_manifest({"schema": SCHEMA_ID, "title": "T", "slug": "t", "voice": "nope/not-a-voice"})


class BundleValidationTests(unittest.TestCase):
    def test_example_validates(self):
        man = validate_bundle(EXAMPLE)
        self.assertEqual(man.slug, "how-natural-gas-gets-to-your-home")
        self.assertIn("art_gas.py", man.modules)

    def test_tiny_validates(self):
        man = validate_bundle(TINY)
        self.assertEqual(man.slug, "tiny-test-bundle")

    def test_missing_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValidationError) as ctx:
                validate_bundle(Path(td))
            self.assertTrue(any("manifest.yaml" in e for e in ctx.exception.errors))

    def test_missing_scene_function(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "manifest.yaml").write_text(
                "schema: explainer-bundle/v1\ntitle: X\nslug: x-bundle\n"
                "script: script.py\nscenes: scenes.py\n"
            )
            (root / "script.py").write_text(
                'SCENES = [("hook", "H", [("Hi.", None)])]\n'
            )
            (root / "scenes.py").write_text("SCENE_FUNCS = {}\n")
            with self.assertRaises(ValidationError) as ctx:
                validate_bundle(root)
            self.assertTrue(any("hook" in e for e in ctx.exception.errors))

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "manifest.yaml").write_text(
                "schema: explainer-bundle/v1\ntitle: X\nslug: x-bundle\n"
                "script: ../secret.py\nscenes: scenes.py\n"
            )
            (root / "scenes.py").write_text("SCENE_FUNCS = dict(hook=hook)\ndef hook(c,t,T): pass\n")
            with self.assertRaises(ValidationError):
                validate_bundle(root)

    def test_pack_roundtrip(self):
        dest = pack_bundle(TINY)
        self.addCleanup(dest.unlink)
        self.assertTrue(dest.is_file())
        self.assertGreater(dest.stat().st_size, 200)
        import tarfile
        with tarfile.open(dest, "r:gz") as tf:
            names = tf.getnames()
        self.assertTrue(any(n.endswith("manifest.yaml") for n in names))
        self.assertFalse(any(n.endswith(".mp4") for n in names))


class SmokeRenderTests(unittest.TestCase):
    """Render a couple of seconds of the example (hook) at low resolution.

    Needs ffmpeg and the bundle extras (skia-python). Skipped when skia is missing
    so `make test` still passes on a writer-only install.
    """

    def test_example_hook_lowres(self):
        try:
            import skia  # noqa: F401
        except ImportError:
            self.skipTest("skia-python not installed (make setup-bundle)")
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not on PATH")
        from explainer.cli import main
        out_root = Path(tempfile.mkdtemp(prefix="explainer-smoke-"))
        self.addCleanup(lambda: shutil.rmtree(out_root, ignore_errors=True))
        # Isolate caches under the temp tree by chdir... no: Context uses REPO_ROOT.
        # Use --tag so we don't clobber a real build, silence voice, 2 seconds, 480x270.
        rc = main([
            "build", str(EXAMPLE),
            "--voice", "silence",
            "--scene", "hook",
            "--width", "480",
            "--height", "270",
            "--max-seconds", "2",
            "--workers", "1",
            "--asr", "off",
            "--no-deliver",
            "--tag", "smoke",
            "--share-max-mb", "5",
        ])
        self.assertEqual(rc, 0)
        out_dir = REPO_ROOT / "out" / "how-natural-gas-gets-to-your-home"
        matches = list(out_dir.glob("16x9-smoke*/how-natural-gas-gets-to-your-home.mp4"))
        self.assertTrue(matches, f"no smoke MP4 under {out_dir}")
        mp4 = matches[0]
        self.assertGreater(mp4.stat().st_size, 1000)
        qa = mp4.parent / "qa.json"
        self.assertTrue(qa.is_file())
        report = json.loads(qa.read_text())
        self.assertEqual(report["video"]["width"], 480)
        self.assertEqual(report["video"]["height"], 270)
        self.assertLessEqual(report["duration_s"], 8.0)
        self.assertTrue((mp4.parent / "contact_sheet.jpg").is_file())
