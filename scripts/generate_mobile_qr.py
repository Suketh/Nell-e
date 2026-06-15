from pathlib import Path
import sys

import qrcode


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "exp://192.168.0.119:8081"
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/run/expo-mobile-qr.png")
    output.parent.mkdir(parents=True, exist_ok=True)

    image = qrcode.make(target)
    image.save(output)
    print(f"[qr] saved {output} for {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
