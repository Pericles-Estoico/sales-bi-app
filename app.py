with st.sidebar:
    st.image(
        "https://via.placeholder.com/200x80/1f77b4/ffffff?text=Sales+BI",
        use_column_width=True,
    )
    st.title("📊 Sales BI Analytics")
    st.markdown("---")

    # Seleção de tipo de upload
    st.subheader("📁 Upload de Vendas")

    upload_type = st.radio(
        "Tipo de Upload",
        ["📊 Vendas Gerais", "🏪 Por Canal de Venda"],
        help="Escolha entre upload geral ou por canal específico",
    )

    # ===================== UPLOAD GERAL =====================
    if upload_type == "📊 Vendas Gerais":
        st.markdown("### Upload Geral")

        uploaded_file = st.file_uploader(
            "Planilha de vendas diárias",
            type=["xlsx", "xls", "csv"],
            key="upload_geral",
            help="Upload da planilha consolidada de vendas",
        )

        if uploaded_file:
            if st.button("🔄 Processar Vendas Gerais", use_container_width=True):
                with st.spinner("Processando..."):
                    processor = DataProcessor()
                    daily_data = processor.load_data(uploaded_file)

                    # Colunas adicionais
                    daily_data["Canal"] = "Geral"
                    daily_data["Data_Upload"] = datetime.now()

                    # Atualizar histórico
                    if not st.session_state.historical_data.empty:
                        st.session_state.historical_data = pd.concat(
                            [st.session_state.historical_data, daily_data],
                            ignore_index=True,
                        )
                    else:
                        st.session_state.historical_data = daily_data

                    # guardar último upload para envio ao Sheets
                    st.session_state.last_upload_df = daily_data
                    st.session_state.last_upload_sheet_name = "Geral"

                    st.success(f"✅ {len(daily_data)} registros processados!")
                    st.balloons()

        # botão de envio para Google Sheets (usa o que está no session_state)
        if (
            st.session_state.last_upload_df is not None
            and st.session_state.last_upload_sheet_name == "Geral"
        ):
            if st.button(
                "📤 Enviar último upload para Google Sheets",
                key="send_geral",
                use_container_width=True,
            ):
                with st.spinner("Enviando para Google Sheets..."):
                    sheets = GoogleSheetsIntegration()
                    if sheets.is_connected():
                        success, message = sheets.upload_daily_data(
                            st.session_state.last_upload_df, "Geral"
                        )
                        if success:
                            st.success(message)
                            st.info(
                                f"🔗 [Abrir Planilha]({sheets.get_spreadsheet_url()})"
                            )
                        else:
                            st.error(message)
                    else:
                        st.error(f"❌ Erro de conexão: {sheets.get_error()}")
                        st.info(
                            "💡 Verifique as configurações de Secrets no Streamlit Cloud"
                        )

    # ===================== UPLOAD POR CANAL =====================
    else:
        st.markdown("### Upload por Canal")

        selected_channel = st.selectbox(
            "Selecione o Canal",
            options=list(CHANNELS.keys()),
            format_func=lambda x: f"{CHANNELS[x]['icon']} {CHANNELS[x]['name']}",
        )

        st.markdown(
            f"""
            <div style="background: {CHANNELS[selected_channel]['color']}; 
                        padding: 10px; border-radius: 5px; color: white; text-align: center;">
                <strong>{CHANNELS[selected_channel]['icon']} {CHANNELS[selected_channel]['name']}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

        uploaded_file = st.file_uploader(
            f"Planilha {CHANNELS[selected_channel]['name']}",
            type=["xlsx", "xls", "csv"],
            key=f"upload_{selected_channel}",
            help=f"Upload de vendas do canal {CHANNELS[selected_channel]['name']}",
        )

        if uploaded_file:
            if st.button(
                f"🔄 Processar {CHANNELS[selected_channel]['name']}",
                use_container_width=True,
            ):
                with st.spinner("Processando..."):
                    processor = DataProcessor()
                    daily_data = processor.load_data(uploaded_file)

                    daily_data["Canal"] = CHANNELS[selected_channel]["name"]
                    daily_data["Canal_ID"] = selected_channel
                    daily_data["Data_Upload"] = datetime.now()

                    # Salvar por canal
                    if selected_channel not in st.session_state.channel_data:
                        st.session_state.channel_data[selected_channel] = daily_data
                    else:
                        st.session_state.channel_data[selected_channel] = pd.concat(
                            [st.session_state.channel_data[selected_channel], daily_data],
                            ignore_index=True,
                        )

                    # Adicionar ao histórico geral
                    if not st.session_state.historical_data.empty:
                        st.session_state.historical_data = pd.concat(
                            [st.session_state.historical_data, daily_data],
                            ignore_index=True,
                        )
                    else:
                        st.session_state.historical_data = daily_data

                    # guardar último upload para envio ao Sheets
                    st.session_state.last_upload_df = daily_data
                    st.session_state.last_upload_sheet_name = CHANNELS[selected_channel][
                        "name"
                    ]

                    st.success(
                        f"✅ {len(daily_data)} registros de {CHANNELS[selected_channel]['name']} processados!"
                    )
                    st.balloons()

        # botão de envio para Google Sheets para o canal atual
        if (
            st.session_state.last_upload_df is not None
            and st.session_state.last_upload_sheet_name
            == CHANNELS[selected_channel]["name"]
        ):
            if st.button(
                "📤 Enviar último upload para Google Sheets",
                key=f"send_{selected_channel}",
                use_container_width=True,
            ):
                with st.spinner("Enviando para Google Sheets..."):
                    sheets = GoogleSheetsIntegration()
                    if sheets.is_connected():
                        success, message = sheets.upload_daily_data(
                            st.session_state.last_upload_df,
                            CHANNELS[selected_channel]["name"],
                        )
                        if success:
                            st.success(message)
                            st.info(
                                f"🔗 [Abrir Planilha]({sheets.get_spreadsheet_url()})"
                            )
                        else:
                            st.error(message)
                    else:
                        st.error(f"❌ Erro de conexão: {sheets.get_error()}")
                        st.info(
                            "💡 Verifique as configurações de Secrets no Streamlit Cloud"
                        )

    st.markdown("---")

    # ---------------- RESUMO E FILTROS (resto do sidebar) ----------------
    if not st.session_state.historical_data.empty:
        st.subheader("📈 Dados Carregados")

        total_records = len(st.session_state.historical_data)
        st.metric("Total de Registros", f"{total_records:,}")

        if "Canal" in st.session_state.historical_data.columns:
            canais_unicos = st.session_state.historical_data["Canal"].unique()
            st.write("**Canais:**")
            for canal in canais_unicos:
                qtd = len(
                    st.session_state.historical_data[
                        st.session_state.historical_data["Canal"] == canal
                    ]
                )
                st.write(f"• {canal}: {qtd:,} registros")

    st.markdown("---")

    if not st.session_state.historical_data.empty:
        st.subheader("🔍 Filtros")

        if "Canal" in st.session_state.historical_data.columns:
            canais_disponiveis = ["Todos"] + list(
                st.session_state.historical_data["Canal"].unique()
            )
            selected_filter_channel = st.selectbox("Canal", canais_disponiveis)

        date_range = st.date_input(
            "Período",
            value=(datetime.now() - timedelta(days=30), datetime.now()),
        )

    st.markdown("---")
    st.caption("Desenvolvido com ❤️")
