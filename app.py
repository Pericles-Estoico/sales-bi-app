import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import json
import unicodedata
import io
import time
import requests
import math
from io import StringIO
import xlsxwriter

# ==============================================================================
# VERSÃO V54 - CORREÇÃO NOME DA ABA "Detalhes_Canais"
# ==============================================================================
# 1. Upload salva em "Detalhes_Canais" (com underscore!)
# 2. Dashboard lê abas processadas corretamente
# 3. Sistema de metas com indicadores visuais
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES - URLS DAS ABAS
# ==============================================================================
SHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid="

ABAS_URLS = {
    'produtos': f"{BASE_URL}1037607798",
    'kits': f"{BASE_URL}1569485799",
    'custo_por_pedido': f"{BASE_URL}1720329296",
    'canais': f"{BASE_URL}1639432432",
    'impostos': f"{BASE_URL}260097325",
    'frete': f"{BASE_URL}1928835495",
    'metas': f"{BASE_URL}1477190272",
    'dashboard_geral': f"{BASE_URL}749174572",
    'detalhes_canais': f"{BASE_URL}961459380",
    'resultado_cnpj': f"{BASE_URL}1830625125",
    'executiva_simples': f"{BASE_URL}1734348857",
    'preco_simples_mktp': f"{BASE_URL}2119792312",
    'bcg_canal_mkt': f"{BASE_URL}914780374",
    'vendas_sku_geral': f"{BASE_URL}1138113192",
    'oportunidades_canais_mkt': f"{BASE_URL}706549654"
}

# ==============================================================================
# CONSTANTES
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

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
def clean_currency(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace('R$', '').replace(' ', '')
    s_val = s_val.replace('.', '').replace(',', '.')
    try: return float(s_val)
    except: return 0.0

def clean_percent(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace('%', '').replace(',', '.')
    try: return float(s_val) / 100
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
# AUTENTICAÇÃO
# ==============================================================================
def get_gspread_client():
    try:
        if "GOOGLE_SHEETS_CREDENTIALS" not in st.secrets:
            st.error("❌ Credenciais não configuradas.")
            return None

        creds_input = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]
        
        creds_dict = None
        if hasattr(creds_input, "_data"):
            creds_dict = dict(creds_input._data)
        elif hasattr(creds_input, "to_dict"):
            creds_dict = creds_input.to_dict()
        elif isinstance(creds_input, dict):
            creds_dict = dict(creds_input)
        elif isinstance(creds_input, str):
            creds_dict = json.loads(creds_input.strip())

        if 'private_key' in creds_dict:
            creds_dict['private_key'] = creds_dict['private_key'].replace('\\\\n', '\n').replace('\\n', '\n')

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)

    except Exception as e:
        st.error(f"❌ Erro na autenticação: {str(e)}")
        return None

# ==============================================================================
# SALVAMENTO (CORRIGIDO - Nome da aba com underscore)
# ==============================================================================
def salvar_dados_sheets(df_novos_dados):
    client = get_gspread_client()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # CORREÇÃO: Nome correto da aba com underscore
        worksheet = sh.worksheet("Detalhes_Canais")
        
        colunas_planilha = worksheet.row_values(1)
        if not colunas_planilha:
            worksheet.append_row(COLUNAS_ESPERADAS)
            colunas_planilha = COLUNAS_ESPERADAS
        
        df_preparado = pd.DataFrame()
        for col in colunas_planilha:
            if col in df_novos_dados.columns:
                df_preparado[col] = df_novos_dados[col]
            else:
                df_preparado[col] = ""
        
        df_preparado = df_preparado.fillna("").astype(str)
        dados_lista = df_preparado.values.tolist()
        
        if dados_lista:
            worksheet.append_rows(dados_lista, value_input_option='USER_ENTERED')
            st.success(f"✅ {len(dados_lista)} registros salvos em 'Detalhes_Canais'!")
            return True
        return False
            
    except gspread.exceptions.WorksheetNotFound:
        st.error("❌ Aba 'Detalhes_Canais' não encontrada!")
        st.info("💡 Verifique se o nome da aba está correto na planilha.")
        return False
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {str(e)}")
        return False

