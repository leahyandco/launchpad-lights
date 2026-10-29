"""Write the tray icon as a multi-size .ico for the exe. Usage: python make_icon.py out.ico"""
import sys
from pathlib import Path

from lpctl.tray import make_icon

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
make_icon(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Wrote {out}")
