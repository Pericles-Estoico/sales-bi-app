import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from modules.bcg_analysis import BCGAnalysis
from modules.pareto_analysis import ParetoAnalysis
from modules.stock_projection import StockProjection
from utils.data_processor import DataProcessor
from modules.google_sheets_integration import GoogleSheetsIntegration

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sales BI Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# CSS
# ---------------------------------------------------------
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
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------
if "historical_data" not in st.session_state:
    st.session_state.historical_data = pd.DataFrame()
if "channel_data" not in st.session_state:
    st.session_state.channel_data = {}

# ---------------------------------------------------------
# DEFINIÇÃO DE CANAIS
# ---------------------------------------------------------
CHANNELS = {
    "geral": {"name": "Vendas Gerais", "color": "#1f77b4", "icon": "📊"},
    "mercado_livre": {"name": "Mercado Livre", "color": "#FFE600", "icon": "🛒"},
    "shopee_matriz": {"name": "Shopee Matriz", "color": "#EE4D2D", "icon": "🛍️"},
    "shopee_150": {"name": "Shopee 1:50", "color": "#FF6B35", "icon": "🏪"},
    "shein": {"name": "Shein", "color": "#000000", "icon": "👗"},
}

# ---------------------------------------------------------
# FUNÇÃO AUXILIAR: ENVIAR PARA GOOGLE SHEETS
# ---------------------------------------------------------
def enviar_para_google_sheets(daily_data: pd.DataFrame, canal_nome: str):
    sheets = GoogleSheetsIntegration()
    if not sheets.is_connected():
        st.error(f"❌ Erro de conexão: {sheets.get_error()}")
        st.info("💡 Verifique o arquivo .streamlit/secrets.toml no Streamlit Cloud.")
        return

    success, message = sheets.upload_daily_data(daily_data, canal_nome)
    if success:
        st.success(message)
        st.info(f"🔗 [Abrir Planilha]({sheets.get_spreadsheet_url()})")
    else:
        st.error(message)


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------
with st.sidebar:
    st.title("📊 Sales BI Analytics")
    st.markdown("---")

    st.subheader("📁 Upload de Vendas")

    upload_type = st.radio(
        "Tipo de Upload",
        ["📊 Vendas Gerais", "🏪 Por Canal de Venda"],
        help="Escolha entre upload geral ou por canal específico",
    )

    # ------------------ UPLOAD GERAL ---------------------
    if upload_type == "📊 Vendas Gerais":
        st.markdown("### Upload Geral")
        uploaded_file = st.file_uploader(
            "Planilha de vendas diárias",
            type=["xlsx", "xls", "csv"],
            key="upload_geral",
            help="Upload da planilha consolidada de vendas",
        )

        if uploaded_file and st.button(
            "🔄 Processar Vendas Gerais", use_container_width=True
        ):
            with st.spinner("Processando..."):
                processor = DataProcessor()
                daily_data = processor.load_data(uploaded_file)
                daily_data["Canal"] = "Geral"
                daily_data["Data_Upload"] = datetime.now()

                if st.session_state.historical_data.empty:
                    st.session_state.historical_data = daily_data
                else:
                    st.session_state.historical_data = pd.concat(
                        [st.session_state.historical_data, daily_data],
                        ignore_index=True,
                    )

                st.success(f"✅ {len(daily_data)} registros processados!")
                st.balloons()

            if st.button(
                "📤 Enviar para Google Sheets",
                key="send_geral",
                use_container_width=True,
            ):
                enviar_para_google_sheets(daily_data, "Geral")

    # ------------------ UPLOAD POR CANAL -----------------
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

        if uploaded_file and st.button(
            f"🔄 Processar {CHANNELS[selected_channel]['name']}",
            use_container_width=True,
        ):
            with st.spinner("Processando..."):
                processor = DataProcessor()
                daily_data = processor.load_data(uploaded_file)
                daily_data["Canal"] = CHANNELS[selected_channel]["name"]
                daily_data["Canal_ID"] = selected_channel
                daily_data["Data_Upload"] = datetime.now()

                # salva por canal
                if selected_channel not in st.session_state.channel_data:
                    st.session_state.channel_data[selected_channel] = daily_data
                else:
                    st.session_state.channel_data[selected_channel] = pd.concat(
                        [st.session_state.channel_data[selected_channel], daily_data],
                        ignore_index=True,
                    )

                # histórico geral
                if st.session_state.historical_data.empty:
                    st.session_state.historical_data = daily_data
                else:
                    st.session_state.historical_data = pd.concat(