# ==============================================================================
# PREPARAÇÃO DE DADOS (Upload)
# ==============================================================================
def preparar_dados_para_salvar(df_raw, canal, cnpj, data_venda):
    try:
        df_prep = df_raw.copy()
        
        if df_prep.empty:
            st.error("❌ DataFrame vazio!")
            return pd.DataFrame()
        
        df_prep['Data'] = data_venda.strftime("%Y-%m-%d")
        df_prep['Canal'] = CHANNELS.get(canal, canal)
        df_prep['CNPJ'] = cnpj
        
        if 'Produto' not in df_prep.columns or 'Quantidade' not in df_prep.columns:
            st.error("❌ Colunas 'Produto' e 'Quantidade' obrigatórias!")
            return pd.DataFrame()
        
        df_prep['Quantidade'] = pd.to_numeric(df_prep['Quantidade'], errors='coerce').fillna(0).astype(int)
        
        if 'Total Venda' not in df_prep.columns:
            df_prep['Total Venda'] = df_prep['Quantidade'] * 50.0
        else:
            df_prep['Total Venda'] = pd.to_numeric(df_prep['Total Venda'], errors='coerce').fillna(0.0)
        
        colunas_financeiras = {
            'Tipo': 'Venda',
            'Custo Produto': 0.0,
            'Impostos': 0.0,
            'Comissão': 0.0,
            'Taxas Fixas': 0.0,
            'Embalagem': 0.0,
            'Investimento Ads': 0.0,
            'Custo Total': 0.0,
            'Lucro Bruto': 0.0,
            'Margem (%)': 0.0
        }
        
        for col, valor in colunas_financeiras.items():
            if col not in df_prep.columns:
                df_prep[col] = valor
        
        df_final = pd.DataFrame()
        for col in COLUNAS_ESPERADAS:
            df_final[col] = df_prep[col] if col in df_prep.columns else ""
        
        st.success(f"✅ {len(df_final)} linhas preparadas!")
        return df_final
        
    except Exception as e:
        st.error(f"❌ Erro: {str(e)}")
        return pd.DataFrame()

# ==============================================================================
# CARREGAMENTO DE DADOS (Dashboard)
# ==============================================================================
@st.cache_data(ttl=300)
def carregar_aba(nome_aba):
    try:
        url = ABAS_URLS.get(nome_aba)
        if not url:
            return pd.DataFrame()
        
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        
        for col in df.columns:
            if any(x in col.lower() for x in ['venda', 'lucro', 'custo', 'valor', 'total', 'r$']):
                df[col] = df[col].apply(clean_currency)
            elif 'margem' in col.lower() or '%' in col.lower():
                df[col] = df[col].apply(clean_percent)
            elif 'quantidade' in col.lower() or 'qtd' in col.lower():
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar {nome_aba}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_metas():
    return {
        'margem_minima': 0.20,
        'margem_ideal': 0.30,
        'ticket_minimo': 45.0,
        'ticket_ideal': 60.0
    }

def get_status_meta(valor, minimo, ideal, tipo='margem'):
    if tipo == 'margem':
        if valor >= ideal: return "🟢 Ideal"
        elif valor >= minimo: return "🟡 Atenção"
        else: return "🔴 Crítico"
    else:
        if valor >= ideal: return "🟢 Ideal"
        elif valor >= minimo: return "🟡 Atenção"
        else: return "🔴 Crítico"

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
st.sidebar.title("🔧 Status da Conexão")

if st.sidebar.button("🔍 Testar Conexão"):
    client = get_gspread_client()
    if client:
        try:
            sh = client.open_by_key(SHEET_ID)
            st.sidebar.success(f"✅ Conectado: {sh.title}")
            ws = sh.worksheet("Detalhes_Canais")
            st.sidebar.info(f"📊 Linhas: {ws.row_count}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro: {e}")

st.sidebar.divider()

if 'sandbox_mode' not in st.session_state:
    st.session_state.sandbox_mode = False

st.sidebar.checkbox("🧪 MODO SIMULAÇÃO", key="sandbox_mode")

if st.session_state.sandbox_mode:
    st.sidebar.warning("⚠️ SIMULAÇÃO ATIVA")

st.sidebar.divider()
st.sidebar.header("📥 Importar Vendas")

if st.sidebar.button("🔄 Atualizar Cache"):
    st.cache_data.clear()
    st.rerun()

canal = st.sidebar.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
cnpj = st.sidebar.selectbox("CNPJ/Regime", ["Simples Nacional", "Lucro Presumido"])
data_venda = st.sidebar.date_input("Data", datetime.now())

uploaded_file = st.sidebar.file_uploader("Arquivo Excel", type=["xlsx", "xls"])

