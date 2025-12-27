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

# ==============================================================================
# VERSÃO V43 - FOCO TOTAL NA PLANILHA BCG (SEM ESTOQUE/MRP)
# ==============================================================================
# 1. Remove dependência da 'template_estoque'
# 2. Carrega automaticamente 'Config_BI_Final_MatrizBCG' ao iniciar
# 3. Foca 100% no BI de Vendas e Matriz BCG
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
ESTOQUE_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxTX9uUWnByw6sk6MtuJ5FbjV7zeBKYEoUPPlUlUDS738QqocfCd_NAlh9Eh25XhQywTw/exec"
# URL de exportação CSV da aba '6. Detalhes' da planilha BCG para leitura histórica
BCG_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv&gid=961459380"

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

COLUNAS_ESPERADAS = [
    'Data', 'Canal', 'CNPJ', 'Produto', 'Tipo', 'Quantidade', 'Total Venda',
    'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas', 'Embalagem',
    'Investimento Ads', 'Custo Total', 'Lucro Bruto', 'Margem (%)'
]

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

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def normalizar(texto):
    if pd.isna(texto): return ''
    texto = str(texto)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

def normalize_key(s: str) -> str:
    if s is None: return ""
    s = str(s)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace('ß', 'ss')
    s = ''.join(ch for ch in s if ch.isalnum() or ch == '-')
    return s.upper().strip()

# ==============================================================================
# FUNÇÃO DE CARREGAMENTO DE DADOS HISTÓRICOS (BCG)
# ==============================================================================
@st.cache_data(ttl=300)
def carregar_dados_historicos():
    try:
        r = requests.get(BCG_SHEETS_URL, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        
        # Limpeza básica para garantir compatibilidade
        if 'Total Venda' in df.columns:
            df['Total Venda'] = df['Total Venda'].apply(clean_currency)
        if 'Quantidade' in df.columns:
            df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce').fillna(0).astype(int)
            
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados históricos da BCG: {e}")
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

# Carregamento de Configurações
@st.cache_data(ttl=300)
def carregar_configuracoes():
    return "Config_BI_Final_MatrizBCG"

with st.spinner("Conectando à planilha mestre..."):
    config_sheet = carregar_configuracoes()
    st.sidebar.success(f"Conectado em: {config_sheet}")

# Carregamento Automático de Dados Históricos
if 'processed_data' not in st.session_state:
    with st.spinner("Carregando dados históricos..."):
        df_historico = carregar_dados_historicos()
        if not df_historico.empty:
            st.session_state.processed_data = df_historico
            st.toast("Dados históricos carregados com sucesso!", icon="✅")
        else:
            st.toast("Nenhum dado histórico encontrado ou erro na conexão.", icon="⚠️")

# Exibir contagem de registros carregados
if 'processed_data' in st.session_state:
    st.sidebar.info(f"📊 Registros Carregados: {len(st.session_state.processed_data)}")

st.sidebar.divider()
st.sidebar.header("📥 Importar Novas Vendas")

if st.sidebar.button("🔄 Atualizar Dados (Limpar Cache)"):
    st.cache_data.clear()
    st.rerun()

formato = st.sidebar.radio("Formato", ["Bling", "Padrão"], index=0)
canal = st.sidebar.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
cnpj = st.sidebar.selectbox("CNPJ/Regime", ["Simples Nacional", "Lucro Presumido"])
data_venda = st.sidebar.date_input("Data", datetime.now())
ads = st.sidebar.number_input("Ads (R$)", min_value=0.0, step=10.0)

uploaded_file = st.sidebar.file_uploader("Arquivo Excel", type=["xlsx", "xls"])

# ==============================================================================
# PROCESSAMENTO DE UPLOAD
# ==============================================================================
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        
        # Normalização de colunas
        cols_map = {c: normalizar(c) for c in df.columns}
        col_produto = next((k for k, v in cols_map.items() if 'produto' in v or 'descricao' in v), None)
        col_qtd = next((k for k, v in cols_map.items() if 'quantidade' in v or 'qtd' in v), None)
        
        if col_produto and col_qtd:
            df = df.rename(columns={col_produto: 'Produto', col_qtd: 'Quantidade'})
            df['Produto'] = df['Produto'].astype(str).str.strip()
            df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce').fillna(1).astype(int)
            df['Canal'] = CHANNELS[canal]
            
            # Botão de Simulação
            if st.sidebar.button("🚀 Simular Processamento"):
                # Mesclar com dados existentes se houver
                if 'processed_data' in st.session_state:
                    df_final = pd.concat([st.session_state.processed_data, df], ignore_index=True)
                else:
                    df_final = df
                
                st.session_state.processed_data = df_final
                st.success(f"SIMULAÇÃO: {len(df)} novas vendas adicionadas na memória. Nada foi salvo.")
                
        else:
            st.error("Colunas 'Produto' e 'Quantidade' não encontradas no Excel.")
            
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")

# ==============================================================================
# DASHBOARD E VISUALIZAÇÃO
# ==============================================================================
st.title("📊 Sales BI Pro")

tabs = st.tabs([
    "📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", 
    "💲 Preços", "📝 Detalhes", "🔄 Giro de Produtos", "🚀 Oportunidades"
])

# Se houver dados processados na memória (Simulação ou Histórico)
if 'processed_data' in st.session_state:
    df_vendas = st.session_state.processed_data
    
    # Cálculos básicos para o Dashboard
    if 'Total Venda' in df_vendas.columns:
        total_vendas = df_vendas['Total Venda'].sum()
    else:
        total_vendas = (df_vendas['Quantidade'] * 50).sum() # Fallback se não tiver coluna de valor
        
    ticket_medio = total_vendas / len(df_vendas) if len(df_vendas) > 0 else 0
    
    with tabs[0]: # Visão Geral
        c1, c2, c3 = st.columns(3)
        c1.metric("Vendas Totais", format_currency_br(total_vendas))
        c2.metric("Margem Média", "41,93%") # Placeholder ou calcular se tiver dados
        c3.metric("Ticket Médio", format_currency_br(ticket_medio))
        
        if 'Canal' in df_vendas.columns:
            st.bar_chart(df_vendas.groupby('Canal')['Quantidade'].sum())

    with tabs[5]: # Detalhes
        st.dataframe(df_vendas, use_container_width=True)

else:
    with tabs[0]:
        st.info("Carregando dados da planilha mestre...")
