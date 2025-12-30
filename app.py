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

GIDS = {
    'produtos': 1037607798,
    'kits': 1569485799,
    'dashboard': 749174572,
    'detalhes': 961459380,
    'cnpj': 1218055125,
    'bcg': 1589145111,
    'precos': 1141986740,
    'giro': 364031804,
    'oportunidades': 563501913,
}

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
def carregar_dados_com_retry(tipo, max_tentativas=3):
    """Carrega dados com retry automático"""
    if tipo not in GIDS:
        return pd.DataFrame()
    
    url = f"{BASE_URL}&gid={GIDS[tipo]}"
    
    for tentativa in range(max_tentativas):
        try:
            df = pd.read_csv(url, timeout=30)
            return df
        except Exception as e:
            if tentativa < max_tentativas - 1:
                time.sleep(2)
                continue
            else:
                return pd.DataFrame()

def format_currency_br(value):
    try: 
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: 
        return "R$ 0,00"

def format_percent_br(value):
    try: 
        return f"{value * 100:.2f}%".replace(".", ",")
    except: 
        return "0,00%"

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
st.title("📊 Sales BI Pro")
st.caption("Sistema de Business Intelligence para Vendas")

# Sidebar
with st.sidebar:
    st.title("⚙️ Configurações")
    
    if st.button("🔄 Atualizar Dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    st.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')}")

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
        df_dashboard = carregar_dados_com_retry('dashboard')
    
    if not df_dashboard.empty:
        try:
            # Métricas principais
            col1, col2, col3, col4 = st.columns(4)
            
            if 'Total Venda' in df_dashboard.columns:
                total_vendas = df_dashboard['Total Venda'].sum()
                col1.metric("Vendas Totais", format_currency_br(total_vendas))
            
            if 'Margem (%)' in df_dashboard.columns:
                margem_media = df_dashboard['Margem (%)'].mean()
                col2.metric("Margem Média", format_percent_br(margem_media))
            
            if 'Quantidade' in df_dashboard.columns:
                qtd_total = df_dashboard['Quantidade'].sum()
                col3.metric("Quantidade", int(qtd_total))
            
            col4.success(f"✅ {len(df_dashboard)} linhas")
            
            # Gráfico de vendas por canal
            if 'Canal' in df_dashboard.columns and 'Total Venda' in df_dashboard.columns:
                st.subheader("Vendas por Canal")
                fig = px.bar(
                    df_dashboard, 
                    x='Canal', 
                    y='Total Venda',
                    title="Faturamento por Canal"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(df_dashboard, use_container_width=True)
            
        except Exception as e:
            st.error(f"Erro ao processar dashboard: {e}")
            st.dataframe(df_dashboard, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado encontrado no dashboard")

# ABA 2: POR CNPJ
with tabs[1]:
    st.header("🏢 Análise por CNPJ")
    
    with st.spinner("Carregando dados..."):
        df_cnpj = carregar_dados_com_retry('cnpj')
    
    if not df_cnpj.empty:
        st.success(f"✅ {len(df_cnpj)} registros")
        st.dataframe(df_cnpj, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 3: MATRIZ BCG
with tabs[2]:
    st.header("⭐ Matriz BCG")
    
    with st.spinner("Carregando BCG..."):
        df_bcg = carregar_dados_com_retry('bcg')
    
    if not df_bcg.empty:
        st.success(f"✅ {len(df_bcg)} produtos")
        
        # Filtros
        if 'Classificação' in df_bcg.columns:
            classificacoes = st.multiselect(
                "Filtrar Classificação:",
                df_bcg['Classificação'].unique(),
                default=df_bcg['Classificação'].unique()
            )
            df_bcg_filt = df_bcg[df_bcg['Classificação'].isin(classificacoes)]
        else:
            df_bcg_filt = df_bcg
        
        st.dataframe(df_bcg_filt, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 4: PREÇOS
with tabs[3]:
    st.header("💲 Preços Marketplaces")
    
    with st.spinner("Carregando preços..."):
        df_precos = carregar_dados_com_retry('precos')
    
    if not df_precos.empty:
        st.success(f"✅ {len(df_precos)} produtos")
        st.dataframe(df_precos, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 5: DETALHES
with tabs[4]:
    st.header("📝 Detalhes de Vendas")
    
    with st.spinner("Carregando vendas..."):
        df_detalhes = carregar_dados_com_retry('detalhes')
    
    if not df_detalhes.empty:
        # Métricas
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Vendas", len(df_detalhes))
        
        if 'Quantidade' in df_detalhes.columns:
            total_itens = df_detalhes['Quantidade'].sum()
            col2.metric("Itens Vendidos", int(total_itens))
        
        if 'Data' in df_detalhes.columns:
            try:
                datas = pd.to_datetime(df_detalhes['Data'], errors='coerce')
                col3.metric("Período", f"{datas.min().strftime('%d/%m')} a {datas.max().strftime('%d/%m')}")
            except:
                pass
        
        # Filtros
        col1, col2 = st.columns(2)
        
        with col1:
            if 'Canal' in df_detalhes.columns:
                canais = ['Todos'] + list(df_detalhes['Canal'].unique())
                canal = st.selectbox("Canal:", canais)
                if canal != 'Todos':
                    df_detalhes = df_detalhes[df_detalhes['Canal'] == canal]
        
        with col2:
            if 'Produto' in df_detalhes.columns:
                busca = st.text_input("Buscar produto:")
                if busca:
                    df_detalhes = df_detalhes[df_detalhes['Produto'].str.contains(busca, case=False, na=False)]
        
        st.dataframe(df_detalhes, use_container_width=True, height=600)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 6: GIRO
with tabs[5]:
    st.header("🔄 Giro de Produtos")
    
    with st.spinner("Carregando giro..."):
        df_giro = carregar_dados_com_retry('giro')
    
    if not df_giro.empty:
        st.success(f"✅ {len(df_giro)} produtos")
        st.dataframe(df_giro, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 7: OPORTUNIDADES
with tabs[6]:
    st.header("🚀 Oportunidades")
    
    with st.spinner("Carregando oportunidades..."):
        df_oport = carregar_dados_com_retry('oportunidades')
    
    if not df_oport.empty:
        st.success(f"✅ {len(df_oport)} oportunidades")
        st.dataframe(df_oport, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 8: PRODUTOS
with tabs[7]:
    st.header("📦 Produtos Cadastrados")
    
    with st.spinner("Carregando produtos..."):
        df_produtos = carregar_dados_com_retry('produtos')
    
    if not df_produtos.empty:
        col1, col2 = st.columns([3, 1])
        col1.success(f"✅ {len(df_produtos)} produtos")
        
        busca = st.text_input("🔍 Buscar produto:")
        if busca:
            mascara = df_produtos.astype(str).apply(
                lambda x: x.str.contains(busca, case=False, na=False)
            ).any(axis=1)
            df_produtos = df_produtos[mascara]
            st.info(f"🔍 {len(df_produtos)} resultados")
        
        st.dataframe(df_produtos, use_container_width=True, height=600)
    else:
        st.warning("⚠️ Nenhum dado encontrado")

# ABA 9: KITS
with tabs[8]:
    st.header("🎁 Kits Disponíveis")
    
    with st.spinner("Carregando kits..."):
        df_kits = carregar_dados_com_retry('kits')
    
    if not df_kits.empty:
        st.success(f"✅ {len(df_kits)} kits")
        st.dataframe(df_kits, use_container_width=True, height=600)
        
        # Exemplo de decomposição
        st.divider()
        st.subheader("🔬 Exemplo de Decomposição")
        kit = df_kits.iloc[0]
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Kit:** {kit.iloc[0]}")
            st.write(f"**Preço:** {kit.iloc[3]}")
        
        with col2:
            componentes = str(kit.iloc[1]).split(';')
            quantidades = str(kit.iloc[2]).split(';')
            st.write("**Componentes:**")
            for comp, qtd in zip(componentes, quantidades):
                st.write(f"- {comp.strip()} → {qtd.strip()} un")
    else:
        st.warning("⚠️ Nenhum dado encontrado")