# ==============================================================================
# PROCESSAMENTO DE UPLOAD
# ==============================================================================
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        st.info(f"📄 {len(df)} linhas | Colunas: {', '.join(df.columns)}")
        
        cols_map = {c: normalizar(c) for c in df.columns}
        col_produto = next((k for k, v in cols_map.items() if any(x in v for x in ['produto', 'descricao', 'codigo', 'item'])), None)
        col_qtd = next((k for k, v in cols_map.items() if any(x in v for x in ['quantidade', 'qtd', 'qtde'])), None)
        col_valor = next((k for k, v in cols_map.items() if any(x in v for x in ['valor', 'total', 'preco'])), None)

        if col_produto and col_qtd:
            rename_dict = {col_produto: 'Produto', col_qtd: 'Quantidade'}
            if col_valor:
                rename_dict[col_valor] = 'Total Venda'
            
            df = df.rename(columns=rename_dict)
            df['Produto'] = df['Produto'].astype(str).str.strip()
            df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce').fillna(1).astype(int)
            
            if 'Total Venda' in df.columns:
                df['Total Venda'] = pd.to_numeric(df['Total Venda'], errors='coerce').fillna(0.0)
            
            btn_label = "🧪 Simular" if st.session_state.sandbox_mode else "🔍 Pré-visualizar"
            
            if st.sidebar.button(btn_label):
                df_preparado = preparar_dados_para_salvar(df, canal, cnpj, data_venda)
                
                if not df_preparado.empty:
                    st.session_state.novos_dados_temp = df_preparado
                    st.markdown("### 📊 Dados Preparados")
                    st.dataframe(df_preparado, use_container_width=True)
                
            if 'novos_dados_temp' in st.session_state and not st.session_state.sandbox_mode:
                st.sidebar.divider()
                st.sidebar.markdown("### 🔒 Finalização")
                
                confirmacao = st.sidebar.checkbox("✅ Dados corretos", key="check_confirmacao")
                
                if confirmacao:
                    st.sidebar.warning("⚠️ Ação irreversível!")
                    if st.sidebar.button("💾 SALVAR", type="primary"):
                        sucesso = salvar_dados_sheets(st.session_state.novos_dados_temp)
                        if sucesso:
                            st.success("✅ Salvo! Aguarde 1-2 min para fórmulas processarem.")
                            del st.session_state.novos_dados_temp
                            time.sleep(2)
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.sidebar.info("👆 Marque para habilitar")

        else:
            st.error("❌ Colunas 'Produto' e 'Quantidade' não encontradas!")
            
    except Exception as e:
        st.error(f"❌ Erro: {str(e)}")

# ==============================================================================
# DASHBOARD
# ==============================================================================
st.title("📊 Sales BI Pro")

tabs = st.tabs([
    "📈 Dashboard Geral", "🏢 Resultado CNPJ", "⭐ BCG por Canal", 
    "💲 Preços MKTP", "🔄 Giro SKU", "🚀 Oportunidades"
])

metas = carregar_metas()

with tabs[0]:
    df_dash = carregar_aba('dashboard_geral')
    
    if not df_dash.empty:
        st.subheader("📊 Resumo por Canal")
        
        total_vendas = df_dash['Total Venda'].sum() if 'Total Venda' in df_dash.columns else 0
        total_lucro = df_dash['Lucro Bruto'].sum() if 'Lucro Bruto' in df_dash.columns else 0
        total_qtd = df_dash['Quantidade'].sum() if 'Quantidade' in df_dash.columns else 0
        
        margem_geral = (total_lucro / total_vendas) if total_vendas > 0 else 0
        ticket_medio = (total_vendas / total_qtd) if total_qtd > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Total Vendas", format_currency_br(total_vendas))
        c2.metric("💎 Lucro Bruto", format_currency_br(total_lucro))
        c3.metric("📊 Margem Geral", format_percent_br(margem_geral), 
                  delta=get_status_meta(margem_geral, metas['margem_minima'], metas['margem_ideal']))
        c4.metric("🎫 Ticket Médio", format_currency_br(ticket_medio),
                  delta=get_status_meta(ticket_medio, metas['ticket_minimo'], metas['ticket_ideal'], 'ticket'))
        
        st.dataframe(df_dash, use_container_width=True)
        
        if 'Canal' in df_dash.columns and 'Total Venda' in df_dash.columns:
            st.subheader("📈 Vendas por Canal")
            vendas_canal = df_dash.set_index('Canal')['Total Venda'].sort_values(ascending=False)
            st.bar_chart(vendas_canal)
    else:
        st.info("📊 Carregando dados...")

with tabs[1]:
    df_cnpj = carregar_aba('resultado_cnpj')
    if not df_cnpj.empty:
        st.subheader("🏢 Análise por CNPJ")
        st.dataframe(df_cnpj, use_container_width=True)
    else:
        st.info("Sem dados")

with tabs[2]:
    df_bcg = carregar_aba('bcg_canal_mkt')
    if not df_bcg.empty:
        st.subheader("⭐ Matriz BCG por Canal")
        st.dataframe(df_bcg, use_container_width=True)
    else:
        st.info("Sem dados")

with tabs[3]:
    df_precos = carregar_aba('preco_simples_mktp')
    if not df_precos.empty:
        st.subheader("💲 Análise de Preços por Marketplace")
        st.dataframe(df_precos, use_container_width=True)
    else:
        st.info("Sem dados")

with tabs[4]:
    df_giro = carregar_aba('vendas_sku_geral')
    if not df_giro.empty:
        st.subheader("🔄 Giro de Produtos (Geral)")
        st.dataframe(df_giro, use_container_width=True)
        
        if 'Quantidade' in df_giro.columns:
            top20 = df_giro.nlargest(20, 'Quantidade')
            st.bar_chart(top20.set_index('Produto')['Quantidade'] if 'Produto' in top20.columns else top20['Quantidade'])
    else:
        st.info("Sem dados")

with tabs[5]:
    df_oport = carregar_aba('oportunidades_canais_mkt')
    if not df_oport.empty:
        st.subheader("🚀 Oportunidades por Canal")
        st.dataframe(df_oport, use_container_width=True)
    else:
        st.info("Sem dados")
