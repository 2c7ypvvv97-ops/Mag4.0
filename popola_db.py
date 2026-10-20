import sqlite3
import random
from datetime import datetime, timedelta
from db import get_db_connection, init_db

def popola_dati_demo():
    # Inizializza le tabelle se non esistono
    init_db()
    
    conn = get_db_connection()
    if not conn:
        print("❌ Impossibile connettersi al database.")
        return

    cursor = conn.cursor()

    print("⏳ Inserimento dati demo in corso...")

    # 1. Inserimento Clienti
    clienti_demo = [
        ("CLI-001", "Acme Corporation S.r.l.", "Mario Rossi", "Cliente principale - Fatturazione mensile"),
        ("CLI-002", "TechSolutions SpA", "Laura Bianchi", "Consegne urgenti presso sede centrale"),
        ("CLI-003", "Officine Meccaniche Ridolfi", "Giuseppe Ridolfi", "Pagamento a 30gg"),
        ("CLI-004", "Logistica & Servizi S.n.c.", "Elena Verdi", "Ritiro con mezzo proprio"),
        ("CLI-005", "Studio Tecnico Associato", "Ing. Andrea Neri", "Cliente occasionale")
    ]

    for cli in clienti_demo:
        cursor.execute("""
            INSERT INTO clienti (codice_cliente, ragione_sociale, referente, note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(codice_cliente) DO UPDATE SET
                ragione_sociale=EXCLUDED.ragione_sociale,
                referente=EXCLUDED.referente,
                note=EXCLUDED.note
        """, cli)

    # 2. Inserimento Articoli (Part Numbers)
    articoli_demo = [
        ("PN-ELET-001", "Scheda Madre Micro-ATX B550", "Elettronica", "SCAFFALE-A1-R1", 5, 2, "TechComponenti Ltd", "Componente sensibile electrostatico"),
        ("PN-ELET-002", "Alimentatore 650W 80 Plus Gold", "Elettronica", "SCAFFALE-A1-R2", 10, 5, "TechComponenti Ltd", "Garanzia 5 anni"),
        ("PN-MECC-101", "Cuscinetto a Sfera 6204-2RSH", "Meccanica", "SCAFFALE-B2-R3", 20, 10, "Rullini & Cuscinetti Srl", "Acciaio inox"),
        ("PN-MECC-102", "Cinghia Trapezoidale A-30", "Meccanica", "SCAFFALE-B2-R4", 8, 4, "Rullini & Cuscinetti Srl", "Profilo classico"),
        ("PN-VITI-501", "Vite TCEI M6x20 Inox A2 (100pz)", "Minuteria", "CESTOTTO-C1", 15, 10, "Bulloneria Friulana", "Confezione da 100 pezzi"),
        ("PN-VITI-502", "Dado Autobloccante M6 Inox (100pz)", "Minuteria", "CESTOTTO-C2", 12, 10, "Bulloneria Friulana", "Confezione da 100 pezzi"),
        ("PN-IMB-001", "Scatola Cartone Onda Doppia 40x30x30", "Imballaggio", "PALLET-P1", 50, 25, "Cartonificio Padano", "Pallet da 200pz"),
        ("PN-IMB-002", "Nastro Adesivo PPL Marrone 50mmx66m", "Imballaggio", "PALLET-P2", 30, 12, "Cartonificio Padano", "Scatole da 36 rotoli"),
        ("PN-CANC-01", "Carta A4 80g Ream (500 fogli)", "Cancelleria", "ARMADIO-U1", 10, 5, "Ufficio Express", "Carta FSC"),
        ("PN-CANC-02", "Toner Nero Compatibile HP 83A", "Cancelleria", "ARMADIO-U2", 3, 2, "Ufficio Express", "Resa 1500 pagine")
    ]

    for art in articoli_demo:
        cursor.execute("""
            INSERT INTO part_numbers (pn_codice, descrizione, categoria, ubicazione, scorta_minima, lotto_riordino, fornitore_abituale, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pn_codice) DO UPDATE SET
                descrizione=EXCLUDED.descrizione,
                categoria=EXCLUDED.categoria,
                ubicazione=EXCLUDED.ubicazione,
                scorta_minima=EXCLUDED.scorta_minima,
                lotto_riordino=EXCLUDED.lotto_riordino,
                fornitore_abituale=EXCLUDED.fornitore_abituale,
                note=EXCLUDED.note
        """, art)

    # 3. Giacenze Live
    giacenze = {
        "PN-ELET-001": 2,   # ⚠️ SOTTO SCORTA (Min: 5)
        "PN-ELET-002": 14,
        "PN-MECC-101": 35,
        "PN-MECC-102": 4,   # ⚠️ SOTTO SCORTA (Min: 8)
        "PN-VITI-501": 18,
        "PN-VITI-502": 8,   # ⚠️ SOTTO SCORTA (Min: 12)
        "PN-IMB-001": 120,
        "PN-IMB-002": 45,
        "PN-CANC-01": 12,
        "PN-CANC-02": 1    # ⚠️ SOTTO SCORTA (Min: 3)
    }

    ubicazioni = {
        "PN-ELET-001": "SCAFFALE-A1-R1", "PN-ELET-002": "SCAFFALE-A1-R2",
        "PN-MECC-101": "SCAFFALE-B2-R3", "PN-MECC-102": "SCAFFALE-B2-R4",
        "PN-VITI-501": "CESTOTTO-C1",    "PN-VITI-502": "CESTOTTO-C2",
        "PN-IMB-001":  "PALLET-P1",      "PN-IMB-002":  "PALLET-P2",
        "PN-CANC-01":  "ARMADIO-U1",     "PN-CANC-02":  "ARMADIO-U2"
    }

    for pn, qta in giacenze.items():
        cursor.execute("""
            INSERT INTO magazzino_quantita (pn_codice, quantita_disponibile, ubicazione, operatore, data_ultimo_aggiornamento)
            VALUES (?, ?, ?, 'Amministratore Magazzino', CURRENT_TIMESTAMP)
            ON CONFLICT(pn_codice) DO UPDATE SET
                quantita_disponibile=EXCLUDED.quantita_disponibile,
                ubicazione=EXCLUDED.ubicazione,
                data_ultimo_aggiornamento=CURRENT_TIMESTAMP
        """, (pn, qta, ubicazioni[pn]))

    # 4. Storico Movimenti fittizi con DDT integrati per gli ultimi 15 giorni
    causali_scarico = ["Vendita Cliente", "Consumo Interno", "Manutenzione"]
    operatori = ["Amministratore Magazzino", "Mario Magazziniere"]
    clienti_codici = ["CLI-001", "CLI-002", "CLI-003", "CLI-004", "CLI-005"]

    for i in range(15):
        data_mov_dt = datetime.now() - timedelta(days=i)
        data_mov = data_mov_dt.strftime("%Y-%m-%d %H:%M:%S")
        data_ddt_str = data_mov_dt.strftime("%Y-%m-%d")
        
        pn_casuale = random.choice(list(giacenze.keys()))
        tipo = random.choice(["CARICO", "SCARICO", "SCARICO", "RETTIFICA"])
        
        qta = random.randint(1, 10)
        cli = random.choice(clienti_codici) if tipo == "SCARICO" else None
        
        # Generazione DDT fittizi in base al tipo movimento
        num_ddt = None
        data_ddt = None
        if tipo == "SCARICO":
            num_ddt = f"DDT-OUT-{1000 + i}"
            data_ddt = data_ddt_str
            causale = random.choice(causali_scarico)
        elif tipo == "CARICO":
            num_ddt = f"BOLLETTA-IN-{500 + i}"
            data_ddt = data_ddt_str
            causale = "Fornitura periodica"
        else:
            causale = "Inventario fisso"

        op = random.choice(operatori)

        cursor.execute("""
            INSERT INTO storico_movimenti (pn_codice, tipo_movimento, quantita, causale, codice_cliente, numero_ddt, data_ddt, ubicazione, operatore, note, data_ora)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Inserimento automatico demo con DDT', ?)
        """, (pn_casuale, tipo, qta, causale, cli, num_ddt, data_ddt, ubicazioni[pn_casuale], op, data_mov))

    conn.commit()
    conn.close()
    print("✅ Database popolato con successo (inclusi i riferimenti DDT nelle movimentazioni)! Ora puoi aprire Streamlit.")

if __name__ == "__main__":
    popola_dati_demo()