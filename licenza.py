import os
import json
import base64
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken

# Chiave master di cifratura/decifratura per la validazione locale
MASTER_KEY = b'G7x_k9P2M4zQ8L0vR1wT5yU3iO6pA7sD9fG1hJ3kL5m='

def genera_file_licenza(ragione_sociale: str, data_scadenza_str: str, file_output: str = "license.key"):
    """
    Utility per generare file di licenza cifrati (da usare lato sviluppatore).
    Formato data: 'YYYY-MM-DD'
    """
    f = Fernet(MASTER_KEY)
    payload = {
        "ragione_sociale": ragione_sociale,
        "scadenza": data_scadenza_str,
        "generata_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    dati_cifrati = f.encrypt(json.dumps(payload).encode('utf-8'))
    
    with open(file_output, "wb") as file_lic:
        file_lic.write(dati_cifrati)

def valida_e_carica_licenza(file_licenza: str = "license.key") -> tuple[bool, str, dict]:
    """
    Verifica la presenza, la validità e la scadenza della licenza d'uso.
    Restituisce: (is_valida, messaggio, dati_licenza)
    """
    if not os.path.exists(file_licenza):
        return False, "File di licenza 'license.key' non trovato. Inserisci una licenza valida per accedere.", {}

    try:
        f = Fernet(MASTER_KEY)
        with open(file_licenza, "rb") as file_lic:
            dati_cifrati = file_lic.read()
        
        dati_decifrati = f.decrypt(dati_cifrati)
        payload = json.loads(dati_decifrati.decode('utf-8'))
        
        data_scadenza = datetime.strptime(payload["scadenza"], "%Y-%m-%d")
        oggi = datetime.now()

        if oggi > data_scadenza:
            dias_scaduti = (oggi - data_scadenza).days
            return False, f"Abbonamento scaduto il {data_scadenza.strftime('%d/%m/%Y')} ({dias_scaduti} giorni fa). Rinnova la licenza per continuare.", payload
        
        giorni_rimasti = (data_scadenza - oggi).days
        msg_ok = f"Licenza Attiva - {payload['ragione_sociale']} (Scadenza: {data_scadenza.strftime('%d/%m/%Y')} - {giorni_rimasti} gg rimasti)"
        return True, msg_ok, payload

    except InvalidToken:
        return False, "File di licenza non valido o manomesso.", {}
    except Exception as e:
        return False, f"Errore durante la verifica della licenza: {e}", {}