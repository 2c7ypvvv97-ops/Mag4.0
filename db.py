import sqlite3
import os
import hashlib

DB_NAME = "magazzino.db"

def get_db_connection():
    """Connessione con Timeout 20s e WAL mode per prestazioni elevate."""
    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

# --- SECURITY PASSWORDS ---
def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return hashed.hex(), salt.hex()

def verify_password(stored_hash: str, stored_salt: str, password_provided: str) -> bool:
    salt = bytes.fromhex(stored_salt)
    hashed_provided = hashlib.pbkdf2_hmac("sha256", password_provided.encode("utf-8"), salt, 100000).hex()
    return hashed_provided == stored_hash

# --- INIZIALIZZAZIONE STRUTTURA DATI ---
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Utenti del Sistema[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            nome_completo TEXT NOT NULL,
            ruolo TEXT NOT NULL,
            attivo INTEGER DEFAULT 1,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM utenti")
    if cursor.fetchone()[0] == 0:
        pwd_hash, salt = hash_password("admin123")
        cursor.execute("""
            INSERT INTO utenti (username, password_hash, salt, nome_completo, ruolo, attivo)
            VALUES (?, ?, ?, ?, ?, 1)
        """, ("admin", pwd_hash, salt, "Amministratore Magazzino", "Admin"))

    # 2. Anagrafica Articoli (Part Numbers)[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS part_numbers (
            pn_codice TEXT PRIMARY KEY,
            descrizione TEXT NOT NULL,
            categoria TEXT DEFAULT 'Generico',
            ubicazione TEXT DEFAULT 'NON ASSEGNATA',
            scorta_minima INTEGER DEFAULT 0,
            lotto_riordino INTEGER DEFAULT 1,
            fornitore_abituale TEXT,
            note TEXT
        )
    """)

    # 3. Giacenze Live Magazzino[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazzino_quantita (
            pn_codice TEXT PRIMARY KEY,
            quantita_disponibile INTEGER DEFAULT 0,
            ubicazione TEXT,
            operatore TEXT,
            data_ultimo_aggiornamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pn_codice) REFERENCES part_numbers(pn_codice) ON DELETE CASCADE
        )
    """)

    # 4. Anagrafica Clienti Leggera[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clienti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codice_cliente TEXT UNIQUE NOT NULL,
            ragione_sociale TEXT NOT NULL,
            referente TEXT,
            note TEXT,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5. Registro Unificato Movimenti & Audit Log (Aggiornato con campi DDT)[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS storico_movimenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pn_codice TEXT NOT NULL,
            tipo_movimento TEXT CHECK(tipo_movimento IN ('CARICO', 'SCARICO', 'RETTIFICA')) NOT NULL,
            quantita INTEGER NOT NULL,
            causale TEXT,
            codice_cliente TEXT,
            numero_ddt TEXT,
            data_ddt TEXT,
            ubicazione TEXT NOT NULL,
            operatore TEXT NOT NULL,
            note TEXT,
            data_ora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pn_codice) REFERENCES part_numbers(pn_codice),
            FOREIGN KEY (codice_cliente) REFERENCES clienti(codice_cliente)
        )
    """)

    # 6. Tabelle per Gestione Inventario in Bozza (Flusso Tablet -> Admin)[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario_sessioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descrizione TEXT,
            operatore_avvio TEXT,
            stato TEXT CHECK(stato IN ('APERTA', 'APPROVATA', 'ANNULLATA')) DEFAULT 'APERTA',
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_chiusura TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario_righe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessione_id INTEGER NOT NULL,
            pn_codice TEXT NOT NULL,
            ubicazione TEXT,
            giacenza_teorica INTEGER NOT NULL,
            quantita_reale INTEGER DEFAULT 0,
            contato INTEGER DEFAULT 0,
            FOREIGN KEY (sessione_id) REFERENCES inventario_sessioni(id) ON DELETE CASCADE,
            FOREIGN KEY (pn_codice) REFERENCES part_numbers(pn_codice)
        )
    """)

    # 7. Tabelle per Liste Batch (Carico e Scarico Massivo con Spunte)[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS liste_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT CHECK(tipo IN ('CARICO', 'SCARICO')) NOT NULL,
            partner_nome TEXT,
            numero_ddt TEXT,
            data_ddt TEXT,
            stato TEXT CHECK(stato IN ('APERTA', 'COMPLETATA', 'ANNULLATA')) DEFAULT 'APERTA',
            operatore TEXT,
            note TEXT,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS liste_batch_righe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lista_id INTEGER NOT NULL,
            pn_codice TEXT NOT NULL,
            quantita INTEGER NOT NULL,
            ubicazione TEXT,
            spuntato INTEGER DEFAULT 0,
            FOREIGN KEY (lista_id) REFERENCES liste_batch(id) ON DELETE CASCADE,
            FOREIGN KEY (pn_codice) REFERENCES part_numbers(pn_codice)
        )
    """)

    # Indici per Velocità di Ricerca[cite: 1]
    indici = [
        "CREATE INDEX IF NOT EXISTS idx_pn_descrizione ON part_numbers(descrizione);",
        "CREATE INDEX IF NOT EXISTS idx_pn_categoria ON part_numbers(categoria);",
        "CREATE INDEX IF NOT EXISTS idx_pn_ubicazione ON part_numbers(ubicazione);",
        "CREATE INDEX IF NOT EXISTS idx_magazzino_pn ON magazzino_quantita(pn_codice);",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_pn ON storico_movimenti(pn_codice);",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_tipo ON storico_movimenti(tipo_movimento);",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_data ON storico_movimenti(data_ora);",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_ddt ON storico_movimenti(numero_ddt);"
    ]
    for idx_sql in indici:
        cursor.execute(idx_sql)

    conn.commit()
    conn.close()

# --- UTILITIES UTENTI ---
def autentica_utente(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password_hash, salt, nome_completo, ruolo, attivo 
        FROM utenti WHERE username = ? AND attivo = 1
    """, (username,))
    user = cursor.fetchone()
    conn.close()

    if user and verify_password(user["password_hash"], user["salt"], password):
        return dict(user)
    return None

def get_tutti_utenti():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, nome_completo, ruolo, attivo FROM utenti ORDER BY id ASC")
    utenti = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return utenti

def crea_utente(username, password, nome_completo, ruolo):
    pwd_hash, salt = hash_password(password)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO utenti (username, password_hash, salt, nome_completo, ruolo, attivo)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (username, pwd_hash, salt, nome_completo, ruolo))
        conn.commit()
        return True, "Utente creato con successo!"
    except sqlite3.IntegrityError:
        return False, "Username già esistente."
    finally:
        conn.close()

def aggiorna_stato_utente(username, nuovo_ruolo, nuovo_stato_attivo):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE utenti 
            SET ruolo = ?, attivo = ? 
            WHERE username = ?
        """, (nuovo_ruolo, nuovo_stato_attivo, username))
        conn.commit()
        return True, f"Utente '{username}' aggiornato con successo!"
    except Exception as e:
        return False, f"Errore durante l'aggiornamento: {e}"
    finally:
        conn.close()