import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import unicodedata
import io
import time
import requests
import math
from io import StringIO
import xlsxwriter
import plotly.express as px

# ==============================================================================
# VERSÃO V55 - RESTAURAÇÃO COMPLETA (BASEADA NA V47)
# ==============================================================================
# 1. Restaura gráficos Plotly (requer requirements.txt atualizado)
# 2. Mapeia corretamente as abas da planilha Config_BI_Final_MatrizBCG
# 3. Garante que cada aba do app leia a aba correspondente do Excel
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DE URLS (GIDs Mapeados)
# ==============================================================================
BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

URLS = {
    'detalhes': f"{BASE_URL}&gid=961459380",      # 6. Detalhes
    'dashboard': f"{BASE_URL}&gid=1526866348",    # 1. Dashboard Geral
    'cnpj': f"{BASE_URL}&gid=1262664738",         # 2. Análise por CNPJ
    'bcg': f"{BASE_URL}&gid=182362507",           # 5. Matriz BCG
    'precos': f"{BASE_URL}&gid=1763860078",       # 4. Preços Marketplaces
    'giro': f"{BASE_URL}&gid=1226903383",         # 7. Giro de Produtos
    'oportunidades': f"{BASE_URL}&gid=1768393863" # 8. Oportunidades
}

# ==============================================================================
# CONSTANTES E MAPEAMENTOS
# ==============================================================================
CHANNELS = {
    'geral': '📊 Vendas Gerais',
    'mercado_livre': '🛒 Mercado Livre',
    'shopee_matriz': '🛍️ Shopee Matriz',
    'shopee_150': '🏪 Shopee 1:50',
    'shein': '👗 Shein'
}

