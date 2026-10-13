import streamlit as st
import pandas as pd
import time
import db
import licenza
import backup
import magazzino
import clienti
import inventario
import liste_batch
import os
from dotenv import load_dotenv

# Caricamento immediato dei segreti all'avvio dell'applicazione
load_dotenv()

# Configurazione Pagina Streamlit
st.set_page_config(
    page_title="Gestione Magazzino SaaS",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inizializzazione DB
db.init_db()

# --- VERIFICA LICENZA CIFRATA (license.key) ---
lic_ok, msg_lic, dati_lic = licenza.valida_e_carica_licenza("license.key")

if not lic_ok:
    st.error(f"⚠️ {msg_lic}")
    st.info("Per sbloccare il sistema, carica o rinnova il file 'license.key' inviato dall'assistenza.")
    st.stop()

# --- GESTIONE SESSIONE E TIMEOUT DI INATTIVITÀ ---
if "utente_loggato" not in st.session_state:
    st.session_state["utente_loggato"] = None

if "ultimo_timestamp_attivita" not in st.session_state:
    st.session_state["ultimo_timestamp_attivita"] = time.time()

if "timeout_minuti" not in st.session_state:
    st.session_state["timeout_minuti"] = 10  # Default a 10 minuti come concordato

# Controllo timeout se l'utente è loggato
if st.session_state["utente_loggato"] is not None:
    tempo_corrente = time.time()
    ultimo_tempo = st.session_state.get("ultimo_timestamp_attivita", tempo_corrente)
    timeout_limite_sec = st.session_state.get("timeout_minuti", 10) * 60
    
    if (tempo_corrente - ultimo_tempo) > timeout_limite_sec:
        st.session_state["utente_loggato"] = None
        st.warning("⏱️ Sessione scaduta per inattività. Effettua nuovamente l'accesso.")
        st.stop()
    else:
        # Aggiorna il timestamp dell'ultima attività rilevata
        st.session_state["ultimo_timestamp_attivita"] = tempo_corrente

def render_login():
    st.markdown("<h1 style='text-align: center;'>📦 Sistema Gestione Magazzino</h1>", unsafe_allow_html=True)
    st.caption(f"<p style='text-align: center;'>{msg_lic}</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Accesso Operatore")
        user_in = st.text_input("Username").strip().lower()
        pwd_in = st.text_input("Password", type="password")

        if st.button("Accedi", use_container_width=True, type="primary"):
            risultato = db.autentica_utente(user_in, pwd_in)
            
            # Controllo se l'autenticazione ha restituito un dizionario di blocco
            if isinstance(risultato, dict) and risultato.get("errore_blocco"):
                st.error(risultato["messaggio"])
            elif risultato:
                st.session_state["utente_loggato"] = risultato
                st.session_state["ultimo_timestamp_attivita"] = time.time()
                st.success(f"Benvenuto {risultato['nome_completo']}!")
                st.rerun()
            else:
                st.error("Credenziali errate. Attenzione: dopo 5 tentativi falliti l'account verrà bloccato.")

def render_cambio_password_forzato():
    utente = st.session_state["utente_loggato"]
    st.warning("⚠️ **Primo accesso o password temporanea rilevata.** Per motivi di sicurezza, è obbligatorio impostare una nuova password personale.")
    
    with st.form("form_cambio_pwd_forzato"):
        nuova_p1 = st.text_input("Nuova Password", type="password")
        nuova_p2 = st.text_input("Conferma Nuova Password", type="password")
        
        if st.form_submit_button("🔒 Aggiorna Password e Accedi", type="primary"):
            if not nuova_p1 or len(nuova_p1) < 6:
                st.error("La password deve contenere almeno 6 caratteri.")
            elif nuova_p1 != nuova_p2:
                st.error("Le password non coincidono.")
            else:
                ok, msg = db.aggiorna_password_utente(utente["username"], nuova_p1)
                if ok:
                    st.success("Password aggiornata con successo! Ricarico il sistema...")
                    utente["cambio_password_richiesto"] = 0
                    st.session_state["utente_loggato"] = utente
                    st.session_state["ultimo_timestamp_attivita"] = time.time()
                    st.rerun()
                else:
                    st.error(msg)

def render_gestione_admin():
    st.title("🛡️ Amministrazione Utenti & Sicurezza")
    
    tab_u, tab_b = st.tabs(["👥 Gestione Utenti & Reset", "💾 Backup & Sicurezza"])

    with tab_u:
        st.subheader("Utenti Registrati e Stato Account")
        utenti = db.get_tutti_utenti()
        df_utenti = pd.DataFrame(utenti).rename(columns={
            "username": "Username",
            "nome_completo": "Nome Completo",
            "ruolo": "Ruolo",
            "tentativi_falliti": "Tentativi Falliti",
            "account_bloccato": "Bloccato",
            "cambio_password_richiesto": "Cambio Psw Obbligatorio"
        })
        st.dataframe(df_utenti, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🔄 Azioni Amministrative (Reset Password)")
        col_r1, col_r2 = st.columns([2, 1])
        with col_r1:
            username_da_resettare = st.selectbox("Seleziona Utente per Reset Password:", [u["username"] for u in utenti])
        with col_r2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔑 Genera Password Temporanea", type="secondary"):
                ok, res_msg = db.reset_password_admin(username_da_resettare)
                if ok:
                    st.success(f"Password temporanea generata per **{username_da_resettare}**:")
                    st.code(res_msg, language="text")
                    st.info("Comunica questa stringa all'utente. Al primo accesso dovrà obbligatoriamente cambiarla.")
                else:
                    st.error(res_msg)

        st.markdown("---")
        with st.form("form_nuovo_u", clear_on_submit=True):
            st.subheader("➕ Crea Nuovo Utente")
            u_name = st.text_input("Username").strip().lower()
            u_full = st.text_input("Nome Completo").strip()
            u_pwd = st.text_input("Password Iniziale", type="password")
            u_role = st.selectbox("Ruolo", ["Admin", "Magazziniere"])

            if st.form_submit_button("Crea Account", type="primary"):
                if u_name and u_full and u_pwd:
                    ok, msg = db.crea_utente(u_name, u_pwd, u_full, u_role)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("Tutti i campi sono obbligatori.")

    with tab_b:
        st.subheader("⏱️ Configurazione Timeout di Inattività")
        timeout_attuale = st.session_state.get("timeout_minuti", 10)
        
        with st.form("form_timeout"):
            nuovo_timeout = st.number_input(
                "Minuti di inattività prima del logout automatico:", 
                min_value=1, 
                max_value=120, 
                value=timeout_attuale,
                help="Tempo di inoperatività trascorso il quale la sessione viene chiusa per sicurezza."
            )
            if st.form_submit_button("💾 Salva Impostazione Timeout", type="primary"):
                st.session_state["timeout_minuti"] = nuovo_timeout
                st.success(f"Timeout di inattività aggiornato con successo a {nuovo_timeout} minuti.")

        st.markdown("---")
        st.subheader("📦 Backup Cifrato Manuale")
        if st.button("🚀 Esegui Backup Cifrato Ora", type="primary"):
            ok, msg = backup.esegui_backup_cifrato()
            if ok:
                st.success(msg)
            else:
                st.error(msg)

# --- FLUSSO APPLICAZIONE ---
if st.session_state["utente_loggato"] is None:
    render_login()
elif st.session_state["utente_loggato"].get("cambio_password_richiesto") == 1:
    render_cambio_password_forzato()
else:
    utente = st.session_state["utente_loggato"]
    ruolo = utente["ruolo"]

    # Header Superiore con info Operatore e Licenza
    c_titolo, c_info, c_logout = st.columns([3, 2, 1])
    with c_titolo:
        st.markdown("## 📦 **Gestione Magazzino**")
    with c_info:
        st.markdown(f"👤 **{utente['nome_completo']}** (`{ruolo}`)<br><small>🟢 {dati_lic.get('ragione_sociale', 'Licenza Attiva')}</small>", unsafe_allow_html=True)
    with c_logout:
        if st.button("🔴 Logout", use_container_width=True):
            st.session_state["utente_loggato"] = None
            st.rerun()

    st.divider()

    # DASHBOARD KPI SUPERIORE
    stock_all = magazzino.get_stock_completo()
    tot_art = len(stock_all)
    sotto_scorta_tot = len([x for x in stock_all if x['giacenza'] <= x['scorta_minima']])
    tot_giacenza_pezzi = sum([x['giacenza'] for x in stock_all])

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("📦 Articoli a Catalogo", f"{tot_art} SKU")
    kpi2.metric("📊 Pezzi Totali a Stock", f"{tot_giacenza_pezzi} pz")
    kpi3.metric("⚠️ Articoli Sotto Scorta", f"{sotto_scorta_tot} voci", delta=-sotto_scorta_tot if sotto_scorta_tot > 0 else 0)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- BARRA DI NAVIGAZIONE CON BADGE DINAMICO PER IL SOTTO SCORTA ---
    badge_nav_text = f" ⚠️ ({sotto_scorta_tot})" if sotto_scorta_tot > 0 else ""

    opzioni_nav = [
        f"📦 Operazioni Magazzino{badge_nav_text}", 
        "📋 Inventario & Tablet", 
        "📑 Liste Batch (Carico/Scarico)", 
        "👥 Anagrafica Clienti"
    ]
    if ruolo == "Admin":
        opzioni_nav.append("🛡️ Admin & Backup")

    scelta_raw = st.segmented_control("Navigazione:", options=opzioni_nav, default=opzioni_nav[0], label_visibility="collapsed")
    scelta = scelta_raw.split(" ⚠️")[0] if " ⚠️" in scelta_raw else scelta_raw

    st.markdown("<br>", unsafe_allow_html=True)

    if scelta == "📦 Operazioni Magazzino":
        magazzino.render()
    elif scelta == "📋 Inventario & Tablet":
        inventario.render()
    elif scelta == "📑 Liste Batch (Carico/Scarico)":
        liste_batch.render()
    elif scelta == "👥 Anagrafica Clienti":
        clienti.render()
    elif scelta == "🛡️ Admin & Backup" and ruolo == "Admin":
        render_gestione_admin()
        
def render_gestione_admin():
    st.title("🛡️ Amministrazione Utenti & Sicurezza")
    
    # Creiamo tab dedicate: Gestione Utenti, Audit Trail (Log), Timeout e Backup
    tab_u, tab_log, tab_b = st.tabs([
        "👥 Gestione Utenti & Reset", 
        "📜 Audit Trail & Log Sicurezza", 
        "⚙️ Timeout & Backup (AES-256)"
    ])

    with tab_u:
        st.subheader("Utenti Registrati e Stato Account")
        utenti = db.get_tutti_utenti()
        df_utenti = pd.DataFrame(utenti).rename(columns={
            "username": "Username",
            "nome_completo": "Nome Completo",
            "ruolo": "Ruolo",
            "tentativi_falliti": "Tentativi Falliti",
            "account_bloccato": "Bloccato",
            "cambio_password_richiesto": "Cambio Psw Obbligatorio"
        })
        st.dataframe(df_utenti, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🔄 Azioni Amministrative (Reset Password)")
        col_r1, col_r2 = st.columns([2, 1])
        with col_r1:
            username_da_resettare = st.selectbox("Seleziona Utente per Reset Password:", [u["username"] for u in utenti])
        with col_r2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔑 Genera Password Temporanea", type="secondary"):
                # Passiamo l'username dell'admin attualmente loggato per tracciarlo nei log
                admin_corrente = st.session_state["utente_loggato"]["username"]
                ok, res_msg = db.reset_password_admin(username_da_resettare, admin_esecutore=admin_corrente)
                if ok:
                    st.success(f"Password temporanea generata per **{username_da_resettare}**:")
                    st.code(res_msg, language="text")
                    st.info("Comunica questa stringa all'utente. Al primo accesso dovrà obbligatoriamente cambiarla.")
                else:
                    st.error(res_msg)

        st.markdown("---")
        with st.form("form_nuovo_u", clear_on_submit=True):
            st.subheader("➕ Crea Nuovo Utente")
            u_name = st.text_input("Username").strip().lower()
            u_full = st.text_input("Nome Completo").strip()
            u_pwd = st.text_input("Password Iniziale", type="password")
            u_role = st.selectbox("Ruolo", ["Admin", "Magazziniere"])

            if st.form_submit_button("Crea Account", type="primary"):
                if u_name and u_full and u_pwd:
                    admin_corrente = st.session_state["utente_loggato"]["username"]
                    ok, msg = db.crea_utente(u_name, u_pwd, u_full, u_role, admin_esecutore=admin_corrente)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("Tutti i campi sono obbligatori.")

    with tab_log:
        st.subheader("📜 Cronologia Immutabile degli Eventi (Audit Trail)")
        st.caption("Registro ufficiale di tutte le azioni amministrative e di sicurezza eseguite sul sistema.")
        
        logs = db.get_log_amministrazione()
        if logs:
            df_logs = pd.DataFrame(logs).rename(columns={
                "id": "ID",
                "username_admin": "Esecutore",
                "azione": "Tipo Azione",
                "dettagli": "Dettagli Operazione",
                "data_ora": "Data e Ora"
            })
            st.dataframe(df_logs, use_container_width=True, hide_index=True)
        else:
            st.info("Nessun evento registrato al momento.")

    with tab_b:
        st.subheader("⏱️ Configurazione Timeout di Inattività")
        timeout_attuale = st.session_state.get("timeout_minuti", 10)
        
        with st.form("form_timeout"):
            nuovo_timeout = st.number_input(
                "Minuti di inattività prima del logout automatico:", 
                min_value=1, 
                max_value=120, 
                value=timeout_attuale,
                help="Tempo di inoperatività trascorso il quale la sessione viene chiusa per sicurezza."
            )
            if st.form_submit_button("💾 Salva Impostazione Timeout", type="primary"):
                st.session_state["timeout_minuti"] = nuovo_timeout
                st.success(f"Timeout di inattività aggiornato con successo a {nuovo_timeout} minuti.")

        st.markdown("---")
        st.subheader("📦 Backup Cifrato Manuale")
        if st.button("🚀 Esegui Backup Cifrato Ora", type="primary"):
            ok, msg = backup.esegui_backup_cifrato()
            if ok:
                st.success(msg)
            else:
                st.error(msg)