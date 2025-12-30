import streamlit as st
import pandas as pd
from datetime import datetime
import time
import plotly.express as px

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
SPREADSHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"

# APENAS GIDS QUE FUNCIONAM (sem fórmulas dinâmicas)
GIDS_FUNCIONANDO = {
    'produtos': 1037607798,
    'kits': 1569485799,
    'dashboard': 749174572,
    'detalhes': 961459380,
}

# GIDS COM FÓRMULAS (não exportam CSV - HTTP 400)
GIDS_COM_FORMULAS = {
    'cnpj': 1218055125,
    'bcg': 1589145111,
    'precos': 1141986740,
    'giro': 364031804,
    'oportunidades': 563501913,
}

# ==============================================================================
# FUNÇÕES
# ==============================================================================
def carregar_dados_com_retry(tipo, max_tentativas=3):
    """Carrega dados com retry"""
    if tipo not in GIDS_FUNCIONANDO:
        return pd.DataFrame()
    
    url = f"{BASE_URL}&gid={GIDS_FUNCIONANDO[tipo]}"
    
    for tentativa in range(max_tentativas):
        try:
            df = pd.read_csv(url, timeout=30)
            return df
        except:
            if tentativa < max_tentativas - 1:
                time.sleep(2)
            else:
                return pd.DataFrame()

def format_currency_br(value):
    try: 
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: 
        return "R$ 0,00"

# ==============================================================================
# INTERFACE
# ==============================================================================
st.title("📊 Sales BI Pro")
st.caption("Sistema de Business Intelligence para Vendas")

# Avisos importantes
st.warning("""
⚠️ **AVISO IMPORTANTE:**  
Algumas abas (CNPJ, BCG, Preços, Giro, Oportunidades) contêm fórmulas dinâmicas e não podem ser exportadas via CSV.  
Para acessá-las, é necessário configurar **Google Sheets API** (instruções na sidebar).
""")

# Sidebar
with st.sidebar:
    st.title("⚙️ Menu")
    
    if st.button("🔄 Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ Cache limpo! Recarregue a página (F5)")
    
    st.divider()
    
    # Status
    st.subheader("📊 Status das Abas")
    st.success("✅ **Funcionando:**")
    st.write("- 📈 Visão Geral")
    st.write("- 📝 Detalhes de Vendas")
    st.write("- 📦 Produtos")
    st.write("- 🎁 Kits")
    
    st.error("❌ **Requer Google API:**")
    st.write("- 🏢 Por CNPJ")
    st.write("- ⭐ Matriz BCG")
    st.write("- 💲 Preços")
    st.write("- 🔄 Giro")
    st.write("- 🚀 Oportunidades")
    
    st.divider()
    
    with st.expander("ℹ️ Como configurar API"):
        st.markdown("""
        **Para acessar abas com fórmulas:**
        
        1. Criar Service Account no Google Cloud
        2. Compartilhar planilha com email da Service Account
        3. Adicionar credenciais no Streamlit Secrets
        
        📚 [Documentação completa](https://docs.streamlit.io/knowledge-base/tutorials/databases/gcs)
        """)
    
    st.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')}")

# ==============================================================================
# ABAS
# ==============================================================================
tabs = st.tabs([
    "📈 Visão Geral",
    "📝 Detalhes",
    "📦 Produtos",
    "🎁 Kits",
])

