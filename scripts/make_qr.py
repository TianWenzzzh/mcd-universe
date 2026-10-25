"""生成分享卡用的二维码（纯标准库写 PNG，运行时不引入任何依赖）。

用法：python scripts/make_qr.py "<url>" <out.png>
产物：白底黑码 PNG，供 templates/starmap.html 以 base64 内嵌。
"""
from __future__ import annotations

import struct
import sys
import zlib

import qrcode

MODULE_PX = 8


def write_png(path: str, matrix: list[list[bool]]) -> None:
    """把 0/1 矩阵写成白底黑块的灰度 PNG（无第三方图像库）。"""
    n = len(matrix)
    size = n * MODULE_PX
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        my = y // MODULE_PX
        for x in range(size):
            dark = matrix[my][x // MODULE_PX]
            row.append(0 if dark else 255)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)  # 8-bit grayscale
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://tianwenzzzh.github.io/mcd-universe/demo/"
    out = sys.argv[2] if len(sys.argv) > 2 else "docs/assets/qr.png"
    qr = qrcode.QRCode(border=0, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    write_png(out, matrix)
    print(f"QR written: {out} ({len(matrix)}x{len(matrix)} modules, {len(matrix) * MODULE_PX}px)")


if __name__ == "__main__":
    main()
