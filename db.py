import sqlite3
import bcrypt
import secrets
import string
from datetime import datetime

DB_NAME = "magazzino.db"

def get_db_connection():
    """Restituisce una connessione al database SQLite configurata con Row factory."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Errore di connessione al database: {e}")
        return None

def init_db():
    """Inizializza tutte le tabelle del database e gli indici di performance se non esistono."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Tabella Zone (Gestione logistica per aree)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS zone (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome_zona TEXT UNIQUE COLLATE NOCASE,
                    descrizione TEXT
                )
            """)

            # Tabella Part Numbers (Articoli)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS part_numbers (
                    pn_codice TEXT PRIMARY KEY,
                    descrizione TEXT,
                    categoria TEXT,
                    ubicazione TEXT,
                    zona TEXT DEFAULT 'Generale',
                    scorta_minima INTEGER DEFAULT 5,
                    lotto_riordino INTEGER DEFAULT 10,
                    fornitore_abituale TEXT,
                    alta_rotazione INTEGER DEFAULT 0
                )
            """)

            # Tabella Giacenze Magazzino
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS magazzino_quantita (
                    pn_codice TEXT PRIMARY KEY,
                    quantita_disponibile INTEGER DEFAULT 0,
                    ubicazione TEXT,
                    zona TEXT DEFAULT 'Generale',
                    operatore TEXT,
                    data_ultimo_aggiornamento TIMESTAMP,
                    FOREIGN KEY (pn_codice) REFERENCES part_numbers(pn_codice)
                )
            """)

            # Tabella Clienti
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clienti (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codice_cliente TEXT UNIQUE,
                    ragione_sociale TEXT,
                    partita_iva TEXT,
                    indirizzo TEXT,
                    referente TEXT,
                    telefono TEXT,
                    email TEXT,
                    note TEXT
                )
            """)

            # Tabella Liste Batch (Testata delle liste)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS liste_batch (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome_lista TEXT,
                    tipo_operazione TEXT,
                    stato TEXT DEFAULT 'Aperta',
                    operatore TEXT,
                    data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabella Dettaglio Liste Batch (Righe della lista)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dettaglio_liste_batch (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_lista INTEGER,
                    pn_codice TEXT,
                    quantita_richiesta INTEGER,
                    FOREIGN KEY (id_lista) REFERENCES liste_batch(id)
                )
            """)

            # Tabella Sessioni Inventario (Gestione conteggi e inventario da tablet)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_sessioni (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome_sessione TEXT,
                    stato TEXT DEFAULT 'Aperta',
                    operatore TEXT,
                    data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabella Dettaglio Sessioni Inventario (Righe scansionate/contate)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario_dettagli (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_sessione INTEGER,
                    pn_codice TEXT,
                    quantita_rilevata INTEGER,
                    ubicazione TEXT,
                    zona TEXT DEFAULT 'Generale',
                    operatore TEXT,
                    data_rilevazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (id_sessione) REFERENCES inventario_sessioni(id)
                )
            """)

            # Tabella Storico Movimenti (Audit Trail Immutabile - Append Only)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS storico_movimenti (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pn_codice TEXT,
                    tipo_movimento TEXT,
                    quantita INTEGER,
                    causale TEXT,
                    codice_cliente TEXT,
                    numero_ddt TEXT,
                    data_ddt TEXT,
                    ubicazione TEXT,
                    zona TEXT DEFAULT 'Generale',
                    operatore TEXT,
                    note TEXT,
                    data_ora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabella Utenti con campi di sicurezza avanzati
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS utenti (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    nome_completo TEXT,
                    ruolo TEXT,
                    tentativi_falliti INTEGER DEFAULT 0,
                    account_bloccato INTEGER DEFAULT 0,
                    cambio_password_richiesto INTEGER DEFAULT 0
                )
            """)

            # Tabella Log Amministrazione (Tracciamento azioni critiche Admin)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS log_amministrazione (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username_admin TEXT,
                    azione TEXT,
                    dettagli TEXT,
                    data_ora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- INDICI SQL PER OTTIMIZZAZIONE PERFORMANCE (Migliaia di SKU) ---
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_part_numbers_codice ON part_numbers(pn_codice);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_part_numbers_ubicazione ON part_numbers(ubicazione);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_part_numbers_zona ON part_numbers(zona);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_part_numbers_categoria ON part_numbers(categoria);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_storico_movimenti_data ON storico_movimenti(data_ora);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_storico_movimenti_pn ON storico_movimenti(pn_codice);")

            conn.commit()

            # Inserimento zona di default se la tabella è vuota
            cursor.execute("SELECT COUNT(*) as cnt FROM zone")
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute("INSERT OR IGNORE INTO zone (nome_zona, descrizione) VALUES (?, ?)", ("Generale", "Zona predefinita di magazzino"))
                conn.commit()

            # Controllo e creazione utente Admin di default se la tabella è vuota
            cursor.execute("SELECT COUNT(*) as cnt FROM utenti")
            if cursor.fetchone()['cnt'] == 0:
                pwd_default = "admin123"
                hashed = bcrypt.hashpw(pwd_default.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute("""
                    INSERT INTO utenti (username, password_hash, nome_completo, ruolo, tentativi_falliti, account_bloccato, cambio_password_richiesto)
                    VALUES (?, ?, ?, ?, 0, 0, 1)
                """, ("admin", hashed, "Amministratore Sistema", "Admin"))
                conn.commit()

        except Exception as e:
            print(f"Errore inizializzazione DB: {e}")
        finally:
            conn.close()

# --- FUNZIONI DI GESTIONE ZONE ---
def get_tutte_zone():
    """Restituisce l'elenco di tutte le zone censite."""
    conn = get_db_connection()
    zone = ["Generale"]
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT nome_zona FROM zone ORDER BY nome_zona ASC")
            res = cursor.fetchall()
            if res:
                zone = [r["nome_zona"] for r in res]
        except Exception as e:
            print(f"Errore lettura zone: {e}")
        finally:
            conn.close()
    return zone

