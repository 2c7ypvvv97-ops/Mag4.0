import io
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

def genera_qr_code_image(testo: str) -> io.BytesIO:
    """Genera l'immagine PNG del QR Code in memoria."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=0
    )
    qr.add_data(testo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def genera_barcode_image(testo: str) -> io.BytesIO:
    """Genera l'immagine PNG del Barcode Code128 in memoria."""
    buffer = io.BytesIO()
    code = Code128(testo, writer=ImageWriter())
    code.write(buffer, options={"write_text": False, "quiet_zone": 1.0, "module_height": 8.0})
    buffer.seek(0)
    return buffer

def genera_pdf_etichetta_singola(
    pn_codice: str, 
    descrizione: str, 
    ubicazione: str, 
    nome_azienda: str = "GESTIONE MAGAZZINO"
) -> bytes:
    """
    Genera un PDF con formato esatto 70x36 mm per stampante termica:
    - Intestazione Azienda
    - Part Number e Ubicazione
    - QR Code e Barcode Code128
    """
    larghezza_pt = 70 * mm
    altezza_pt = 36 * mm

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(larghezza_pt, altezza_pt))

    m_left = 2 * mm
    m_top = altezza_pt - (3 * mm)

    # 1. Intestazione
    c.setFont("Helvetica-Bold", 8)
    c.drawString(m_left, m_top, nome_azienda.upper()[:22])

    c.setLineWidth(0.5)
    c.line(m_left, m_top - (2 * mm), larghezza_pt - m_left, m_top - (2 * mm))

    # 2. Testo PN e Ubicazione
    desc_txt = descrizione if len(descrizione) <= 18 else descrizione[:16] + ".."
    c.setFont("Helvetica-Bold", 8)
    c.drawString(m_left, m_top - (5.5 * mm), f"PN: {pn_codice[:16]}")
    c.setFont("Helvetica", 6.5)
    c.drawString(m_left, m_top - (8.5 * mm), desc_txt)
    c.drawString(m_left, m_top - (11.5 * mm), f"UBIC: {ubicazione[:14]}")

    # 3. QR Code
    try:
        qr_buf = genera_qr_code_image(pn_codice)
        qr_image = ImageReader(qr_buf)
        qr_size = 13 * mm
        qr_x = larghezza_pt - qr_size - (2 * mm)
        qr_y = altezza_pt - qr_size - (3 * mm)
        c.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        pass

    # 4. Barcode Code128
    try:
        barcode_buf = genera_barcode_image(pn_codice)
        barcode_image = ImageReader(barcode_buf)
        bc_w = 64 * mm
        bc_h = 9 * mm
        bc_x = (larghezza_pt - bc_w) / 2
        bc_y = 6 * mm
        c.drawImage(barcode_image, bc_x, bc_y, width=bc_w, height=bc_h)
    except Exception:
        pass

    # 5. Codice in chiaro sotto il barcode
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(larghezza_pt / 2, 2 * mm, pn_codice)

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()

def genera_pdf_lista_riordino(lista_articoli: list, nome_azienda: str = "GESTIONE MAGAZZINO") -> bytes:
    """Genera un Report A4 in PDF con la lista degli articoli sotto scorta da ordinare."""
    from reportlab.lib.pagesizes import A4
    
    larghezza_pt, altezza_pt = A4
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    m_left = 15 * mm
    m_right = larghezza_pt - (15 * mm)
    m_top = altezza_pt - (15 * mm)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(m_left, m_top, nome_azienda.upper())
    
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(m_right, m_top, "LISTA RIORDINO ARTICOLI")

    c.setFont("Helvetica", 9)
    c.drawString(m_left, m_top - (5 * mm), "Report Articoli Sotto Scorta Minima")

    c.setLineWidth(1)
    c.line(m_left, m_top - (8 * mm), m_right, m_top - (8 * mm))

    y = m_top - (18 * mm)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(m_left, y, "Part Number")
    c.drawString(m_left + (45 * mm), y, "Descrizione")
    c.drawString(m_left + (105 * mm), y, "Giacenza")
    c.drawString(m_left + (130 * mm), y, "Scorta Min.")
    c.drawString(m_left + (155 * mm), y, "Fornitore")

    c.line(m_left, y - 2, m_right, y - 2)

    c.setFont("Helvetica", 8)
    for art in lista_articoli:
        y -= 5 * mm
        if y < 20 * mm:
            c.showPage()
            y = altezza_pt - 20 * mm
            c.setFont("Helvetica", 8)

        c.drawString(m_left, y, str(art.get('pn_codice', 'N/D'))[:20])
        c.drawString(m_left + (45 * mm), y, str(art.get('descrizione', 'N/D'))[:32])
        c.drawString(m_left + (105 * mm), y, str(art.get('quantita_disponibile', '0')))
        c.drawString(m_left + (130 * mm), y, str(art.get('scorta_minima', '0')))
        c.drawString(m_left + (155 * mm), y, str(art.get('fornitore_abituale', 'N/D'))[:18])

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()
    
def genera_pdf_inventario_cartaceo(lista_ubicazioni: list, nome_azienda: str = "GESTIONE MAGAZZINO") -> bytes:
    """Genera un Report A4 in PDF per l'inventario fisico cartaceo, ordinato per ubicazione, con spazi per il conteggio."""
    from reportlab.lib.pagesizes import A4
    
    larghezza_pt, altezza_pt = A4
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    m_left = 15 * mm
    m_right = larghezza_pt - (15 * mm)
    m_top = altezza_pt - (15 * mm)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(m_left, m_top, nome_azienda.upper())
    
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(m_right, m_top, "FOGLIO DI CONTEGGIO INVENTARIO")

    c.setFont("Helvetica", 9)
    c.drawString(m_left, m_top - (5 * mm), "Elenco completo ordinato per ubicazione per riscontro fisico")

    c.setLineWidth(1)
    c.line(m_left, m_top - (8 * mm), m_right, m_top - (8 * mm))

    y = m_top - (18 * mm)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(m_left, y, "Ubicazione")
    c.drawString(m_left + (35 * mm), y, "Part Number")
    c.drawString(m_left + (80 * mm), y, "Descrizione")
    c.drawString(m_left + (145 * mm), y, "Teorico")
    c.drawString(m_left + (165 * mm), y, "Conteggio Reale")

    c.line(m_left, y - 2, m_right, y - 2)

    c.setFont("Helvetica", 8)
    for art in lista_ubicazioni:
        y -= 6 * mm
        if y < 20 * mm:
            c.showPage()
            y = altezza_pt - 20 * mm
            c.setFont("Helvetica", 8)

        c.drawString(m_left, y, str(art.get('ubicazione', 'N/D'))[:18])
        c.drawString(m_left + (35 * mm), y, str(art.get('pn_codice', 'N/D'))[:20])
        c.drawString(m_left + (80 * mm), y, str(art.get('descrizione', 'N/D'))[:30])
        c.drawString(m_left + (145 * mm), y, str(art.get('quantita_disponibile', '0')))
        # Casella vuota tratteggiata per il conteggio a penna
        c.rect(m_left + (165 * mm), y - 1, 25 * mm, 5 * mm, stroke=1, fill=0)

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()    