from io import BytesIO
import qrcode


def generate_upi_qr(upi_id: str, payee_name: str, amount: float, note: str) -> BytesIO:
    """Generates a UPI payment QR code image in-memory for the given amount."""
    upi_uri = (
        f"upi://pay?pa={upi_id}&pn={payee_name.replace(' ', '%20')}"
        f"&am={amount}&cu=INR&tn={note.replace(' ', '%20')}"
    )
    img = qrcode.make(upi_uri)
    bio = BytesIO()
    bio.name = "payment_qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


def generate_text_qr(data: str) -> BytesIO:
    """Generates a QR code image encoding plain text (number/amount/reference).

    Used for bKash/Nagad — unlike UPI, they have no public deep-link/intent
    standard, so this QR does NOT auto-open the bKash/Nagad app or prefill an
    amount. It's a scan-to-copy convenience only; the buyer still has to
    manually open bKash/Nagad, send the money, then submit a screenshot.
    """
    img = qrcode.make(data)
    bio = BytesIO()
    bio.name = "payment_qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio
