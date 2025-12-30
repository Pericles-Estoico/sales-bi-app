import streamlit as st
import pandas as pd
from datetime import datetime
import time

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
# FUNÇÕES COM RETRY
# ==============================================================================
def carregar_dados_com_retry(tipo, max_tentativas=3):
    """Carrega dados com retry automático"""
    if tipo not in GIDS:
        return pd.DataFrame()
    
    url = f"{BASE_URL}&gid={GIDS[tipo]}"
    
    for tentativa in range(max_tentativas):
        try:
            # Timeout maior
            df = pd.read_csv(url, timeout=30)
            return df
        except Exception as e:
            if tentativa < max_tentativas - 1:
                time.sleep(2)  # Aguarda 2 segundos entre tentativas
                continue
            else:
                st.error(f"❌ Erro após {max_tentativas} tentativas: {str(e)}")
                return pd.DataFrame()

# ==============================================================================
# INTERFACE
# ==============================================================================
st.title("📊 Sales BI Pro")
st.caption("Sistema de Business Intelligence para Vendas")

# Sidebar
with st.sidebar:
    st.title("⚙️ Configurações")
    
    if st.button("🔄 Recarregar Dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    
    # Status de conexão
    st.subheader("📡 Status")
    with st.spinner("Testando conexão..."):
        df_test = carregar_dados_com_retry('produtos')
        if not df_test.empty:
            st.success("✅ Conectado")
            st.metric("Produtos", len(df_test))
        else:
            st.error("❌ Erro de conexão")
    
    st.divider()
    st.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')}")

# ==============================================================================
# ABAS
# ==============================================================================
tab1, tab2, tab3 = st.tabs(["📦 Produtos", "🎁 Kits", "📝 Detalhes de Vendas"])

# TAB 1: PRODUTOS
with tab1:
    st.header("📦 Produtos Cadastrados")
    
    with st.spinner("Carregando produtos..."):
        df_produtos = carregar_dados_com_retry('produtos')
    
    if not df_produtos.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Produtos", len(df_produtos))
        col2.metric("Colunas", len(df_produtos.columns))
        col3.success("✅ Dados carregados")
        
        # Busca
        busca = st.text_input("🔍 Buscar produto por código ou nome:")
        if busca:
            mascara = df_produtos.astype(str).apply(lambda x: x.str.contains(busca, case=False, na=False)).any(axis=1)
            df_produtos = df_produtos[mascara]
            st.info(f"🔍 {len(df_produtos)} resultados encontrados")
        
        # Tabela
        st.dataframe(
            df_produtos,
            use_container_width=True,
            height=600
        )
        
        # Download
        csv = df_produtos.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download CSV",
            csv,
            "produtos.csv",
            "text/csv",
        )
    else:
        st.error("❌ Não foi possível carregar os produtos")
        st.info("💡 Clique em 'Recarregar Dados' na sidebar")

# TAB 2: KITS
with tab2:
    st.header("🎁 Kits Disponíveis")
    
    with st.spinner("Carregando kits..."):
        df_kits = carregar_dados_com_retry('kits')
    
    if not df_kits.empty:
        col1, col2 = st.columns(2)
        col1.metric("Total de Kits", len(df_kits))
        col2.success("✅ Dados carregados")
        
        # Tabela
        st.dataframe(
            df_kits,
            use_container_width=True,
            height=600
        )
        
        # Exemplo de decomposição
        st.divider()
        st.subheader("🔬 Exemplo de Decomposição de Kit")
        
        kit_exemplo = df_kits.iloc[0]
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Código do Kit:** {kit_exemplo.iloc[0]}")
            st.write(f"**Preço de Venda:** {kit_exemplo.iloc[3]}")
        
        with col2:
            componentes = str(kit_exemplo.iloc[1]).split(';')
            quantidades = str(kit_exemplo.iloc[2]).split(';')
            
            st.write("**Componentes:**")
            for comp, qtd in zip(componentes, quantidades):
                st.write(f"- {comp.strip()} → {qtd.strip()} unidade(s)")
    else:
        st.error("❌ Não foi possível carregar os kits")

# TAB 3: DETALHES DE VENDAS
with tab3:
    st.header("📝 Detalhes de Vendas")
    
    with st.spinner("Carregando vendas..."):
        df_vendas = carregar_dados_com_retry('detalhes')
    
    if not df_vendas.empty:
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("Total de Vendas", len(df_vendas))
        
        if 'Quantidade' in df_vendas.columns:
            total_itens = df_vendas['Quantidade'].sum()
            col2.metric("Itens Vendidos", int(total_itens))
        
        if 'Data' in df_vendas.columns:
            try:
                datas = pd.to_datetime(df_vendas['Data'], errors='coerce')
                col3.metric("Período Inicial", datas.min().strftime('%d/%m/%Y'))
                col4.metric("Período Final", datas.max().strftime('%d/%m/%Y'))
            except:
                pass
        
        # Filtros
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            if 'Canal' in df_vendas.columns:
                canais = ['Todos'] + list(df_vendas['Canal'].unique())
                canal_selecionado = st.selectbox("Filtrar por Canal:", canais)
                
                if canal_selecionado != 'Todos':
                    df_vendas = df_vendas[df_vendas['Canal'] == canal_selecionado]
        
        with col2:
            if 'Produto' in df_vendas.columns:
                busca_produto = st.text_input("Buscar produto:")
                if busca_produto:
                    df_vendas = df_vendas[df_vendas['Produto'].str.contains(busca_produto, case=False, na=False)]
        
        # Tabela
        st.dataframe(
            df_vendas,
            use_container_width=True,
            height=600
        )
        
        # Download
        csv = df_vendas.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download CSV",
            csv,
            "vendas.csv",
            "text/csv",
        )
    else:
        st.error("❌ Não foi possível carregar as vendas")