# ABA 1: VISÃO GERAL
with tabs[0]:
    st.header("📈 Dashboard Geral")
    
    with st.spinner("Carregando..."):
        df_dashboard = carregar_dados_com_retry('dashboard')
    
    if not df_dashboard.empty:
        st.success(f"✅ Dashboard carregado ({len(df_dashboard)} canais)")
        
        # Métricas
        col1, col2, col3 = st.columns(3)
        
        if 'Total Venda' in df_dashboard.columns:
            # Limpar valores monetários
            df_dashboard['Total Venda Num'] = df_dashboard['Total Venda'].apply(
                lambda x: float(str(x).replace('R$', '').replace('.', '').replace(',', '.').strip()) 
                if pd.notna(x) else 0
            )
            total = df_dashboard['Total Venda Num'].sum()
            col1.metric("💰 Total de Vendas", format_currency_br(total))
        
        if 'Lucro Bruto' in df_dashboard.columns:
            df_dashboard['Lucro Num'] = df_dashboard['Lucro Bruto'].apply(
                lambda x: float(str(x).replace('R$', '').replace('.', '').replace(',', '.').strip()) 
                if pd.notna(x) else 0
            )
            lucro = df_dashboard['Lucro Num'].sum()
            col2.metric("💵 Lucro Bruto", format_currency_br(lucro))
        
        if 'Quantidade' in df_dashboard.columns:
            qtd = df_dashboard['Quantidade'].sum()
            col3.metric("📦 Quantidade", int(qtd))
        
        # Gráfico
        if 'Canal' in df_dashboard.columns and 'Total Venda Num' in df_dashboard.columns:
            st.subheader("📊 Vendas por Canal")
            fig = px.bar(
                df_dashboard,
                x='Canal',
                y='Total Venda Num',
                title="Faturamento por Canal",
                labels={'Total Venda Num': 'Total de Vendas (R$)'}
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Tabela
        st.subheader("📋 Dados Detalhados")
        st.dataframe(df_dashboard, use_container_width=True)
    else:
        st.error("❌ Erro ao carregar dashboard")

# ABA 2: DETALHES
with tabs[1]:
    st.header("📝 Detalhes de Vendas (01/12 a 26/12)")
    
    with st.spinner("Carregando vendas..."):
        df_vendas = carregar_dados_com_retry('detalhes')
    
    if not df_vendas.empty:
        # Métricas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📋 Total", len(df_vendas))
        
        if 'Quantidade' in df_vendas.columns:
            col2.metric("📦 Itens", int(df_vendas['Quantidade'].sum()))
        
        if 'Data' in df_vendas.columns:
            datas = pd.to_datetime(df_vendas['Data'], errors='coerce')
            col3.metric("📅 Início", datas.min().strftime('%d/%m'))
            col4.metric("📅 Fim", datas.max().strftime('%d/%m'))
        
        # Filtros
        st.subheader("🔍 Filtros")
        col1, col2 = st.columns(2)
        
        with col1:
            if 'Canal' in df_vendas.columns:
                canais = ['Todos'] + sorted(df_vendas['Canal'].unique().tolist())
                canal = st.selectbox("Canal:", canais)
                if canal != 'Todos':
                    df_vendas = df_vendas[df_vendas['Canal'] == canal]
        
        with col2:
            if 'Produto' in df_vendas.columns:
                busca = st.text_input("Buscar produto:")
                if busca:
                    df_vendas = df_vendas[
                        df_vendas['Produto'].str.contains(busca, case=False, na=False)
                    ]
        
        st.dataframe(df_vendas, use_container_width=True, height=600)
        
        # Download
        csv = df_vendas.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download CSV",
            csv,
            "vendas.csv",
            "text/csv"
        )
    else:
        st.error("❌ Erro ao carregar vendas")

# ABA 3: PRODUTOS
with tabs[2]:
    st.header("📦 Produtos Cadastrados")
    
    with st.spinner("Carregando..."):
        df_produtos = carregar_dados_com_retry('produtos')
    
    if not df_produtos.empty:
        st.success(f"✅ {len(df_produtos)} produtos cadastrados")
        
        # Busca
        busca = st.text_input("🔍 Buscar produto:")
        if busca:
            mask = df_produtos.astype(str).apply(
                lambda x: x.str.contains(busca, case=False, na=False)
            ).any(axis=1)
            df_produtos = df_produtos[mask]
            st.info(f"Encontrados: {len(df_produtos)}")
        
        st.dataframe(df_produtos, use_container_width=True, height=600)
        
        # Download
        csv = df_produtos.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download", csv, "produtos.csv", "text/csv")
    else:
        st.error("❌ Erro ao carregar produtos")

# ABA 4: KITS
with tabs[3]:
    st.header("🎁 Kits Disponíveis")
    
    with st.spinner("Carregando..."):
        df_kits = carregar_dados_com_retry('kits')
    
    if not df_kits.empty:
        st.success(f"✅ {len(df_kits)} kits disponíveis")
        
        st.dataframe(df_kits, use_container_width=True, height=600)
        
        # Exemplo de decomposição
        st.divider()
        st.subheader("🔬 Exemplo de Decomposição de Kit")
        
        kit = df_kits.iloc[0]
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Kit:** {kit.iloc[0]}")
            st.write(f"**Preço:** {kit.iloc[3]}")
        
        with col2:
            comps = str(kit.iloc[1]).split(';')
            qtds = str(kit.iloc[2]).split(';')
            st.write("**Componentes:**")
            for c, q in zip(comps, qtds):
                st.write(f"- {c.strip()} → {q.strip()} un")
        
        # Download
        csv = df_kits.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download", csv, "kits.csv", "text/csv")
    else:
        st.error("❌ Erro ao carregar kits")
