"""Show what is actually AT and AROUND the seam in each device output.

Recovered from diag_real24:
  output 5c2e4c57  h=3384  seam k=2606  d=778   -> bottom kept = 16
  output e538adcb  h=3445  seam k=2397  d=1048  -> bottom kept = 225
  output fe1aa8c1  h=3485  seam k=2376  d=1109  -> bottom kept = 246

Suspicion: the bottom overlay height is inconsistent (16 / 225 / 246), so in
some outputs the chat input bar + home indicator is baked into the middle of
the long image, and in others real content got cut.

Crop a window around each seam and save as PNG for visual inspection, and
also print how many rows around the seam look like the bottom bar
(dark uniform rows / the white home indicator pill).

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

OUT_DIR = r"E:\DeepSeek\本地电脑\splice\samples"
DST = r"E:\DeepSeek\本地电脑\splice\samples\_seam"

SEAMS = {
    "5c2e4c57b2b2c79316e7c74c6bb1b8b8.jpg": (2606, 778),
    "e538adcbf64763cef63c4034298a69f4.jpg": (2397, 1048),
    "fe1aa8c112f25952bc693e3567edbe42.jpg": (2376, 1109),
}


def main():
    os.makedirs(DST, exist_ok=True)
    for fn, (k, d) in SEAMS.items():
        p = os.path.join(OUT_DIR, fn)
        im = Image.open(p).convert("RGB")
        a = np.asarray(im).astype(np.int16)
        h = a.shape[0]
        print("=== %s h=%d seam k=%d d=%d bottom_kept=%d"
              % (fn[:8], h, k, d, 2622 - k))

        # 1) crop window around seam
        y0 = max(0, k - 500)
        y1 = min(h, k + 500)
        im.crop((0, y0, im.width, y1)).save(
            os.path.join(DST, "%s_seam.png" % fn[:8]))
        print("   seam crop rows %d..%d" % (y0, y1))

        # 2) detect the white home indicator pill (bright horizontal run near
        #    the horizontal centre, ~420px wide) inside the long image
        cx0, cx1 = 393, 813
        for y in range(0, h):
            row = a[y, cx0:cx1]
            bright = (row.mean(axis=1) > 200).mean()
            if bright > 0.85:
                print("   home-pill-like row at y=%d (mean=%.1f)"
                      % (y, row.mean()))
                break
        else:
            print("   no home-pill row found")

        # 3) find uniform dark bands (input bar background) longer than 40 rows
        dark = (a[:, 60:1140].mean(axis=(1, 2)) < 40)
        runs = []
        st = None
        for y in range(h):
            if dark[y]:
                if st is None:
                    st = y
            else:
                if st is not None and y - st >= 40:
                    runs.append((st, y))
                st = None
        if st is not None and h - st >= 40:
            runs.append((st, h))
        print("   dark uniform bands >=40 rows: %s" % (runs[:8],))
        print("")


if __name__ == "__main__":
    main()
