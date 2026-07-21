"""
qr_decode.py
-------------
Decodes QR codes from an uploaded image (e.g. a QR code on a digital
prescription) into plain text, which is then fed into the same digital
prescription parser used for PDFs.

Requires the 'pyzbar' Python package AND a system library called 'zbar'.
If either is missing, this module fails gracefully with a clear error
message instead of crashing the whole server - see README for install steps
per operating system (Mac/Linux/Windows).
"""

import io


class QRDecodeError(Exception):
    pass


def decode_qr_from_image(image_bytes: bytes) -> str:
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image
    except ImportError as e:
        raise QRDecodeError(
            "QR scanning needs the 'pyzbar' package and the system 'zbar' library, "
            "which aren't installed. See the README's QR Code Setup section for exact install steps."
        ) from e

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception:
        raise QRDecodeError("Could not read this file as an image.")

    try:
        results = decode(image)
    except Exception as e:
        # This usually means the zbar *system library* (not just the Python package) is missing
        raise QRDecodeError(
            "The zbar system library isn't installed on this computer. "
            "See the README's QR Code Setup section for exact install steps."
        ) from e

    if not results:
        raise QRDecodeError("No QR code could be found in this image. Try a clearer, closer photo.")

    # If multiple QR codes are found, use the first one
    return results[0].data.decode("utf-8", errors="replace")
