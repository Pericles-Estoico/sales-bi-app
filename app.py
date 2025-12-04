import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from modules.bcg_analysis import BCGAnalysis
from modules.pareto_analysis import ParetoAnalysis
from modules.stock_projection import StockProjection
from utils.data_processor import DataProcessor
from modules.google_sheets_integration import GoogleSheetsIntegration
import os
import json

# ---------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Sales BI Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown(
    """
    <style>
        .main {padding: 0rem 1rem;}
        .stMetric {
            background-color: #f0f2f6;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .upload-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 15px;
        }
        .channel-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 12px;
            font-weight: 600;
            margin: 3px;
        }
        .badge-ml {background: #FFE600; color: #333;}
        .badge-shopee {background: #EE4D2D; color: white;}
        .badge-shein {background: #000; color: white;}
        .badge-geral {background: #1f77b4; color: white;}
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------
if "historical_data" not in st.session_state:
    st.session_state.historical_data = pd.DataFrame()

if "channel_data" not in st.session_state:
    st.session_state.channel_data = {}

# ---------------------------------------------------------------------
# DEFINIÇÃO DE CANAIS
# ---------------------------------------------------------------------
CHANNELS = {
    "geral": {"name": "Vendas Gerais", "color": "#1f77b4", "icon": "📊"},
    "mercado_livre": {"name": "Mercado Livre", "color": "#FFE600", "icon": "🛒"},
    "shopee_matriz": {"name": "Shopee Matriz", "color": "#EE4D2D", "icon": "🛍️"},
    "shopee_150": {"name": "Shopee 1:50", "color": "#FF6B35", "icon": "🏪"},
    "shein": {"name": "Shein", "color": "#000000", "icon": "👗"},
}

# ---------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------
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

    # ---------------- UPLOAD GERAL ----------------
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

                    st.success(f"✅ {len(daily_data)} registros processados!")
                    st.balloons()

        # botão de envio para Google Sheets
        if (
            uploaded_file
            and "daily_data" in locals()
            and st.button(
                "📤 Enviar para Google Sheets",
                key="send_geral",
                use_container_width=True,
            )
        ):
            with st.spinner("Enviando para Google Sheets..."):
                sheets = GoogleSheetsIntegration()
                if sheets.is_connected():
                    success, message = sheets.upload_daily_data(daily_data, "Geral")
                    if success:
                        st.success(message)
                        st.info(
                            f"🔗 [Abrir Planilha]({sheets.get_spreadsheet_url()})"
                        )
                    else:
                        st.error(message)
                else:
                    st.error(f"❌ Erro de conexão: {sheets.get_error()}")
                    st.info("💡 Verifique as configurações de Secrets no Streamlit Cloud")

    # ---------------- UPLOAD POR CANAL ----------------
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

                    st.success(
                        f"✅ {len(daily_data)} registros de {CHANNELS[selected_channel]['name']} processados!"
                    )
                    st.balloons()

        # botão de envio para Google Sheets
        if (
            uploaded_file
            and "daily_data" in locals()
            and st.button(
                "📤 Enviar para Google Sheets",
                key=f"send_{selected_channel}",
                use_container_width=True,
            )
        ):
            with st.spinner("Enviando para Google Sheets..."):
                sheets = GoogleSheetsIntegration()
                if sheets.is_connected():
                    success, message = sheets.upload_daily_data(
                        daily_data, CHANNELS[selected_channel]["name"]
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
                    st.info("💡 Verifique as configurações de Secrets no Streamlit Cloud")

    st.markdown("---")

    # -----------------------------------------------------------------
    # RESUMO DE UPLOADS NA SIDEBAR
    # -----------------------------------------------------------------
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

    # -----------------------------------------------------------------
    # FILTROS NA SIDEBAR
    # -----------------------------------------------------------------
    if not st.session_state.historical_data.empty:
        st.subheader("🔍 Filtros")

        # Filtro de canal
        if "Canal" in st.session_state.historical_data.columns:
            canais_disponiveis = ["Todos"] + list(
                st.session_state.historical_data["Canal"].unique()
            )
            selected_filter_channel = st.selectbox("Canal", canais_disponiveis)

        # Filtro de data (últimos 30 dias como padrão)
        date_range = st.date_input(
            "Período",
            value=(datetime.now() - timedelta(days=30), datetime.now()),
        )

    st.markdown("---")
    st.caption("Desenvolvido com ❤️")

# ---------------------------------------------------------------------
# CONTEÚDO PRINCIPAL
# ---------------------------------------------------------------------
if st.session_state.historical_data.empty:
    # Tela inicial sem dados
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 40px; border-radius: 15px; color: white; margin-bottom: 30px;">
            <h1 style="color: white; margin-bottom: 15px;">👋 Bem-vindo ao Sales BI Analytics</h1>
            <p style="font-size: 18px; margin-bottom: 20px;">
                Sistema profissional de Business Intelligence para análise de vendas multicanal
            </p>
            <p style="font-size: 14px; opacity: 0.9;">
                📤 Faça upload das vendas na barra lateral para começar
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📊 Upload Geral")
        st.info(
            """
            **Vendas Consolidadas**
            
            Faça upload de uma planilha com todas as vendas do dia, independente do canal.
            
            ✅ Análise geral de performance  
            ✅ Visão consolidada do negócio  
            ✅ KPIs totais
            """
        )

    with col2:
        st.markdown("### 🏪 Upload por Canal")
        st.success(
            """
            **Vendas Segmentadas**
            
            Faça upload separado por canal de venda para análise detalhada.
            
            ✅ Mercado Livre  
            ✅ Shopee Matriz  
            ✅ Shopee 1:50  
            ✅ Shein
            """
        )

    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.info("📈 **Matriz BCG**\n\nClassifique produtos estrategicamente")

    with col2:
        st.success("📊 **Pareto 80/20**\n\nIdentifique produtos-chave")

    with col3:
        st.warning("📦 **Projeção de Estoque**\n\nPrevisões inteligentes")

    with col4:
        st.error("📉 **Análise Multicanal**\n\nCompare performance")

else:
    # -----------------------------------------------------------------
    # APLICAR FILTROS
    # -----------------------------------------------------------------
    df_filtered = st.session_state.historical_data.copy()

    # Garante datetime
    if "Data" in df_filtered.columns:
        df_filtered["Data"] = pd.to_datetime(df_filtered["Data"])

    # Filtro de canal vindo da sidebar
    if "selected_filter_channel" in globals() and selected_filter_channel != "Todos":
        df_filtered = df_filtered[df_filtered["Canal"] == selected_filter_channel]

    # Filtro de período vindo da sidebar
    if "date_range" in globals():
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_date, end_date = date_range
            if "Data" in df_filtered.columns:
                mask = (df_filtered["Data"].dt.date >= start_date) & (
                    df_filtered["Data"].dt.date <= end_date
                )
                df_filtered = df_filtered[mask]

    # -----------------------------------------------------------------
    # DASHBOARD PRINCIPAL
    # -----------------------------------------------------------------
    st.title("📊 Dashboard de Vendas")

    # KPIs principais
    col1, col2, col3, col4, col5 = st.columns(5)

    total_vendas = df_filtered["Quantidade"].sum()
    produtos_vendidos = df_filtered["Produto"].nunique()
    canais_ativos = (
        df_filtered["Canal"].nunique() if "Canal" in df_filtered.columns else 1
    )

    if "Data" in df_filtered.columns:
        hoje = df_filtered["Data"].max()
        ontem = hoje - timedelta(days=1)

        vendas_hoje = df_filtered[df_filtered["Data"] == hoje]["Quantidade"].sum()
        vendas_ontem = df_filtered[df_filtered["Data"] == ontem]["Quantidade"].sum()
        crescimento = (
            (vendas_hoje - vendas_ontem) / vendas_ontem * 100
            if vendas_ontem > 0
            else 0
        )

        media_diaria = (
            df_filtered.groupby("Data")["Quantidade"].sum().mean()
            if not df_filtered.empty
            else 0
        )
    else:
        vendas_hoje = 0
        crescimento = 0
        media_diaria = 0

    with col1:
        st.metric("Vendas Hoje", f"{vendas_hoje:,.0f}", f"{crescimento:+.1f}%")

    with col2:
        st.metric("Produtos", f"{produtos_vendidos}")

    with col3:
        st.metric("Canais Ativos", f"{canais_ativos}")

    with col4:
        st.metric("Média Diária", f"{media_diaria:,.0f}")

    with col5:
        st.metric("Total Período", f"{total_vendas:,.0f}")

    # -----------------------------------------------------------------
    # ABAS
    # -----------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Visão Geral", "Matriz BCG", "Pareto 80/20", "Projeção de Estoque", "Multicanal"]
    )

    # ================= TAB 1: VISÃO GERAL =================
    with tab1:
        st.subheader("📈 Evolução de Vendas")

        if "Data" in df_filtered.columns:
            df_diario = (
                df_filtered.groupby("Data")["Quantidade"]
                .sum()
                .reset_index()
                .sort_values("Data")
            )

            fig = px.line(
                df_diario, x="Data", y="Quantidade", markers=True, title="Vendas por Dia"
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("📦 Top Produtos do Período")
        top_produtos = (
            df_filtered.groupby("Produto")["Quantidade"]
            .sum()
            .reset_index()
            .sort_values("Quantidade", ascending=False)
            .head(20)
        )
        st.dataframe(top_produtos, use_container_width=True, height=400)

    # ================= TAB 2: MATRIZ BCG =================
    with tab2:
        st.subheader("🎯 Matriz BCG")

        if len(df_filtered) > 10:
            bcg = BCGAnalysis(df_filtered)
            bcg_results = bcg.analyze()

            col1, col2, col3, col4 = st.columns(4)

            for col, (categoria, emoji) in zip(
                [col1, col2, col3, col4],
                [
                    ("Estrela", "⭐"),
                    ("Vaca Leiteira", "🐄"),
                    ("Interrogação", "❓"),
                    ("Abacaxi", "🍍"),
                ],
            ):
                with col:
                    cat_data = bcg_results[bcg_results["Categoria"] == categoria]
                    st.metric(f"{emoji} {categoria}", len(cat_data))
                    st.caption(f"{cat_data['Quantidade'].sum():,.0f} unidades")

            fig = bcg.plot_bcg_matrix(bcg_results)
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(bcg_results, use_container_width=True, height=400)
        else:
            st.info("📊 Carregue mais dados para análise BCG")

    # ================= TAB 3: PARETO =================
    with tab3:
        st.subheader("📊 Análise de Pareto 80/20")

        pareto = ParetoAnalysis(df_filtered)
        pareto_results = pareto.analyze()

        fig = pareto.plot_pareto(pareto_results)
        st.plotly_chart(fig, use_container_width=True)

        insights = pareto.get_insights(pareto_results)

        col1, col2 = st.columns(2)
        with col1:
            st.success("**💡 Insight Pareto**")
            st.write(
                f"**{insights['produtos_top_80']} produtos** "
                f"({insights['percentual_produtos_top']:.1f}%) geram **80%** das vendas"
            )

        with col2:
            st.dataframe(
                pareto_results.head(20),
                use_container_width=True,
                height=300,
            )

        # Alertas estratégicos simples (pode ir refinando depois)
        alerts = []
        if insights.get("produtos_top_80", 0) > 50:
            alerts.append(
                {
                    "Mensagem": "Muitos produtos para compor 80% das vendas. "
                    "Avalie enxugar o portfólio e focar nos campeões.",
                }
            )

        if alerts:
            st.markdown("### ⚠️ Alertas Estratégicos")
            for alert in alerts:
                st.warning(f"🟡 {alert['Mensagem']}")

    # ================= TAB 4: PROJEÇÃO DE ESTOQUE =================
    with tab4:
        st.subheader("📦 Projeção de Estoque")

        st.info(
            "Integração com `StockProjection` pode ser configurada aqui para "
            "prever ruptura, giro e cobertura de estoque por produto."
        )

    # ================= TAB 5: ANÁLISE MULTICANAL =================
    with tab5:
        st.subheader("🏪 Análise Multicanal")

        if "Canal" in df_filtered.columns and df_filtered["Canal"].nunique() > 1:
            df_canal_time = (
                df_filtered.groupby(["Data", "Canal"])["Quantidade"]
                .sum()
                .reset_index()
            )

            fig = px.line(
                df_canal_time,
                x="Data",
                y="Quantidade",
                color="Canal",
                title="Evolução de Vendas por Canal",
                markers=True,
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📊 Comparativo de Canais")

            df_comp = (
                df_filtered.groupby("Canal").agg(
                    {
                        "Quantidade": ["sum", "mean", "count"],
                        "Produto": "nunique",
                    }
                )
                .reset_index()
            )
            df_comp.columns = [
                "Canal",
                "Total Vendas",
                "Média Diária",
                "Num Vendas",
                "Produtos Únicos",
            ]
            df_comp = df_comp.sort_values("Total Vendas", ascending=False)

            st.dataframe(df_comp, use_container_width=True)
        else:
            st.info("Carregue vendas de mais de um canal para ver a análise multicanal.")
