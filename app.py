import streamlit as st
import pandas as pd
import db
import licenza
import backup
import magazzino
import clienti
import inventario
import liste_batch

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

# --- GESTIONE SESSIONE ---
if "utente_loggato" not in st.session_state:
    st.session_state["utente_loggato"] = None

def render_login():
    st.markdown("<h1 style='text-align: center;'>📦 Sistema Gestione Magazzino</h1>", unsafe_allow_html=True)
    st.caption(f"<p style='text-align: center;'>{msg_lic}</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Accesso Operatore")
        user_in = st.text_input("Username").strip().lower()
        pwd_in = st.text_input("Password", type="password")

        if st.button("Accedi", use_container_width=True, type="primary"):
            user = db.autentica_utente(user_in, pwd_in)
            if user:
                st.session_state["utente_loggato"] = user
                st.success(f"Benvenuto {user['nome_completo']}!")
                st.rerun()
            else:
                st.error("Credenziali errate o account non attivo.")

def render_gestione_admin():
    st.title("🛡️ Amministrazione Utenti & Backup Cifrati")
    
    tab_u, tab_b = st.tabs(["👥 Gestione Utenti", "💾 Backup & Ripristino (AES-256)"])

    with tab_u:
        st.subheader("Utenti Registrati")
        utenti = db.get_tutti_utenti()
        st.dataframe(pd.DataFrame(utenti), use_container_width=True, hide_index=True)

        with st.form("form_nuovo_u", clear_on_submit=True):
            st.subheader("Crea Nuovo Utente")
            u_name = st.text_input("Username").strip().lower()
            u_full = st.text_input("Nome Completo").strip()
            u_pwd = st.text_input("Password", type="password")
            u_role = st.selectbox("Ruolo", ["Admin", "Magazziniere"])

            if st.form_submit_button("➕ Crea Account", type="primary"):
                if u_name and u_full and u_pwd:
                    ok, msg = db.crea_utente(u_name, u_pwd, u_full, u_role)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab_b:
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

    # BARRA DI NAVIGAZIONE AGGIORNATA CON OPZIONE A (SEZIONI DEDICATE)
    opzioni_nav = [
        "📦 Operazioni Magazzino", 
        "📋 Inventario & Tablet", 
        "📑 Liste Batch (Carico/Scarico)", 
        "👥 Anagrafica Clienti"
    ]
    if ruolo == "Admin":
        opzioni_nav.append("🛡️ Admin & Backup")

    scelta = st.segmented_control("Navigazione:", options=opzioni_nav, default=opzioni_nav[0], label_visibility="collapsed")
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