import streamlit as st
import pandas as pd
from db import get_db_connection

def get_tutti_clienti():
    conn = get_db_connection()
    clienti = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, codice_cliente, ragione_sociale, referente, note FROM clienti ORDER BY ragione_sociale ASC")
            clienti = [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            st.error(f"Errore caricamento clienti: {e}")
        finally:
            conn.close()
    return clienti

def inserisci_cliente(codice: str, ragione_sociale: str, referente: str, note: str):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO clienti (codice_cliente, ragione_sociale, referente, note)
                VALUES (?, ?, ?, ?)
            """, (codice, ragione_sociale, referente, note))
            conn.commit()
            return True, f"Cliente '{ragione_sociale}' registrato con successo!"
        except Exception as e:
            return False, f"Errore durante l'inserimento: {e}"
        finally:
            conn.close()
    return False, "Connessione al DB fallita."

def render():
    st.header("👥 Anagrafica Clienti (Destinatari Uscite)")
    st.markdown("---")

    tab_lista, tab_nuovo = st.tabs(["📋 Lista Clienti", "➕ Registra Nuovo Cliente"])

    with tab_lista:
        clienti = get_tutti_clienti()
        if clienti:
            df_clienti = pd.DataFrame(clienti)
            df_clienti_display = df_clienti.rename(columns={
                "codice_cliente": "Codice Cliente",
                "ragione_sociale": "Ragione Sociale / Nome",
                "referente": "Referente",
                "note": "Note"
            })
            st.dataframe(df_clienti_display, use_container_width=True, hide_index=True)
        else:
            st.info("Nessun cliente censito al momento.")

    with tab_nuovo:
        with st.form("form_nuovo_cliente", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                cod_cli = st.text_input("Codice Cliente *", placeholder="Es. CLI-001").strip().upper()
                rag_soc = st.text_input("Ragione Sociale / Nome *").strip()
            with col2:
                ref = st.text_input("Referente / Contatto").strip()
                note = st.text_area("Note aggiuntive", height=68).strip()

            if st.form_submit_button("💾 Salva Cliente", type="primary", use_container_width=True):
                if not cod_cli or not rag_soc:
                    st.error("I campi Codice Cliente e Ragione Sociale sono obbligatori.")
                else:
                    ok, msg = inserisci_cliente(cod_cli, rag_soc, ref, note)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)