import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
from modules.sheets_reader import SheetsReader

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
st.set_page_config(
    page_title="Sales BI Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

SPREADSHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"

# Mapeamento das abas
SHEET_MAPPING = {
    'produtos': {'gid': 1037607798, 'name': 'Produtos'},
    'kits': {'gid': 1569485799, 'name': 'Kits'},
    'dashboard': {'gid': 749174572, 'name': '1. Dashboard Geral'},
    'detalhes': {'gid': 961459380, 'name': '6. Detalhes'},
    'cnpj': {'gid': 1218055125, 'name': '2. Analise por CNPJ'},
    'bcg': {'gid': 1589145111, 'name': '5. Matriz BCG'},
    'precos': {'gid': 1141986740, 'name': '4. Precos Marketplaces'},
    'giro': {'gid': 364031804, 'name': '7. Giro de Produtos'},
    'oportunidades': {'gid': 563501913, 'name': '8. Oportunidades'},
}

# ==============================================================================
# FUNÇÕES DE CACHE
# ==============================================================================
@st.cache_resource
def get_sheets_reader():
    """Inicializa o leitor de Google Sheets"""
    return SheetsReader(SPREADSHEET_ID)

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados(tipo):
    """Carrega dados de uma aba específica"""
    reader = get_sheets_reader()
    
    if tipo not in SHEET_MAPPING:
        return pd.DataFrame()
    
    config = SHEET_MAPPING[tipo]
    df = reader.read_sheet_by_gid(config['gid'], config['name'])
    
    return df

def clean_currency(value):
    """Remove formatação de moeda e retorna float"""
    try:
        if pd.isna(value):
            return 0.0
        value_str = str(value).replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(value_str)
    except:
        return 0.0

def format_currency_br(value):
    """Formata valor como moeda brasileira"""
    try:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# ==============================================================================
# INTERFACE
# ==============================================================================
st.title("📊 Sales BI Pro")

# Sidebar
with st.sidebar:
    st.title("⚙️ Configurações")
    
    # Status da conexão
    reader = get_sheets_reader()
    status = reader.get_status()
    
    if status['realtime']:
        st.success(f"✅ {status['method']}")
        st.info("📡 Dados em tempo real")
    else:
        st.warning(f"⚠️ {status['method']}")
        st.info("💡 Algumas abas podem não funcionar (fórmulas complexas)")
    
    st.divider()
    
    # Botão de atualizar
    if st.button("🔄 Atualizar Dados", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ Cache limpo! Recarregue (F5)")
    
    st.divider()
    
    st.caption(f"🕐 Última atualização: {datetime.now().strftime('%H:%M:%S')}")

# ==============================================================================
# ABAS
# ==============================================================================
tabs = st.tabs([
    "📈 Visão Geral",
    "🏢 Por CNPJ",
    "⭐ Matriz BCG",
    "💲 Preços",
    "📝 Detalhes",
    "🔄 Giro",
    "🚀 Oportunidades",
    "📦 Produtos",
    "🎁 Kits"
])

# ABA 1: VISÃO GERAL
with tabs[0]:
    st.header("📈 Dashboard Geral")
    
    with st.spinner("Carregando dashboard..."):
        df_dashboard = carregar_dados('dashboard')
    
    if not df_dashboard.empty:
        st.success(f"✅ Dashboard carregado - {len(df_dashboard)} registros")
        
        # Processar dados
        if 'Total Venda' in df_dashboard.columns:
            df_dashboard['Total_Venda_Num'] = df_dashboard['Total Venda'].apply(clean_currency)
        
        if 'Lucro Bruto' in df_dashboard.columns:
            df_dashboard['Lucro_Bruto_Num'] = df_dashboard['Lucro Bruto'].apply(clean_currency)
        
        # Métricas
        col1, col2, col3 = st.columns(3)
        
        if 'Total_Venda_Num' in df_dashboard.columns:
            total_vendas = df_dashboard['Total_Venda_Num'].sum()
            col1.metric("💰 Total de Vendas", format_currency_br(total_vendas))
        
        if 'Lucro_Bruto_Num' in df_dashboard.columns:
            lucro_bruto = df_dashboard['Lucro_Bruto_Num'].sum()
            col2.metric("💵 Lucro Bruto", format_currency_br(lucro_bruto))
            
            # Margem
            if 'Total_Venda_Num' in df_dashboard.columns and total_vendas > 0:
                margem = (lucro_bruto / total_vendas) * 100
                col3.metric("📊 Margem", f"{margem:.1f}%")
        
        # Gráfico
        if 'Canal' in df_dashboard.columns and 'Total_Venda_Num' in df_dashboard.columns:
            st.subheader("📊 Vendas por Canal")
            fig = px.bar(
                df_dashboard,
                x='Canal',
                y='Total_Venda_Num',
                title="Faturamento por Canal",
                labels={'Total_Venda_Num': 'Total (R$)'}
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Tabela
        st.subheader("📋 Dados Completos")
        st.dataframe(df_dashboard, use_container_width=True)
        
    else:
        st.error("❌ Nenhum dado encontrado no Dashboard")
        st.info("💡 Verifique se a planilha está compartilhada e se há dados")

# ABA 2: POR CNPJ
with tabs[1]:
    st.header("🏢 Análise por CNPJ")
    
    with st.spinner("Carregando..."):
        df_cnpj = carregar_dados('cnpj')
    
    if not df_cnpj.empty:
        st.success(f"✅ {len(df_cnpj)} registros")
        st.dataframe(df_cnpj, use_container_width=True, height=500)
    else:
        st.warning("⚠️ Esta aba contém fórmulas dinâmicas")
        st.info("💡 Configure Google Sheets API para acessar estes dados")

# ABA 3: MATRIZ BCG
with tabs[2]:
    st.header("⭐ Matriz BCG")
    
    with st.spinner("Carregando..."):
        df_bcg = carregar_dados('bcg')
    
    if not df_bcg.empty:
        st.success(f"✅ {len(df_bcg)} produtos")
        st.dataframe(df_bcg, use_container_width=True, height=500)
    else:
        st.warning("⚠️ Esta aba contém fórmulas dinâmicas")
        st.info("💡 Configure Google Sheets API para acessar estes dados")

# ABA 4: PREÇOS
with tabs[3]:
    st.header("💲 Preços Marketplaces")
    
    with st.spinner("Carregando..."):
        df_precos = carregar_dados('precos')
    
    if not df_precos.empty:
        st.success(f"✅ {len(df_precos)} registros")
        st.dataframe(df_precos, use_container_width=True, height=500)
    else:
        st.warning("⚠️ Esta aba contém fórmulas dinâmicas")
        st.info("💡 Configure Google Sheets API para acessar estes dados")

# ABA 5: DETALHES
with tabs[4]:
    st.header("📝 Detalhes de Vendas")
    
    with st.spinner("Carregando vendas..."):
        df_detalhes = carregar_dados('detalhes')
    
    if not df_detalhes.empty:
        st.success(f"✅ {len(df_detalhes)} vendas registradas")
        
        # Filtros
        col1, col2 = st.columns(2)
        
        with col1:
            if 'Canal' in df_detalhes.columns:
                canais = ['Todos'] + sorted(df_detalhes['Canal'].unique().tolist())
                canal = st.selectbox("🏪 Canal:", canais)
                if canal != 'Todos':
                    df_detalhes = df_detalhes[df_detalhes['Canal'] == canal]
        
        with col2:
            if 'Produto' in df_detalhes.columns:
                busca = st.text_input("🔍 Buscar produto:")
                if busca:
                    df_detalhes = df_detalhes[
                        df_detalhes['Produto'].str.contains(busca, case=False, na=False)
                    ]
        
        st.dataframe(df_detalhes, use_container_width=True, height=500)
        
        # Download
        csv = df_detalhes.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", csv, "vendas.csv", "text/csv")
        
    else:
        st.error("❌ Nenhuma venda encontrada")

# ABA 6: GIRO
with tabs[5]:
    st.header("🔄 Giro de Produtos")
    
    with st.spinner("Carregando..."):
        df_giro = carregar_dados('giro')
    
    if not df_giro.empty:
        st.success(f"✅ {len(df_giro)} produtos")
        st.dataframe(df_giro, use_container_width=True, height=500)
    else:
        st.warning("⚠️ Esta aba contém fórmulas dinâmicas")
        st.info("💡 Configure Google Sheets API para acessar estes dados")

# ABA 7: OPORTUNIDADES
with tabs[6]:
    st.header("🚀 Oportunidades")
    
    with st.spinner("Carregando..."):
        df_oport = carregar_dados('oportunidades')
    
    if not df_oport.empty:
        st.success(f"✅ {len(df_oport)} oportunidades")
        st.dataframe(df_oport, use_container_width=True, height=500)
    else:
        st.warning("⚠️ Esta aba contém fórmulas dinâmicas")
        st.info("💡 Configure Google Sheets API para acessar estes dados")

# ABA 8: PRODUTOS
with tabs[7]:
    st.header("📦 Produtos Cadastrados")
    
    with st.spinner("Carregando produtos..."):
        df_produtos = carregar_dados('produtos')
    
    if not df_produtos.empty:
        st.success(f"✅ {len(df_produtos)} produtos cadastrados")
        
        # Busca
        busca = st.text_input("🔍 Buscar produto:", key="busca_produtos")
        if busca:
            mask = df_produtos.astype(str).apply(
                lambda x: x.str.contains(busca, case=False, na=False)
            ).any(axis=1)
            df_produtos = df_produtos[mask]
        
        st.dataframe(df_produtos, use_container_width=True, height=500)
        
        # Download
        csv = df_produtos.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download", csv, "produtos.csv", "text/csv")
        
    else:
        st.error("❌ Erro ao carregar produtos")

# ABA 9: KITS
with tabs[8]:
    st.header("🎁 Kits Disponíveis")
    
    with st.spinner("Carregando kits..."):
        df_kits = carregar_dados('kits')
    
    if not df_kits.empty:
        st.success(f"✅ {len(df_kits)} kits disponíveis")
        
        st.dataframe(df_kits, use_container_width=True, height=500)
        
        # Exemplo de decomposição
        if len(df_kits) > 0:
            st.divider()
            st.subheader("🔬 Exemplo de Kit")
            
            kit = df_kits.iloc[0]
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Kit:** {kit.iloc[0]}")
                if len(kit) > 3:
                    st.write(f"**Preço:** {kit.iloc[3]}")
            
            with col2:
                if len(kit) > 2:
                    comps = str(kit.iloc[1]).split(';')
                    qtds = str(kit.iloc[2]).split(';')
                    st.write("**Componentes:**")
                    for c, q in zip(comps[:5], qtds[:5]):  # Limita a 5
                        st.write(f"- {c.strip()} → {q.strip()} un")
        
        # Download
        csv = df_kits.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download", csv, "kits.csv", "text/csv")
        
    else:
        st.error("❌ Erro ao carregar kits")