ORDEM_BCG = ['Vaca Leiteira 🐄', 'Estrela ⭐', 'Interrogação ❓', 'Abacaxi 🍍']

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
def clean_currency(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace('R$', '').replace(' ', '').replace('%', '')
    try: return float(s_val)
    except: pass
    if ',' in s_val and '.' in s_val: s_val = s_val.replace('.', '').replace(',', '.')
    elif ',' in s_val: s_val = s_val.replace(',', '.')
    try: return float(s_val)
    except: return 0.0

def clean_percent_read(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace('%', '').replace(' ', '')
    if ',' in s_val: s_val = s_val.replace('.', '').replace(',', '.')
    try: return float(s_val) / 100
    except: return 0.0

def clean_float(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace(',', '.')
    try: return float(s_val)
    except: return 0.0

def format_currency_br(value):
    try: return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def format_percent_br(value):
    try: return f"{value * 100:.2f}%".replace(".", ",")
    except: return "0,00%"

def normalizar(texto):
    if pd.isna(texto): return ''
    texto = str(texto)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

# ==============================================================================
# FUNÇÃO DE CARREGAMENTO DE DADOS (CACHEADA)
# ==============================================================================
@st.cache_data(ttl=300)
def carregar_dados(tipo):
    url = URLS.get(tipo)
    if not url: return pd.DataFrame()
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        
        # Limpeza Genérica
        for col in df.columns:
            if 'Total' in col or 'Venda' in col or 'Lucro' in col or 'Preço' in col:
                if df[col].dtype == 'object':
                    df[col] = df[col].apply(clean_currency)
            if 'Margem' in col or '%' in col:
                if df[col].dtype == 'object':
                    df[col] = df[col].apply(clean_percent_read)
            if 'Quantidade' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de {tipo}: {e}")
        return pd.DataFrame()

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
st.sidebar.title("🔧 Status da Conexão")

# MODO SIMULAÇÃO (SANDBOX)
if 'sandbox_mode' not in st.session_state:
    st.session_state.sandbox_mode = False

sandbox_toggle = st.sidebar.checkbox("🧪 MODO SIMULAÇÃO (Sandbox)", value=st.session_state.sandbox_mode, help="Ative para testar sem salvar dados reais.")
if sandbox_toggle != st.session_state.sandbox_mode:
    st.session_state.sandbox_mode = sandbox_toggle
    st.rerun()

if st.session_state.sandbox_mode:
    st.sidebar.warning("⚠️ MODO SIMULAÇÃO ATIVO: Nenhuma alteração será salva!")

# Carregamento Inicial
with st.spinner("Conectando à planilha mestre..."):
    df_dashboard = carregar_dados('dashboard')
    if not df_dashboard.empty:
        st.sidebar.success("Conectado: Config_BI_Final_MatrizBCG")
    else:
        st.sidebar.error("Falha na conexão com a planilha.")

st.sidebar.divider()
st.sidebar.header("📥 Importar Novas Vendas")

if st.sidebar.button("🔄 Atualizar Dados (Limpar Cache)"):
    st.cache_data.clear()
    st.rerun()

# Inputs de Upload (Mantidos para compatibilidade)
formato = st.sidebar.radio("Formato", ["Bling", "Padrão"], index=0)
canal = st.sidebar.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
cnpj = st.sidebar.selectbox("CNPJ/Regime", ["Simples Nacional", "Lucro Presumido"])
data_venda = st.sidebar.date_input("Data", datetime.now())
ads = st.sidebar.number_input("Ads (R$)", min_value=0.0, step=10.0)
uploaded_file = st.sidebar.file_uploader("Arquivo Excel", type=["xlsx", "xls"])

# ==============================================================================
# DASHBOARD E VISUALIZAÇÃO
# ==============================================================================
st.title("📊 Sales BI Pro")

tabs = st.tabs([
    "📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", 
    "💲 Preços", "📝 Detalhes", "🔄 Giro de Produtos", "🚀 Oportunidades"
])

# 1. VISÃO GERAL
with tabs[0]:
    if not df_dashboard.empty:
        total_vendas = df_dashboard['Total Venda'].sum()
        margem_media = df_dashboard['Margem (%)'].mean()
        qtd_total = df_dashboard['Quantidade'].sum()
        ticket_medio = total_vendas / qtd_total if qtd_total > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Vendas Totais", format_currency_br(total_vendas))
        c2.metric("Margem Média", format_percent_br(margem_media))
        c3.metric("Ticket Médio", format_currency_br(ticket_medio))
        
        st.subheader("Vendas por Canal")
        fig = px.bar(df_dashboard, x='Canal', y='Total Venda', color='Canal', text_auto='.2s', title="Faturamento por Canal")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Carregando dados do Dashboard...")

# 2. POR CNPJ
with tabs[1]:
    df_cnpj = carregar_dados('cnpj')
    if not df_cnpj.empty:
        st.subheader("Análise por CNPJ")
        st.dataframe(df_cnpj.style.format({'Total Venda': 'R$ {:,.2f}', 'Lucro Bruto': 'R$ {:,.2f}'}), use_container_width=True)
        
        fig = px.pie(df_cnpj, values='Total Venda', names='CNPJ', title='Distribuição de Vendas por CNPJ')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Carregando dados de CNPJ...")

# 3. BCG GERAL
with tabs[2]:
    df_bcg = carregar_dados('bcg')
    if not df_bcg.empty:
        st.subheader("Matriz BCG Geral")
        
        # Filtros
        classificacoes = st.multiselect("Filtrar Classificação", df_bcg['Classificação'].unique(), default=df_bcg['Classificação'].unique())
        df_bcg_filt = df_bcg[df_bcg['Classificação'].isin(classificacoes)]
        
        fig = px.scatter(
            df_bcg_filt, 
            x='Margem (%)', 
            y='Quantidade', 
            color='Classificação', 
            size='Total Venda', 
            hover_name='Produto',
            title="Matriz BCG (Volume x Margem)",
            color_discrete_map={
                'Estrela ⭐': '#FFD700',
                'Vaca Leiteira 🐄': '#C0C0C0',
                'Interrogação ❓': '#1E90FF',
                'Abacaxi 🍍': '#FF4500'
            }
        )
        # Linhas de Corte (Médias)
        med_qtd = df_bcg['Quantidade'].median()
        med_margem = df_bcg['Margem (%)'].median()
        fig.add_hline(y=med_qtd, line_dash="dash", line_color="gray", annotation_text="Média Qtd")
        fig.add_vline(x=med_margem, line_dash="dash", line_color="gray", annotation_text="Média Margem")
        
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_bcg_filt, use_container_width=True)
    else:
        st.info("Carregando dados da BCG...")

# 4. BCG POR CANAL
with tabs[3]:
    st.subheader("BCG por Canal")
    # Como a aba BCG já tem todos os produtos, podemos filtrar se houver coluna Canal, 
    # mas a planilha BCG consolidada geralmente não tem canal linha a linha.
    # Vamos usar a aba Detalhes para reconstruir se necessário, ou avisar.
    st.info("Para análise detalhada por canal, utilize a aba 'Detalhes' e filtre pelo canal desejado.")

# 5. PREÇOS
with tabs[4]:
    df_precos = carregar_dados('precos')
    if not df_precos.empty:
        st.subheader("Monitoramento de Preços")
        st.dataframe(df_precos, use_container_width=True)
    else:
        st.info("Carregando dados de Preços...")

# 6. DETALHES
with tabs[5]:
    df_detalhes = carregar_dados('detalhes')
    if not df_detalhes.empty:
        st.subheader("Base de Dados Completa")
        st.dataframe(df_detalhes, use_container_width=True)
    else:
        st.info("Carregando detalhes...")

# 7. GIRO
with tabs[6]:
    df_giro = carregar_dados('giro')
    if not df_giro.empty:
        st.subheader("Giro de Estoque")
        st.dataframe(df_giro, use_container_width=True)
    else:
        st.info("Carregando dados de Giro...")

# 8. OPORTUNIDADES
with tabs[7]:
    df_oportunidades = carregar_dados('oportunidades')
    if not df_oportunidades.empty:
        st.subheader("🚀 Oportunidades Identificadas")
        st.dataframe(df_oportunidades, use_container_width=True)
    else:
        st.info("Carregando oportunidades...")
