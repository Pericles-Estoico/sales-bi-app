import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px

# Configuração da página
st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
SPREADSHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"

# Mapeamento de abas
GIDS = {
    'produtos': 1037607798,
    'kits': 1569485799,
    'dashboard': 749174572,
    'detalhes': 961459380,
}

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados(tipo):
    """Carrega dados do Google Sheets"""
    if tipo not in GIDS:
        return pd.DataFrame()
    
    try:
        url = f"{BASE_URL}&gid={GIDS[tipo]}"
        df = pd.read_csv(url, timeout=15)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar {tipo}: {e}")
        return pd.DataFrame()

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
st.title("📊 Sales BI Pro")

# Sidebar
st.sidebar.title("⚙️ Configurações")

if st.sidebar.button("🔄 Atualizar Dados"):
    st.cache_data.clear()
    st.success("✅ Cache limpo!")
    st.rerun()

st.sidebar.divider()

# ==============================================================================
# ABAS
# ==============================================================================
tabs = st.tabs([
    "📈 Visão Geral", 
    "📝 Detalhes", 
    "📋 Relatório de Produção"
])

# ABA 1: Visão Geral
with tabs[0]:
    st.subheader("📊 Dashboard Geral")
    
    with st.spinner("Carregando dashboard..."):
        df_dashboard = carregar_dados('dashboard')
    
    if not df_dashboard.empty:
        st.success(f"✅ Dados carregados: {len(df_dashboard)} linhas")
        st.dataframe(df_dashboard.head(20), width="stretch")
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 2: Detalhes
with tabs[1]:
    st.subheader("📝 Detalhes de Vendas")
    
    with st.spinner("Carregando detalhes..."):
        df_detalhes = carregar_dados('detalhes')
    
    if not df_detalhes.empty:
        st.success(f"✅ Dados carregados: {len(df_detalhes)} linhas")
        st.dataframe(df_detalhes.head(50), width="stretch")
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 3: Relatório de Produção
with tabs[2]:
    st.subheader("📋 Relatório de Produção")
    
    st.markdown("""
    **Fluxo:**
    1. Upload de vendas por marketplace
    2. Decomposição de kits
    3. Verificação de estoque
    4. Geração de relatórios
    """)
    
    # Import local para evitar problemas
    try:
        from modules.production_analyzer import ProductionAnalyzer
        from modules.production_report_generator import ProductionReportGenerator
        
        # Data de análise
        data_analise = st.date_input("Data:", datetime.now())
        
        # Upload de vendas
        marketplace = st.selectbox("Marketplace:", ["Mercado Livre", "Shopee 1:50", "Shein"])
        uploaded = st.file_uploader("Arquivo de vendas:", type=["xlsx", "csv"])
        
        if uploaded:
            try:
                df_vendas = pd.read_excel(uploaded) if uploaded.name.endswith('.xlsx') else pd.read_csv(uploaded)
                st.success(f"✅ {len(df_vendas)} linhas carregadas")
                st.dataframe(df_vendas.head(10), width="stretch")
            except Exception as e:
                st.error(f"❌ Erro: {e}")
    
    except ImportError as e:
        st.warning(f"⚠️ Módulos de produção não disponíveis: {e}")
        st.info("💡 Esta funcionalidade será habilitada em breve.")

st.sidebar.markdown("---")
st.sidebar.caption(f"Última atualização: {datetime.now().strftime('%H:%M:%S')}")
