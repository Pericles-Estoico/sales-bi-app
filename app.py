import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
SPREADSHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"

GIDS = {
    'produtos': 1037607798,
    'kits': 1569485799,
    'detalhes': 961459380,
}

# ==============================================================================
# FUNÇÕES
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados(tipo):
    if tipo not in GIDS:
        return pd.DataFrame()
    try:
        url = f"{BASE_URL}&gid={GIDS[tipo]}"
        df = pd.read_csv(url, timeout=15)
        return df
    except:
        return pd.DataFrame()

# ==============================================================================
# INTERFACE
# ==============================================================================
st.title("📊 Sales BI Pro")

st.sidebar.title("⚙️ Menu")
if st.sidebar.button("🔄 Atualizar"):
    st.cache_data.clear()
    st.rerun()

# ==============================================================================
# ABAS
# ==============================================================================
tab1, tab2, tab3 = st.tabs(["📦 Produtos", "🎁 Kits", "📝 Vendas"])

with tab1:
    st.subheader("📦 Produtos Cadastrados")
    df = carregar_dados('produtos')
    
    if not df.empty:
        st.success(f"✅ {len(df)} produtos encontrados")
        
        # Filtro de busca
        busca = st.text_input("🔍 Buscar produto:", "")
        if busca:
            df = df[df.iloc[:, 0].astype(str).str.contains(busca, case=False, na=False)]
        
        st.dataframe(df, width="stretch", height=500)
    else:
        st.error("❌ Erro ao carregar produtos")

with tab2:
    st.subheader("🎁 Kits Disponíveis")
    df = carregar_dados('kits')
    
    if not df.empty:
        st.success(f"✅ {len(df)} kits encontrados")
        st.dataframe(df, width="stretch", height=500)
        
        # Exemplo de decomposição
        if st.checkbox("🔬 Mostrar decomposição de um kit"):
            kit = df.iloc[0]
            st.write(f"**Kit:** {kit.iloc[0]}")
            st.write(f"**Componentes:** {kit.iloc[1]}")
            st.write(f"**Quantidades:** {kit.iloc[2]}")
    else:
        st.error("❌ Erro ao carregar kits")

with tab3:
    st.subheader("📝 Detalhes de Vendas")
    df = carregar_dados('detalhes')
    
    if not df.empty:
        st.success(f"✅ {len(df)} vendas registradas")
        
        # Métricas
        if 'Quantidade' in df.columns:
            total_qtd = df['Quantidade'].sum()
            st.metric("Total de Itens Vendidos", int(total_qtd))
        
        # Filtro por data
        if 'Data' in df.columns:
            datas = pd.to_datetime(df['Data'], errors='coerce')
            data_min = datas.min()
            data_max = datas.max()
            st.info(f"📅 Período: {data_min.date()} a {data_max.date()}")
        
        st.dataframe(df, width="stretch", height=500)
    else:
        st.error("❌ Erro ao carregar vendas")

st.sidebar.markdown("---")
st.sidebar.caption(f"Atualizado: {datetime.now().strftime('%H:%M:%S')}")
