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
    """Inizializza le tabelle del database se non esistono e gestisce le colonne di sicurezza."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Tabella Part Numbers (Articoli)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS part_numbers (
                    pn_codice TEXT PRIMARY KEY,
                    descrizione TEXT,
                    categoria TEXT,
                    ubicazione TEXT,
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
                    operatore TEXT,
                    data_ultimo_aggiornamento TIMESTAMP,
                    FOREIGN KEY (pn_codice) REFERENCES part_numbers(pn_codice)
                )
            """)

            # Tabella Clienti
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clienti (
                    codice_cliente TEXT PRIMARY KEY,
                    ragione_sociale TEXT,
                    partita_iva TEXT,
                    indirizzo TEXT,
                    email TEXT
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
                print("Creato utente di default 'admin' con password temporanea 'admin123' (richiesto cambio password al primo accesso).")

        except Exception as e:
            print(f"Errore inizializzazione DB: {e}")
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
        
        # Traccia log admin
        registra_log_admin(admin_esecutore, "CREAZIONE_UTENTE", f"Creato utente '{username}' con ruolo '{ruolo}'.")
        
        return True, f"Account '{username}' creato con successo."
    except Exception as e:
        return False, f"Errore creazione utente: {e}"
    finally:
        conn.close()

def autentica_utente(username: str, password_chiara: str):
    """
    Autentica l'utente gestendo la politica dei 5 tentativi falliti 
    e il blocco account.
    """
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

        # Controllo se l'account è bloccato
        if user['account_bloccato'] == 1:
            return {"errore_blocco": True, "messaggio": "Account bloccato per superamento tentativi. Contatta l'Amministratore."}

        # Verifica password
        if verifica_password(password_chiara, user['password_hash']):
            # Password corretta: resetta i tentativi falliti e restituisce i dati utente
            cursor.execute("UPDATE utenti SET tentativi_falliti = 0 WHERE username = ?", (user_lower,))
            conn.commit()
            return dict(user)
        else:
            # Password errata: incrementa i tentativi falliti
            nuovi_tentativi = user['tentativi_falliti'] + 1
            
            if nuovi_tentativi >= 5:
                # Blocco definitivo dell'account dopo 5 tentativi
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
    """
    L'admin resetta la password generando una stringa casuale temporanea,
    imposta il flag di cambio password obbligatorio, sblocca l'account e traccia l'evento.
    """
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

        # Traccia log amministrazione
        registra_log_admin(admin_esecutore, "RESET_PASSWORD", f"Generata password temporanea per l'utente '{username}'.")

        return True, temp_pwd
    except Exception as e:
        return False, f"Errore reset password: {e}"
    finally:
        conn.close()

def aggiorna_password_utente(username: str, nuova_password: str):
    """Permette all'utente di impostare una nuova password e azzera il flag di cambio obbligatorio."""
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
    """Recupera la lista di tutti gli utenti registrati (senza includere l'hash)."""
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
    """Recupera la cronologia dei log amministrativi per la visualizzazione di controllo."""
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