import streamlit as st
import pandas as pd
from datetime import datetime
from db import get_db_connection
from etichette_pdf import genera_pdf_inventario_cartaceo
from magazzino import get_stock_completo

def render():
    st.header("📋 Gestione Inventario & Conteggio Fisico")
    st.markdown("---")

    utente = st.session_state.get("utente_loggato", {})
    ruolo = utente.get("ruolo", "Magazziniere")
    nome_operatore = utente.get("nome_completo", "OPERATORE")

    tab_tablet, tab_admin, tab_cartaceo = st.tabs([
        "📱 Sessione / Conteggio Tablet",
        "🛡️ Revisione & Approvazione (Admin)",
        "📄 Inventario Cartaceo (PDF)"
    ])

    # --- TAB 1: SESSIONE / CONTEGGIO TABLET ---
    with tab_tablet:
        st.subheader("Avvia o Partecipa a una Sessione d'Inventario")
        
        conn = get_db_connection()
        sessioni_aperte = []
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inventario_sessioni WHERE stato = 'APERTA' ORDER BY id DESC")
                sessioni_aperte = [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                st.error(f"Errore caricamento sessioni: {e}")
            finally:
                conn.close()

        if ruolo == "Admin":
            with st.form("form_nuova_sessione"):
                desc_sess = st.text_input("Descrizione Sessione Inventario", value=f"Inventario {datetime.now().strftime('%d/%m/%Y')}").strip()
                if st.form_submit_button("➕ Crea Nuova Sessione in Bozza", type="primary"):
                    conn = get_db_connection()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO inventario_sessioni (descrizione, operatore_avvio, stato)
                                VALUES (?, ?, 'APERTA')
                            """, (desc_sess, nome_operatore))
                            sessione_id = cursor.lastrowid

                            # Popola le righe con lo stock teorico attuale
                            cursor.execute("""
                                SELECT pn.pn_codice, pn.ubicazione, COALESCE(mq.quantita_disponibile, 0) as giacenza
                                FROM part_numbers pn
                                LEFT JOIN magazzino_quantita mq ON pn.pn_codice = mq.pn_codice
                            """)
                            articoli = cursor.fetchall()
                            for art in articoli:
                                cursor.execute("""
                                    INSERT INTO inventario_righe (sessione_id, pn_codice, ubicazione, giacenza_teorica, quantita_reale, contato)
                                    VALUES (?, ?, ?, ?, 0, 0)
                                """, (sessione_id, art['pn_codice'], art['ubicazione'] or 'NON ASSEGNATA', art['giacenza']))

                            conn.commit()
                            st.success("Sessione creata con successo! Gli articoli sono pronti per il conteggio in bozza.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore creazione sessione: {e}")
                        finally:
                            conn.close()

        if sessioni_aperte:
            opzioni_sess = {f"#{s['id']} - {s['descrizione']} (Avviata da {s['operatore_avvio']})": s['id'] for s in sessioni_aperte}
            sess_scelta_lbl = st.selectbox("Seleziona Sessione Aperta:", list(opzioni_sess.keys()))
            sess_id = opzioni_sess[sess_scelta_lbl]

            st.markdown("#### Inserimento Conteggio Reale (Modalità Tablet)")
            conn = get_db_connection()
            righe_sess = []
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT r.id, r.pn_codice, p.descrizione, r.ubicazione, r.giacenza_teorica, r.quantita_reale, r.contato
                        FROM inventario_righe r
                        JOIN part_numbers p ON r.pn_codice = p.pn_codice
                        WHERE r.sessione_id = ?
                        ORDER BY r.ubicazione, r.pn_codice
                    """, (sess_id,))
                    righe_sess = [dict(r) for r in cursor.fetchall()]
                except Exception as e:
                    st.error(f"Errore caricamento righe: {e}")
                finally:
                    conn.close()

            if righe_sess:
                tot_inv = len(righe_sess)
                contati_inv = len([x for x in righe_sess if x['contato'] == 1])
                perc_inv = int((contati_inv / tot_inv) * 100) if tot_inv > 0 else 0

                st.progress(perc_inv / 100, text=f"Stato Conteggio: **{contati_inv} di {tot_inv} SKU contati ({perc_inv}%)**")

                for r in righe_sess:
                    is_contato = bool(r['contato'])
                    badge_status = f"🟢 CONTATO ({r['quantita_reale']} pz)" if is_contato else "🟡 DA CONTARE"

                    with st.container(border=True):
                        col_info, col_inp, col_btn = st.columns([2.5, 1.5, 1])
                        with col_info:
                            st.markdown(f"**{r['pn_codice']}** — {r['descrizione']} | `{badge_status}`")
                            st.caption(f"Ubicazione: **{r['ubicazione']}** | Giacenza a sistema: **{r['giacenza_teorica']} pz**")
                        
                        with col_inp:
                            qta_reale_in = st.number_input(
                                "Pezzi reali", 
                                min_value=0, 
                                value=int(r['quantita_reale']), 
                                step=1, 
                                key=f"qta_reale_{r['id']}"
                            )
                        
                        with col_btn:
                            st.write("")
                            st.write("")
                            lbl_btn = "✏️ Modifica" if is_contato else "💾 Salva"
                            if st.button(lbl_btn, key=f"btn_salva_{r['id']}", type="primary" if not is_contato else "secondary", use_container_width=True):
                                conn = get_db_connection()
                                if conn:
                                    try:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE inventario_righe 
                                            SET quantita_reale = ?, contato = 1 
                                            WHERE id = ?
                                        """, (qta_reale_in, r['id']))
                                        conn.commit()
                                        st.success(f"Registrato {r['pn_codice']} = {qta_reale_in} pz")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore salvataggio: {e}")
                                    finally:
                                        conn.close()
        else:
            st.info("Nessuna sessione d'inventario aperta al momento. Chiedi a un Admin di crearne una.")

    # --- TAB 2: REVISIONE & APPROVAZIONE (ADMIN) ---
    with tab_admin:
        st.subheader("🛡️ Revisione Scostamenti e Chiusura Inventario")
        if ruolo != "Admin":
            st.warning("⚠️ Accesso riservato agli amministratori per l'approvazione finale.")
        else:
            if sessioni_aperte:
                opzioni_sess_adm = {f"#{s['id']} - {s['descrizione']}": s['id'] for s in sessioni_aperte}
                sess_adm_lbl = st.selectbox("Seleziona Sessione da Revisionare:", list(opzioni_sess_adm.keys()), key="adm_sess")
                sess_adm_id = opzioni_sess_adm[sess_adm_lbl]

                conn = get_db_connection()
                righe_adm = []
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT r.id, r.pn_codice, p.descrizione, r.ubicazione, r.giacenza_teorica, r.quantita_reale, r.contato
                            FROM inventario_righe r
                            JOIN part_numbers p ON r.pn_codice = p.pn_codice
                            WHERE r.sessione_id = ?
                        """, (sess_adm_id,))
                        righe_adm = [dict(r) for r in cursor.fetchall()]
                    except Exception as e:
                        st.error(f"Errore: {e}")
                    finally:
                        conn.close()

                if righe_adm:
                    df_rev = pd.DataFrame(righe_adm)
                    df_rev['Scostamento'] = df_rev['quantita_reale'] - df_rev['giacenza_teorica']
                    df_rev_display = df_rev.rename(columns={
                        "pn_codice": "Part Number",
                        "descrizione": "Descrizione",
                        "ubicazione": "Ubicazione",
                        "giacenza_teorica": "Teorico",
                        "quantita_reale": "Reale",
                        "contato": "Contato"
                    })
                    st.dataframe(df_rev_display[["Part Number", "Descrizione", "Ubicazione", "Teorico", "Reale", "Scostamento", "Contato"]], use_container_width=True, hide_index=True)

                    if st.button("🚀 APPROVA INVENTARIO E APPLICA RETTIFICHE AL MAGAZZINO", type="primary", use_container_width=True):
                        conn = get_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                for ra in righe_adm:
                                    if ra['contato'] == 1:
                                        pn = ra['pn_codice']
                                        q_reale = ra['quantita_reale']
                                        ubic = ra['ubicazione']

                                        cursor.execute("""
                                            INSERT INTO magazzino_quantita (pn_codice, quantita_disponibile, ubicazione, operatore, data_ultimo_aggiornamento)
                                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                                            ON CONFLICT(pn_codice) DO UPDATE SET
                                                quantita_disponibile = EXCLUDED.quantita_disponibile,
                                                ubicazione = EXCLUDED.ubicazione,
                                                operatore = EXCLUDED.operatore,
                                                data_ultimo_aggiornamento = CURRENT_TIMESTAMP
                                        """, (pn, q_reale, ubic, nome_operatore))

                                        cursor.execute("""
                                            INSERT INTO storico_movimenti (pn_codice, tipo_movimento, quantita, causale, ubicazione, operatore, note)
                                            VALUES (?, 'RETTIFICA', ?, 'Approvazione Inventario #{sess_adm_id}', ?, ?, 'Allineamento inventario fisico')
                                        """, (pn, q_reale, ubic, nome_operatore))

                                cursor.execute("UPDATE inventario_sessioni SET stato = 'APPROVATA', data_chiusura = CURRENT_TIMESTAMP WHERE id = ?", (sess_adm_id,))
                                conn.commit()
                                st.success("Inventario approvato e giacenze di magazzino aggiornate con successo!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante l'approvazione: {e}")
                            finally:
                                conn.close()
            else:
                st.info("Nessuna sessione aperta da approvare.")

    # --- TAB 3: INVENTARIO CARTACEO (PDF) ---
    with tab_cartaceo:
        st.subheader("📄 Stampa Foglio di Conteggio Cartaceo")
        st.markdown("Genera un report PDF ordinato per ubicazione con spazi vuoti per effettuare il conteggio fisico a penna in magazzino.")
        
        stock_per_pdf = get_stock_completo()
        if stock_per_pdf:
            pdf_cartaceo_bytes = genera_pdf_inventario_cartaceo(stock_per_pdf)
            st.download_button(
                "📥 Scarica Foglio Inventario Cartaceo (PDF)",
                data=pdf_cartaceo_bytes,
                file_name=f"Inventario_Cartaceo_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.warning("Nessun articolo a catalogo per generare il foglio d'inventario.")