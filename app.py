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

# Definizione della Funzione Admin con la nuova tab per le Zone
def render_gestione_admin():
    st.title("🛡️ Amministrazione Utenti & Sicurezza")
    
    tab_u, tab_log, tab_zone, tab_b, tab_stampa = st.tabs([
        "👥 Gestione Utenti & Reset", 
        "📜 Audit Trail & Log Sicurezza", 
        "🗺️ Bonifica & Gestione Zone",
        "⚙️ Timeout & Backup (AES-256)",
        "🖨️ Configurazione Stampante"
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

    with tab_zone:
        st.subheader("🗺️ Bonifica e Unione Zone di Magazzino")
        st.caption("Usa questo pannello per correggere errori di digitazione, refusi o unire due zone create per errore in un'unica zona corretta su tutti gli articoli.")
        
        elenco_zone = db.get_tutte_zone()
        if not elenco_zone:
            st.info("Nessuna zona registrata nel sistema.")
        else:
            with st.form("form_bonifica_zona"):
                col_z1, col_z2 = st.columns(2)
                with col_z1:
                    zona_da_correggere = st.selectbox("Seleziona Zona da Correggere / Unire:", elenco_zone)
                with col_z2:
                    nuova_zona_nome = st.text_input("Nuovo Nome Corretto (o Zona di destinazione):").strip().upper()

                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("🚀 Esegui Bonifica e Aggiorna Articoli", type="primary", use_container_width=True):
                    if not nuova_zona_nome:
                        st.error("Inserisci il nome della zona corretta.")
                    else:
                        admin_corrente = st.session_state["utente_loggato"]["username"]
                        ok_b, msg_b = db.bonifica_e_unisci_zone(zona_da_correggere, nuova_zona_nome, admin_esecutore=admin_corrente)
                        if ok_b:
                            st.success(msg_b)
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg_b)

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
                
    with tab_stampa:
        st.subheader("🏷️ Configurazione Stampante Termica (Zebra / IP)")
        st.caption("Imposta l'indirizzo IP della stampante termica di rete utilizzata per la stampa diretta delle etichette nei reparti.")
        
        ip_attuale = st.session_state.get("ip_stampante_zebra_globale", "192.168.1.50")
        
        with st.form("form_config_stampante"):
            nuovo_ip_zebra = st.text_input(
                "Indirizzo IP Stampante Zebra (Porta 9100 standard):", 
                value=ip_attuale,
                placeholder="Es. 192.168.1.200"
            ).strip()
            
            if st.form_submit_button("💾 Salva Indirizzo IP Stampante", type="primary"):
                st.session_state["ip_stampante_zebra_globale"] = nuovo_ip_zebra
                st.success(f"Indirizzo IP della stampante aggiornato con successo a **{nuovo_ip_zebra}**!")

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