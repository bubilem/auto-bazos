import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from PIL import Image
    from crawler import collage
except ImportError:  # pragma: no cover
    Image = None


@unittest.skipIf(Image is None, "Pillow not installed")
class CollageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def photos(self, n, size=(1600, 1200)):
        out = []
        for i in range(n):
            p = self.dir / f"{i + 1:02d}.jpg"
            Image.new("RGB", size, (40 * i % 255, 120, 200)).save(p)
            out.append(p)
        return out

    def size(self, path):
        with Image.open(path) as im:
            return im.size

    def test_six_photos_make_2x3_grid(self):
        out = collage.make_collage(self.photos(6), self.dir / "c.jpg")
        w, h = self.size(out)
        self.assertEqual((w, h), (3 * 640 + 4 * 6, 2 * 480 + 3 * 6))

    def test_fewer_photos_shrink_grid(self):
        self.assertEqual(self.size(collage.make_collage(self.photos(2), self.dir / "a.jpg")), (2 * 640 + 3 * 6, 480 + 2 * 6))
        self.assertEqual(self.size(collage.make_collage(self.photos(4), self.dir / "b.jpg"))[1], 2 * 480 + 3 * 6)

    def test_unreadable_file_keeps_slot(self):
        ph = self.photos(3)
        bad = self.dir / "bad.jpg"
        bad.write_bytes(b"not an image")
        out = collage.make_collage([ph[0], bad, ph[2]], self.dir / "c.jpg")
        self.assertEqual(self.size(out)[0], 3 * 640 + 4 * 6)

    def test_portrait_and_tiny_inputs(self):
        ph = self.photos(1, size=(300, 900)) + self.photos(1, size=(20, 20))
        out = collage.make_collage(ph, self.dir / "c.jpg")
        self.assertTrue(out.exists())

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            collage.make_collage([], self.dir / "c.jpg")

    def test_make_collages_splits_and_names(self):
        names = collage.make_collages(self.photos(9), self.dir / "out")
        self.assertEqual(names, ["collage_1.jpg", "collage_2.jpg"])
        self.assertEqual(self.size(self.dir / "out" / "collage_2.jpg")[1], 480 + 2 * 6)  # 3 photos -> 1 row

    def test_make_collages_caps_count(self):
        names = collage.make_collages(self.photos(20), self.dir / "out", per_collage=6, max_collages=2)
        self.assertEqual(len(names), 2)


if __name__ == "__main__":
    unittest.main()
