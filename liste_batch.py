import streamlit as st
import pandas as pd
from datetime import datetime
from db import get_db_connection

def get_ubicazione_articolo(pn_codice: str) -> str:
    """Recupera l'ubicazione dal database se l'articolo esiste già."""
    if not pn_codice:
        return "SCAFFALE-A1"
    conn = get_db_connection()
    ubicazione = "SCAFFALE-A1"
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT ubicazione FROM part_numbers WHERE pn_codice = ?", (pn_codice.strip().upper(),))
            row = cursor.fetchone()
            if row and row['ubicazione']:
                ubicazione = row['ubicazione']
        except Exception:
            pass
        finally:
            conn.close()
    return ubicazione

def render():
    st.header("📑 Liste di Carico e Scarico (Batch Operations)")
    st.markdown("---")

    tab_gestione, tab_nuova = st.tabs(["📋 Gestione Liste Aperte", "➕ Crea Nuova Lista Batch"])

    utente = st.session_state.get("utente_loggato", {})
    nome_operatore = utente.get("nome_completo", "OPERATORE")

    # --- TAB 1: CREAZIONE NUOVA LISTA ---
    with tab_nuova:
        st.subheader("Crea Testata Nuova Lista")
        with st.form("form_nuova_lista", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                tipo_lista = st.selectbox("Tipo Lista Batch *", ["CARICO", "SCARICO"])
                partner = st.text_input("Fornitore (se Carico) o Cliente (se Scarico)").strip()
            with col2:
                num_ddt = st.text_input("Numero DDT Riferimento *").strip()
                data_ddt = st.date_input("Data DDT", value=datetime.now())
            
            note_lista = st.text_area("Note / Descrizione").strip()

            if st.form_submit_button("🚀 Crea Lista Batch", type="primary", use_container_width=True):
                if not num_ddt:
                    st.error("Il campo Numero DDT è obbligatorio per tracciare la lista.")
                else:
                    conn = get_db_connection()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO liste_batch (tipo, partner_nome, numero_ddt, data_ddt, stato, operatore, note)
                                VALUES (?, ?, ?, ?, 'APERTA', ?, ?)
                            """, (tipo_lista, partner, num_ddt, data_ddt.strftime('%Y-%m-%d'), nome_operatore, note_lista))
                            lista_id = cursor.lastrowid
                            conn.commit()
                            st.success(f"Lista creata con successo! Ora puoi iniziare ad aggiungere o sparare gli articoli.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore creazione lista: {e}")
                        finally:
                            conn.close()

    # --- TAB 2: GESTIONE LISTE APERTE E SPUNTE ---
    with tab_gestione:
        conn = get_db_connection()
        liste = []
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM liste_batch WHERE stato = 'APERTA' ORDER BY id DESC")
                liste = [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                st.error(f"Errore caricamento liste: {e}")
            finally:
                conn.close()

        if liste:
            col_sel, col_del = st.columns([3, 1])
            with col_sel:
                # Menu a tendina pulito senza ID numerico
                opzioni_liste = {f"[{l['tipo']}] Partner: {l['partner_nome'] or 'N/D'} | DDT: {l['numero_ddt'] or 'N/D'}": l['id'] for l in liste}
                lista_scelta_lbl = st.selectbox("Seleziona Lista da Gestire:", list(opzioni_liste.keys()))
                lista_id_sel = opzioni_liste[lista_scelta_lbl]

            info_l = next((x for x in liste if x['id'] == lista_id_sel), None)
            
            with col_del:
                st.write("") 
                st.write("")
                if st.button("🗑️ Elimina Lista", type="secondary", use_container_width=True, key=f"btn_del_l_{lista_id_sel}"):
                    st.session_state[f"conferma_del_lista_{lista_id_sel}"] = True

            if st.session_state.get(f"conferma_del_lista_{lista_id_sel}", False):
                st.warning(f"⚠️ Sei sicuro di voler eliminare definitivamente questa Lista (DDT: {info_l['numero_ddt'] if info_l else 'N/D'})?")
                c_yes, c_no = st.columns(2)
                with c_yes:
                    if st.button("Sì, Elimina", type="primary", key=f"yes_del_{lista_id_sel}"):
                        conn = get_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM liste_batch_righe WHERE lista_id = ?", (lista_id_sel,))
                                cursor.execute("DELETE FROM liste_batch WHERE id = ?", (lista_id_sel,))
                                conn.commit()
                                st.session_state[f"conferma_del_lista_{lista_id_sel}"] = False
                                st.success("Lista eliminata con successo.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore eliminazione: {e}")
                            finally:
                                conn.close()
                with c_no:
                    if st.button("Annulla", key=f"no_del_{lista_id_sel}"):
                        st.session_state[f"conferma_del_lista_{lista_id_sel}"] = False
                        st.rerun()

            if info_l:
                st.info(f"**Tipo Operazione:** {info_l['tipo']} | **Partner:** {info_l['partner_nome'] or 'N/D'} | **N. DDT:** {info_l['numero_ddt']} ({info_l['data_ddt']})")

            conn = get_db_connection()
            righe = []
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT r.id, r.pn_codice, p.descrizione, r.quantita, r.ubicazione, r.spuntato
                        FROM liste_batch_righe r
                        JOIN part_numbers p ON r.pn_codice = p.pn_codice
                        WHERE r.lista_id = ?
                    """, (lista_id_sel,))
                    righe = [dict(r) for r in cursor.fetchall()]
                except Exception as e:
                    st.error(f"Errore caricamento righe: {e}")
                finally:
                    conn.close()

            # --- SEZIONE SPARACODICI / INSERIMENTO RAPIDO ---
            with st.container(border=True):
                st.markdown("#### 🔍 Sparacodici / Spunta Automatica")
                col_sp1, col_sp2, col_sp3 = st.columns([2, 1, 1])
                with col_sp1:
                    pn_sparo = st.text_input("Spara o digita Part Number (PN)", key=f"sparo_pn_{lista_id_sel}", placeholder="Es. PN-ELET-001").strip().upper()
                with col_sp2:
                    qta_sparo = st.number_input("Quantità", min_value=1, value=1, key=f"sparo_qta_{lista_id_sel}")
                with col_sp3:
                    st.write("")
                    st.write("")
                    btn_sparo = st.button("✅ Registra / Spunta", use_container_width=True, type="primary")

                if btn_sparo and pn_sparo:
                    riga_esistente = next((r for r in righe if r['pn_codice'] == pn_sparo), None)
                    conn = get_db_connection()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            if riga_esistente:
                                # Aggiorna e spunta automaticamente in modo che sia pronto per la finalizzazione
                                cursor.execute("""
                                    UPDATE liste_batch_righe 
                                    SET spuntato = 1, quantita = ? 
                                    WHERE id = ?
                                """, (qta_sparo, riga_esistente['id']))
                                st.success(f"Articolo {pn_sparo} verificato e spuntato automaticamente!")
                            else:
                                # Aggiunge l'articolo inserendolo già spuntato
                                ubic_sug = get_ubicazione_articolo(pn_sparo)
                                if info_l['tipo'] == 'CARICO':
                                    cursor.execute("""
                                        INSERT INTO part_numbers (pn_codice, descrizione, categoria, ubicazione)
                                        VALUES (?, ?, 'Generico', ?)
                                        ON CONFLICT(pn_codice) DO UPDATE SET
                                            ubicazione = COALESCE(EXCLUDED.ubicazione, part_numbers.ubicazione)
                                    """, (pn_sparo, f"Articolo {pn_sparo}", ubic_sug))

                                cursor.execute("""
                                    INSERT INTO liste_batch_righe (lista_id, pn_codice, quantita, ubicazione, spuntato)
                                    VALUES (?, ?, ?, ?, 1)
                                """, (lista_id_sel, pn_sparo, qta_sparo, ubic_sug))
                                st.success(f"Articolo {pn_sparo} aggiunto e spuntato automaticamente!")

                            conn.commit()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante lo sparo: {e}")
                        finally:
                            conn.close()

            # --- TABELLA D'AVANZAMENTO E RIGHE CON CONTRASTO VISIVO ---
            st.markdown("#### 📋 Controllo Operativo Passo-Passo")
            tot_righe = len(righe)
            spuntate_tot = len([r for r in righe if r['spuntato'] == 1])

            if tot_righe > 0:
                perc = int((spuntate_tot / tot_righe) * 100)
                st.progress(perc / 100, text=f"Avanzamento Controllo: **{spuntate_tot} di {tot_righe} articoli verificati ({perc}%)**")

            for r in righe:
                is_ok = bool(r['spuntato'])
                # Distinzione visiva netta tramite etichette e stili
                badge = "🟢 **VERIFICATO**" if is_ok else "🟡 *DA VERIFICARE*"

                with st.container(border=True):
                    col_chk, col_info, col_act = st.columns([0.5, 3.5, 1])
                    with col_chk:
                        spuntato_nuovo = st.checkbox("OK", value=is_ok, key=f"chk_riga_{r['id']}")
                    with col_info:
                        st.markdown(f"**{r['pn_codice']}** — {r['descrizione']} &nbsp;&nbsp;|&nbsp;&nbsp; {badge}")
                        st.caption(f"Quantità: **{r['quantita']} pz** | Ubicazione: **{r['ubicazione']}**")
                    with col_act:
                        st.write("")
                        if st.button("🗑️ Rimuovi", key=f"del_riga_{r['id']}", use_container_width=True):
                            conn = get_db_connection()
                            if conn:
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("DELETE FROM liste_batch_righe WHERE id = ?", (r['id'],))
                                    conn.commit()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                                finally:
                                    conn.close()

                    if spuntato_nuovo != is_ok:
                        conn = get_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("UPDATE liste_batch_righe SET spuntato = ? WHERE id = ?", (1 if spuntato_nuovo else 0, r['id']))
                                conn.commit()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore aggiornamento spunta: {e}")
                            finally:
                                conn.close()

            # --- AGGIUNTA MANUALE RIGA ---
            with st.form(f"form_aggiungi_riga_{lista_id_sel}", clear_on_submit=True):
                st.markdown("##### ➕ Aggiungi Articolo Manualmente alla Lista")
                ca1, ca2, ca3 = st.columns(3)
                with ca1:
                    pn_extra = st.text_input("Part Number").strip().upper()
                with ca2:
                    qta_extra = st.number_input("Quantità", min_value=1, value=1)
                with ca3:
                    ubic_extra_sugg = get_ubicazione_articolo(pn_extra) if pn_extra else "SCAFFALE-A1"
                    ubic_extra = st.text_input("Ubicazione", value=ubic_extra_sugg).strip().upper()

                if st.form_submit_button("➕ Aggiungi alla Lista"):
                    if pn_extra:
                        conn = get_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                if info_l['tipo'] == 'CARICO':
                                    cursor.execute("""
                                        INSERT INTO part_numbers (pn_codice, descrizione, categoria, ubicazione)
                                        VALUES (?, ?, 'Generico', ?)
                                        ON CONFLICT(pn_codice) DO UPDATE SET
                                            ubicazione = COALESCE(EXCLUDED.ubicazione, part_numbers.ubicazione)
                                    """, (pn_extra, f"Articolo {pn_extra}", ubic_extra))

                                cursor.execute("""
                                    INSERT INTO liste_batch_righe (lista_id, pn_codice, quantita, ubicazione, spuntato)
                                    VALUES (?, ?, ?, ?, 0)
                                """, (lista_id_sel, pn_extra, qta_extra, ubic_extra))
                                conn.commit()
                                st.success("Articolo aggiunto con successo!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore: {e}")
                            finally:
                                conn.close()

            st.markdown("---")
            if st.button("🚀 Conferma e Finalizza Lista (Aggiorna Magazzino)", type="primary", use_container_width=True):
                if tot_righe == 0:
                    st.error("Impossibile finalizzare una lista vuota.")
                elif spuntate_tot < tot_righe:
                    st.warning("⚠️ Attenzione: ci sono ancora articoli da verificare prima di poter finalizzare.")
                else:
                    conn = get_db_connection()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("SELECT * FROM liste_batch_righe WHERE lista_id = ?", (lista_id_sel,))
                            tutte_righe = cursor.fetchall()

                            for tr in tutte_righe:
                                pn = tr['pn_codice']
                                qta = tr['quantita']
                                ubic = tr['ubicazione']

                                cursor.execute("SELECT quantita_disponibile FROM magazzino_quantita WHERE pn_codice = ?", (pn,))
                                q_row = cursor.fetchone()
                                q_att = q_row['quantita_disponibile'] if q_row else 0

                                if info_l['tipo'] == 'CARICO':
                                    nuova_q = q_att + qta
                                    tipo_m = 'CARICO'
                                else:
                                    if q_att < qta:
                                        st.error(f"Giacenza insufficiente per {pn}. Disponibili: {q_att}, richiesti: {qta}.")
                                        st.stop()
                                    nuova_q = q_att - qta
                                    tipo_m = 'SCARICO'

                                cursor.execute("""
                                    INSERT INTO magazzino_quantita (pn_codice, quantita_disponibile, ubicazione, operatore, data_ultimo_aggiornamento)
                                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                                    ON CONFLICT(pn_codice) DO UPDATE SET
                                        quantita_disponibile = EXCLUDED.quantita_disponibile,
                                        ubicazione = EXCLUDED.ubicazione,
                                        operatore = EXCLUDED.operatore,
                                        data_ultimo_aggiornamento = CURRENT_TIMESTAMP
                                """, (pn, nuova_q, ubic, nome_operatore))

                                cursor.execute("""
                                    INSERT INTO storico_movimenti (pn_codice, tipo_movimento, quantita, causale, numero_ddt, data_ddt, ubicazione, operatore, note)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (pn, tipo_m, qta, f"Lista Batch #{lista_id_sel} ({info_l['tipo']})", info_l['numero_ddt'], info_l['data_ddt'], ubic, nome_operatore, info_l['note']))

                            cursor.execute("UPDATE liste_batch SET stato = 'COMPLETATA' WHERE id = ?", (lista_id_sel,))
                            conn.commit()
                            st.success("Lista batch completata e magazzino aggiornato con successo!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante la finalizzazione: {e}")
                        finally:
                            conn.close()
        else:
            st.info("Nessuna lista batch aperta al momento.")