def registra_zona_al_volo(nome_zona: str):
    """Aggiunge automaticamente una nuova zona se non esiste già (evitando duplicati case-insensitive)."""
    if not nome_zona or not nome_zona.strip():
        return "Generale"
    zona_pulita = nome_zona.strip().upper()
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO zone (nome_zona) VALUES (?)", (zona_pulita,))
            conn.commit()
        except Exception as e:
            print(f"Errore registrazione zona al volo: {e}")
        finally:
            conn.close()
    return zona_pulita

def bonifica_e_unisci_zone(vecchia_zona: str, nuova_zona: str, admin_esecutore: str = "admin"):
    """Permette di rinominare o unire una zona errata/duplicata in un'unica zona corretta su tutti gli articoli."""
    conn = get_db_connection()
    if not conn:
        return False, "Errore di connessione al database."
    try:
        cursor = conn.cursor()
        nuova_pulita = nuova_zona.strip().upper()
        
        # Assicura che la nuova zona esista
        cursor.execute("INSERT OR IGNORE INTO zone (nome_zona) VALUES (?)", (nuova_pulita,))
        
        # Aggiorna tutte le tabelle collegate
        cursor.execute("UPDATE part_numbers SET zona = ? WHERE zona = ?", (nuova_pulita, vecchia_zona))
        cursor.execute("UPDATE magazzino_quantita SET zona = ? WHERE zona = ?", (nuova_pulita, vecchia_zona))
        cursor.execute("UPDATE storico_movimenti SET zona = ? WHERE zona = ?", (nuova_pulita, vecchia_zona))
        cursor.execute("UPDATE inventario_dettagli SET zona = ? WHERE zona = ?", (nuova_pulita, vecchia_zona))
        
        # Rimuove la vecchia zona dalla tabella zone se diversa
        if vecchia_zona != nuova_pulita:
            cursor.execute("DELETE FROM zone WHERE nome_zona = ?", (vecchia_zona,))
            
        conn.commit()
        registra_log_admin(admin_esecutore, "BONIFICA_ZONA", f"Unita/Rinominata zona '{vecchia_zona}' in '{nuova_pulita}'.")
        return True, f"Zona bonificata con successo in '{nuova_pulita}'."
    except Exception as e:
        return False, f"Errore durante la bonifica: {e}"
    finally:
        conn.close()

def hash_password(password: str) -> str:
    """Genera l'hash sicuro della password tramite bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verifica_password(password: str, hashed: str) -> bool:
    """Verifica una password in chiaro rispetto al suo hash bcrypt."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def registra_log_admin(username_admin: str, azione: str, dettagli: str):
    """Registra in modo immutabile un'azione amministrativa sensibile."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO log_amministrazione (username_admin, azione, dettagli)
                VALUES (?, ?, ?)
            """, (username_admin.strip().lower(), azione, dettagli))
            conn.commit()
        except Exception as e:
            print(f"Errore registrazione log admin: {e}")
        finally:
            conn.close()

