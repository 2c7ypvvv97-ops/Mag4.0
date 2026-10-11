import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from db import get_db_connection
from clienti import get_tutti_clienti
from etichette_pdf import genera_pdf_etichetta_singola, genera_pdf_lista_riordino

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

def get_stock_completo(filtro_ricerca: str = "", filtro_stato: str = "Tutti"):
    conn = get_db_connection()
    rows = []
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                SELECT 
                    pn.pn_codice, pn.descrizione, pn.categoria, pn.ubicazione, 
                    pn.scorta_minima, pn.lotto_riordino, pn.fornitore_abituale,
                    COALESCE(mq.quantita_disponibile, 0) AS giacenza,
                    mq.data_ultimo_aggiornamento
                FROM part_numbers pn
                LEFT JOIN magazzino_quantita mq ON pn.pn_codice = mq.pn_codice
            """
            conditions = []
            params = []

            if filtro_ricerca:
                pattern = f"%{filtro_ricerca.strip()}%"
                conditions.append("(pn.pn_codice LIKE ? OR pn.descrizione LIKE ? OR pn.ubicazione LIKE ? OR pn.categoria LIKE ?)")
                params.extend([pattern, pattern, pattern, pattern])

            if filtro_stato == "Disponibili":
                conditions.append("COALESCE(mq.quantita_disponibile, 0) > 0")
            elif filtro_stato == "Sotto Scorta":
                conditions.append("COALESCE(mq.quantita_disponibile, 0) <= pn.scorta_minima")
            elif filtro_stato == "Esauriti":
                conditions.append("COALESCE(mq.quantita_disponibile, 0) = 0")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY pn.pn_codice ASC"
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            st.error(f"Errore lettura stock: {e}")
        finally:
            conn.close()
    return rows

def get_movimenti_storico(data_inizio, data_fine, filtro_pn=""):
    conn = get_db_connection()
    movimenti = []
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                SELECT m.id, m.pn_codice, m.tipo_movimento, m.quantita, m.causale, 
                       c.ragione_sociale AS cliente, m.numero_ddt, m.data_ddt, m.ubicazione, m.operatore, m.note, m.data_ora
                FROM storico_movimenti m
                LEFT JOIN clienti c ON m.codice_cliente = c.codice_cliente
                WHERE DATE(m.data_ora) BETWEEN ? AND ?
            """
            params = [data_inizio.strftime('%Y-%m-%d'), data_fine.strftime('%Y-%m-%d')]

            if filtro_pn:
                query += " AND m.pn_codice LIKE ?"
                params.append(f"%{filtro_pn.strip()}%")

            query += " ORDER BY m.data_ora DESC"
            cursor.execute(query, params)
            movimenti = [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            st.error(f"Errore storico movimenti: {e}")
        finally:
            conn.close()
    return movimenti

def render():
    st.header("📦 Gestione Operativa Magazzino")
    st.markdown("---")

    utente = st.session_state.get("utente_loggato", {})
    nome_operatore = utente.get("nome_completo", utente.get("username", "OPERATORE")).upper()

    tab_stock, tab_movimenti, tab_sotto_scorta, tab_storico = st.tabs([
        "📋 Stock Live & Giacenze", 
        "🔄 Movimentazione (Carico/Scarico/Rettifica)", 
        "⚠️ Sotto Scorta & Riordini",
        "📜 Registro Movimenti"
    ])

    # --- TAB 1: STOCK LIVE ---
    with tab_stock:
        col_f1, col_f2 = st.columns([3, 1.5])
        with col_f1:
            ricerca = st.text_input("🔍 Ricerca rapida (PN, Descrizione, Ubicazione, Categoria)", placeholder="Digita per cercare...", key="input_ricerca_stock").strip()
        with col_f2:
            stato_sel = st.selectbox("Filtra per Stato:", ["Tutti", "Disponibili", "Sotto Scorta", "Esauriti"], key="select_stato_stock")

        # Evitiamo la tabella pesante fissa all'avvio se non si sta cercando nulla
        if not ricerca:
            st.info("💡 Digita almeno un carattere nella barra di ricerca sopra per visualizzare gli articoli in magazzino ed evitare rallentamenti.")
        else:
            stock_data = get_stock_completo(ricerca, stato_sel)

            if stock_data:
                df_stock = pd.DataFrame(stock_data)
                df_display = df_stock.rename(columns={
                    "pn_codice": "Part Number",
                    "descrizione": "Descrizione",
                    "categoria": "Categoria",
                    "ubicazione": "Ubicazione",
                    "giacenza": "Giacenza",
                    "scorta_minima": "Scorta Min.",
                    "fornitore_abituale": "Fornitore"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                st.markdown("#### 🏷️ Stampa Etichetta Selezionata")
                col_sel, col_btn = st.columns([3, 1])
                with col_sel:
                    pn_scelto = st.selectbox("Seleziona Articolo per Etichetta:", [x['pn_codice'] for x in stock_data])
                with col_btn:
                    art_info = next((x for x in stock_data if x['pn_codice'] == pn_scelto), None)
                    if art_info:
                        pdf_bytes = genera_pdf_etichetta_singola(
                            art_info['pn_codice'], art_info['descrizione'], art_info['ubicazione']
                        )
                        st.download_button(
                            "📄 Stampa Etichetta (PDF)",
                            data=pdf_bytes,
                            file_name=f"Etichetta_{pn_scelto}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
            else:
                st.info("Nessun articolo trovato con i criteri di ricerca inseriti.")

    # --- TAB 2: CARICO / SCARICO / RETTIFICA ---
    with tab_movimenti:
        tipo_op = st.radio("Seleziona Tipo Operazione:", ["📥 CARICO (Ingresso)", "📤 SCARICO (Uscita)", "✏️ RETTIFICA INVENTARIO"], horizontal=True)
        
        with st.form("form_movimentazione", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                pn_in = st.text_input("Part Number (PN) *").strip().upper()
                qta_in = st.number_input("Quantità *", min_value=1, value=1, step=1)
            with col_b:
                ubic_sugg = get_ubicazione_articolo(pn_in) if pn_in else "SCAFFALE-A1"
                ubic_in = st.text_input("Ubicazione Magazzino *", value=ubic_sugg).strip().upper()
                st.text_input("Operatore", value=nome_operatore, disabled=True)

            causale_in = ""
            cliente_in = None
            numero_ddt_in = ""
            data_ddt_in = datetime.now()
            note_in = ""

            if "SCARICO" in tipo_op:
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    causale_in = st.selectbox("Causale Uscita:", ["Vendita Cliente", "Consumo Interno", "Scarto/Danneggiato", "Manutenzione"])
                with col_s2:
                    clienti_lista = get_tutti_clienti()
                    opzioni_cli = {"Nessuno / Interno": None}
                    for c in clienti_lista:
                        opzioni_cli[f"{c['codice_cliente']} - {c['ragione_sociale']}"] = c['codice_cliente']
                    cli_scelto_lbl = st.selectbox("Cliente Destinatario:", list(opzioni_cli.keys()))
                    cliente_in = opzioni_cli[cli_scelto_lbl]
                with col_s3:
                    numero_ddt_in = st.text_input("N. DDT Uscita *").strip()
                    data_ddt_in = st.date_input("Data DDT Uscita", value=datetime.now())

            elif "CARICO" in tipo_op:
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    desc_in = st.text_input("Descrizione Articolo (Se nuovo)").strip()
                    cat_in = st.text_input("Categoria", value="Generico").strip()
                with col_c2:
                    scorta_min_in = st.number_input("Scorta Minima", min_value=0, value=5)
                    forn_in = st.text_input("Fornitore Abituale").strip()
                with col_c3:
                    numero_ddt_in = st.text_input("N. DDT Fornitore *").strip()
                    data_ddt_in = st.date_input("Data DDT Fornitore", value=datetime.now())

            elif "RETTIFICA" in tipo_op:
                note_in = st.text_input("Motivo della Rettifica *", placeholder="Es. Conteggio Inventario / Errore precedente").strip()

            if st.form_submit_button("🚀 Esegui Operazione", type="primary", use_container_width=True):
                if not pn_in or not ubic_in:
                    st.error("I campi Part Number e Ubicazione sono obbligatori.")
                elif ("CARICO" in tipo_op or "SCARICO" in tipo_op) and not numero_ddt_in:
                    st.error("Il Numero di DDT è obbligatorio per i Carichi e gli Scarichi.")
                elif "RETTIFICA" in tipo_op and not note_in:
                    st.error("Inserisci la motivazione per la rettifica.")
                else:
                    conn = get_db_connection()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            
                            # 1. Se CARICO e l'articolo non esiste, crea anagrafica
                            if "CARICO" in tipo_op:
                                cursor.execute("""
                                    INSERT INTO part_numbers (pn_codice, descrizione, categoria, ubicazione, scorta_minima, fornitore_abituale)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(pn_codice) DO UPDATE SET
                                        descrizione=COALESCE(EXCLUDED.descrizione, part_numbers.descrizione),
                                        ubicazione=EXCLUDED.ubicazione
                                """, (pn_in, desc_in if desc_in else f"Articolo {pn_in}", cat_in, ubic_in, scorta_min_in, forn_in))

                            # 2. Controllo e aggiornamento giacenza
                            cursor.execute("SELECT quantita_disponibile FROM magazzino_quantita WHERE pn_codice = ?", (pn_in,))
                            row_qta = cursor.fetchone()
                            qta_attuale = row_qta['quantita_disponibile'] if row_qta else 0

                            if "CARICO" in tipo_op:
                                nuova_qta = qta_attuale + qta_in
                                tipo_m = "CARICO"
                            elif "SCARICO" in tipo_op:
                                if qta_attuale < qta_in:
                                    st.error(f"Giacenza insufficiente per {pn_in}. Disponibili: {qta_attuale} pz.")
                                    st.stop()
                                nuova_qta = qta_attuale - qta_in
                                tipo_m = "SCARICO"
                            else: # RETTIFICA
                                nuova_qta = qta_in
                                tipo_m = "RETTIFICA"

                            cursor.execute("""
                                INSERT INTO magazzino_quantita (pn_codice, quantita_disponibile, ubicazione, operatore, data_ultimo_aggiornamento)
                                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(pn_codice) DO UPDATE SET
                                    quantita_disponibile = EXCLUDED.quantita_disponibile,
                                    ubicazione = EXCLUDED.ubicazione,
                                    operatore = EXCLUDED.operatore,
                                    data_ultimo_aggiornamento = CURRENT_TIMESTAMP
                            """, (pn_in, nuova_qta, ubic_in, nome_operatore))

                            # 3. Registrazione Audit Log con DDT
                            str_data_ddt = data_ddt_in.strftime('%Y-%m-%d') if data_ddt_in else None
                            cursor.execute("""
                                INSERT INTO storico_movimenti (pn_codice, tipo_movimento, quantita, causale, codice_cliente, numero_ddt, data_ddt, ubicazione, operatore, note)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (pn_in, tipo_m, qta_in, causale_in, cliente_in, numero_ddt_in if numero_ddt_in else None, str_data_ddt, ubic_in, nome_operatore, note_in))

                            conn.commit()
                            st.success(f"Operazione completata! Nuova giacenza per **{pn_in}**: **{nuova_qta} pz**.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore operazione: {e}")
                        finally:
                            conn.close()

    # --- TAB 3: SOTTO SCORTA & RIORDINI ---
    with tab_sotto_scorta:
        st.subheader("⚠️ Articoli in Esaurimento o Sotto Scorta")
        
        if "mostra_sotto_scorta" not in st.session_state:
            st.session_state["mostra_sotto_scorta"] = False

        if not st.session_state["mostra_sotto_scorta"]:
            st.info("💡 Per evitare rallentamenti all'avvio, l'elenco dettagliato degli articoli sotto scorta è nascosto.")
            if st.button("🔍 Mostra Articoli Sotto Scorta", type="primary"):
                st.session_state["mostra_sotto_scorta"] = True
                st.rerun()
        else:
            if st.button("🔄 Nascondi Elenco"):
                st.session_state["mostra_sotto_scorta"] = False
                st.rerun()

            stock_tutto = get_stock_completo(filtro_stato="Sotto Scorta")
            if stock_tutto:
                df_ss = pd.DataFrame(stock_tutto)
                st.dataframe(df_ss[["pn_codice", "descrizione", "giacenza", "scorta_minima", "fornitore_abituale"]], use_container_width=True, hide_index=True)
                
                pdf_riordino = genera_pdf_lista_riordino(stock_tutto)
                st.download_button(
                    "📥 Scarica Lista Riordino (PDF)",
                    data=pdf_riordino,
                    file_name=f"Lista_Riordino_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.success("🎉 Tutti gli articoli rispettano la scorta minima!")

    # --- TAB 4: REGISTRO MOVIMENTI ---
    with tab_storico:
        st.subheader("📜 Registro Movimenti Storici")
        
        c_d1, c_d2, c_pn = st.columns([1.5, 1.5, 2])
        with c_d1:
            d_inizio = st.date_input("Da Data:", value=datetime.now() - timedelta(days=30), key="reg_data_1")
        with c_d2:
            d_fine = st.date_input("A Data:", value=datetime.now(), key="reg_data_2")
        with c_pn:
            pn_f = st.text_input("Filtra per PN Articolo (Facoltativo):", key="reg_pn_f").strip()

        if st.button("🔍 Carica Registro Storico", type="primary"):
            st.session_state["carica_storico"] = True

        if st.session_state.get("carica_storico", False):
            movs = get_movimenti_storico(d_inizio, d_fine, pn_f)
            if movs:
                df_movs = pd.DataFrame(movs)
                df_movs_display = df_movs.rename(columns={
                    "pn_codice": "Part Number",
                    "tipo_movimento": "Tipo",
                    "quantita": "Q.tà",
                    "causale": "Causale",
                    "cliente": "Cliente",
                    "numero_ddt": "N. DDT",
                    "data_ddt": "Data DDT",
                    "ubicazione": "Ubicazione",
                    "operatore": "Operatore",
                    "note": "Note",
                    "data_ora": "Data/Ora"
                })
                st.dataframe(df_movs_display, use_container_width=True, hide_index=True)
            else:
                st.info("Nessun movimento registrato nel periodo selezionato.")
        else:
            st.info("💡 Seleziona l'intervallo di date desiderato e clicca su **'Carica Registro Storico'** per visualizzare i movimenti.")