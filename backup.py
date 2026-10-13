import os
from dotenv import load_dotenv
import shutil
from datetime import datetime
from cryptography.fernet import Fernet

# Carica le variabili protette dal file .env
load_dotenv()

DB_NAME = "magazzino.db"
KEY_FILE = "secret.key"

# Recupera la chiave di cifratura AES-256 in modo sicuro dall'ambiente (con fallback sulla chiave locale se non definita)
MASTER_KEY = os.getenv("MASTER_ENCRYPTION_KEY")

def ottieni_o_genera_chiave() -> bytes:
    """Carica la chiave Fernet o ne genera una nuova."""
    if MASTER_KEY:
        # Se la chiave è definita nel file .env, la usiamo convertendola in bytes se necessario
        return MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY
    
    # Altrimenti fallback sul file locale secret.key
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key
    else:
        with open(KEY_FILE, "rb") as f:
            return f.read()

def esegui_backup_cifrato(cartella_destinazione: str = "./backups") -> tuple[bool, str]:
    """Cifra il database magazzino.db e lo salva in formato .enc usando la chiave protetta."""
    if not os.path.exists(DB_NAME):
        return False, "Database 'magazzino.db' non trovato."

    try:
        if not os.path.exists(cartella_destinazione):
            os.makedirs(cartella_destinazione)

        key = ottieni_o_genera_chiave()
        fernet = Fernet(key)

        with open(DB_NAME, "rb") as f_in:
            dati_db = f_in.read()

        dati_cifrati = fernet.encrypt(dati_db)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_file_backup = f"backup_magazzino_{timestamp}.enc"
        percorso_completo = os.path.join(cartella_destinazione, nome_file_backup)

        with open(percorso_completo, "wb") as f_out:
            f_out.write(dati_cifrati)

        return True, f"Backup cifrato AES-256 eseguito con successo: {nome_file_backup}"

    except Exception as e:
        return False, f"Errore durante la creazione del backup cifrato: {e}"

def ripristina_backup_cifrato(percorso_file_enc: str) -> tuple[bool, str]:
    """Decifra un file .enc e sovrascrive magazzino.db."""
    if not os.path.exists(percorso_file_enc):
        return False, "File di backup non trovato."

    try:
        key = ottieni_o_genera_chiave()
        fernet = Fernet(key)

        with open(percorso_file_enc, "rb") as f_enc:
            dati_cifrati = f_enc.read()

        dati_decifrati = fernet.decrypt(dati_cifrati)

        # Salvataggio di sicurezza del DB attuale prima di sovrascrivere
        if os.path.exists(DB_NAME):
            shutil.copyfile(DB_NAME, f"{DB_NAME}.bak")

        with open(DB_NAME, "wb") as f_db:
            f_db.write(dati_decifrati)

        return True, "Database ripristinato con successo!"

    except Exception as e:
        return False, f"Impossibile ripristinare il backup. Chiave errata o file corrotto: {e}"