def crea_utente(username: str, password_chiara: str, nome_completo: str, ruolo: str, admin_esecutore: str = "sistema"):
    """Crea un nuovo utente con password cifrata tramite bcrypt e traccia l'azione."""
    conn = get_db_connection()
    if not conn:
        return False, "Errore di connessione al database."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM utenti WHERE username = ?", (username.strip().lower(),))
        if cursor.fetchone():
            return False, "Username già esistente."

        hashed = hash_password(password_chiara)
        cursor.execute("""
            INSERT INTO utenti (username, password_hash, nome_completo, ruolo, tentativi_falliti, account_bloccato, cambio_password_richiesto)
            VALUES (?, ?, ?, ?, 0, 0, 0)
        """, (username.strip().lower(), hashed, nome_completo.strip(), ruolo))
        conn.commit()
        
        registra_log_admin(admin_esecutore, "CREAZIONE_UTENTE", f"Creato utente '{username}' con ruolo '{ruolo}'.")
        return True, f"Account '{username}' creato con successo."
    except Exception as e:
        return False, f"Errore creazione utente: {e}"
    finally:
        conn.close()

def autentica_utente(username: str, password_chiara: str):
    """Autentica l'utente gestendo la politica dei 5 tentativi falliti e il blocco account."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        user_lower = username.strip().lower()
        cursor.execute("SELECT * FROM utenti WHERE username = ?", (user_lower,))
        user = cursor.fetchone()

        if not user:
            return None

        if user['account_bloccato'] == 1:
            return {"errore_blocco": True, "messaggio": "Account bloccato per superamento tentativi. Contatta l'Amministratore."}

        if verifica_password(password_chiara, user['password_hash']):
            cursor.execute("UPDATE utenti SET tentativi_falliti = 0 WHERE username = ?", (user_lower,))
            conn.commit()
            return dict(user)
        else:
            nuovi_tentativi = user['tentativi_falliti'] + 1
            if nuevos_tentativi := nuovi_tentativi >= 5:
                cursor.execute("UPDATE utenti SET tentativi_falliti = ?, account_bloccato = 1 WHERE username = ?", (nuovi_tentativi, user_lower))
                conn.commit()
                registra_log_admin("sistema", "BLOCCO_ACCOUNT", f"Account '{user_lower}' bloccato per 5 tentativi falliti.")
                return {"errore_blocco": True, "messaggio": "Account bloccato dopo 5 tentativi errati. Contatta l'Amministratore per il reset."}
            else:
                cursor.execute("UPDATE utenti SET tentativi_falliti = ? WHERE username = ?", (nuovi_tentativi, user_lower))
                conn.commit()
                return None
    except Exception as e:
        print(f"Errore autenticazione: {e}")
        return None
    finally:
        conn.close()

def reset_password_admin(username: str, admin_esecutore: str = "admin"):
    """L'admin resetta la password generando una stringa casuale temporanea."""
    conn = get_db_connection()
    if not conn:
        return False, "Errore connessione DB."
    try:
        cursor = conn.cursor()
        alfabeto = string.ascii_letters + string.digits
        temp_pwd = ''.join(secrets.choice(alfabeto) for _ in range(10))
        hashed = hash_password(temp_pwd)

        cursor.execute("""
            UPDATE utenti 
            SET password_hash = ?, tentativi_falliti = 0, account_bloccato = 0, cambio_password_richiesto = 1
            WHERE username = ?
        """, (hashed, username.strip().lower()))
        conn.commit()

        registra_log_admin(admin_esecutore, "RESET_PASSWORD", f"Generata password temporanea per l'utente '{username}'.")
        return True, temp_pwd
    except Exception as e:
        return False, f"Errore reset password: {e}"
    finally:
        conn.close()

def aggiorna_password_utente(username: str, nuova_password: str):
    """Permette all'utente di impostare una nuova password."""
    conn = get_db_connection()
    if not conn:
        return False, "Errore connessione DB."
    try:
        cursor = conn.cursor()
        hashed = hash_password(nuova_password)
        cursor.execute("""
            UPDATE utenti 
            SET password_hash = ?, cambio_password_richiesto = 0 
            WHERE username = ?
        """, (hashed, username.strip().lower()))
        conn.commit()
        return True, "Password aggiornata con successo."
    except Exception as e:
        return False, f"Errore aggiornamento password: {e}"
    finally:
        conn.close()

def get_tutti_utenti():
    """Recupera la lista di tutti gli utenti registrati."""
    conn = get_db_connection()
    utenti = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username, nome_completo, ruolo, tentativi_falliti, account_bloccato, cambio_password_richiesto 
                FROM utenti
            """)
            utenti = [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"Errore lettura utenti: {e}")
        finally:
            conn.close()
    return utenti

def get_log_amministrazione():
    """Recupera la cronologia dei log amministrativi."""
    conn = get_db_connection()
    logs = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM log_amministrazione ORDER BY data_ora DESC")
            logs = [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"Errore lettura log admin: {e}")
        finally:
            conn.close()
    return logs