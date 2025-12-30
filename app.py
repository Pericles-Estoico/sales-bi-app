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
# VERSÃO V49 - CLEAN (RESTAURADA)
# ==============================================================================
# 1. Funcionalidades originais da v49
# 2. Sem integração com template_estoque
# 3. Sem arquivos lixo
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
# URL da planilha Config_BI_Final_MatrizBCG (Aba 6. Detalhes - GID 961459380)
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

def safe_int(x, default=0):
    try:
        if x is None: return default
        if isinstance(x, float) and math.isnan(x): return default
        if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null", "n/a"}: return default
        return int(float(str(x).replace(",", ".")))
    except: return default

# ==============================================================================
# FUNÇÕES DE DADOS (CARREGAMENTO E SALVAMENTO)
# ==============================================================================
def get_gspread_client():
    try:
        if "GOOGLE_SHEETS_CREDENTIALS" in st.secrets:
            creds_data = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]
            
            # Garante formato de dicionário
            if isinstance(creds_data, str):
                try:
                    creds_dict = json.loads(creds_data)
                except:
                    creds_dict = dict(creds_data)
            elif hasattr(creds_data, 'to_dict'):
                creds_dict = creds_data.to_dict()
            else:
                creds_dict = dict(creds_data)
            
            scope = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            
            # Nova forma de autenticação (google-auth)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            return gspread.authorize(creds)
        else:
            st.error("Credenciais não encontradas.")
            return None
    except Exception as e:
        st.error(f"Erro de Autenticação: {e}")
        return None

def salvar_dados_sheets(df_novos_dados):
    client = get_gspread_client()
    if not client: return False
    
    try:
        # Extrai o ID da planilha da URL
        sheet_id = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E" # ID fixo da planilha mestre
        sh = client.open_by_key(sheet_id)
        
        # Tenta acessar a aba '6. Detalhes' (onde ficam os dados brutos)
        try:
            worksheet = sh.worksheet("6. Detalhes")
        except:
            # Se não achar pelo nome, tenta a primeira aba ou cria uma nova
            worksheet = sh.sheet1
            
        # Prepara os dados para envio (converte para lista de listas)
        # Garante que as colunas estejam na ordem certa se necessário, ou apenas append
        dados_lista = df_novos_dados.values.tolist()
        
        # Adiciona as linhas no final da planilha
        worksheet.append_rows(dados_lista)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")
        return False

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
        if 'Margem (%)' in df.columns:
            df['Margem (%)'] = df['Margem (%)'].apply(clean_percent_read)
        if 'Lucro Bruto' in df.columns:
            df['Lucro Bruto'] = df['Lucro Bruto'].apply(clean_currency)
            
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados históricos da BCG: {e}")
        return pd.DataFrame()

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
st.sidebar.title("🔧 Status da Conexão")

# MODO SIMULAÇÃO (SANDBOX) - CORREÇÃO DE BUG
# Usamos st.session_state.get para inicializar, mas o controle é feito pelo key do widget
if 'sandbox_mode' not in st.session_state:
    st.session_state.sandbox_mode = False

# O widget checkbox atualiza diretamente o session_state['sandbox_mode']
st.sidebar.checkbox(
    "🧪 MODO SIMULAÇÃO (Sandbox)", 
    key="sandbox_mode",
    help="Ative para testar sem salvar dados reais."
)

if st.session_state.sandbox_mode:
    st.sidebar.warning("⚠️ MODO SIMULAÇÃO ATIVO: Nenhuma alteração será salva!")

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
        col_produto = next((k for k, v in cols_map.items() if 'produto' in v or 'descricao' in v or 'codigo' in v), None)
        col_qtd = next((k for k, v in cols_map.items() if 'quantidade' in v or 'qtd' in v), None)
        
        col_valor = next((k for k, v in cols_map.items() if 'valor' in v or 'total' in v), None)

        if col_produto and col_qtd:
            rename_dict = {col_produto: 'Produto', col_qtd: 'Quantidade'}
            if col_valor:
                rename_dict[col_valor] = 'Total Venda'
            
            df = df.rename(columns=rename_dict)
            df['Produto'] = df['Produto'].astype(str).str.strip()
            df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce').fillna(1).astype(int)
            
            if 'Total Venda' in df.columns:
                df['Total Venda'] = pd.to_numeric(df['Total Venda'], errors='coerce').fillna(0.0)
            
            df['Canal'] = CHANNELS[canal]
            
            # Botão de Processamento (Texto Dinâmico)
            btn_label = "🧪 Simular (Teste)" if st.session_state.sandbox_mode else "🔍 Pré-visualizar Importação"
            
            if st.sidebar.button(btn_label):
                # Mesclar com dados existentes se houver
                if 'processed_data' in st.session_state:
                    df_final = pd.concat([st.session_state.processed_data, df], ignore_index=True)
                else:
                    df_final = df
                
                st.session_state.processed_data = df_final
                st.session_state.novos_dados_temp = df # Guarda apenas os novos dados para salvar depois
                
                if st.session_state.sandbox_mode:
                    st.success(f"TESTE: {len(df)} vendas simuladas na memória. Nada será salvo.")
                else:
                    st.info(f"PRÉ-VISUALIZAÇÃO: {len(df)} vendas prontas para importar. Confira os dados e use o botão abaixo para SALVAR.")
                
            # Botão de Gravação Real com Trava de Segurança
            if 'novos_dados_temp' in st.session_state and not st.session_state.sandbox_mode:
                st.sidebar.divider()
                st.sidebar.markdown("### 🔒 Finalização")
                
                # Checkbox de Confirmação
                confirmacao = st.sidebar.checkbox(
                    "✅ Confirmo que analisei a simulação e os dados estão corretos.",
                    key="check_confirmacao"
                )
                
                if confirmacao:
                    st.sidebar.warning("⚠️ Atenção: Esta ação é irreversível!")
                    if st.sidebar.button("💾 SALVAR DADOS NA PLANILHA (OFICIAL)", type="primary"):
                        with st.spinner("Salvando dados no Google Sheets..."):
                            sucesso = salvar_dados_sheets(st.session_state.novos_dados_temp)
                            if sucesso:
                                st.success("✅ Dados salvos com sucesso na planilha Google Sheets!")
                                del st.session_state.novos_dados_temp # Limpa os dados temporários
                                time.sleep(2)
                                st.cache_data.clear() # Limpa o cache para recarregar tudo atualizado
                                st.rerun()
                            else:
                                st.error("❌ Falha ao salvar dados. Verifique as permissões ou a conexão.")
                else:
                    st.sidebar.info("👆 Marque a caixa acima para liberar o salvamento.")

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
    
    # Margem Média
    margem_media = 0
    if 'Margem (%)' in df_vendas.columns:
        margem_media = df_vendas['Margem (%)'].mean()
    
    with tabs[0]: # Visão Geral
        c1, c2, c3 = st.columns(3)
        c1.metric("Vendas Totais", format_currency_br(total_vendas))
        c2.metric("Margem Média", format_percent_br(margem_media))
        c3.metric("Ticket Médio", format_currency_br(ticket_medio))
        
        if 'Canal' in df_vendas.columns:
            st.subheader("Vendas por Canal")
            st.bar_chart(df_vendas.groupby('Canal')['Quantidade'].sum())

    with tabs[1]: # Por CNPJ
        if 'CNPJ' in df_vendas.columns:
            st.subheader("Análise por CNPJ")
            df_cnpj = df_vendas.groupby('CNPJ').agg({
                'Total Venda': 'sum',
                'Quantidade': 'sum',
                'Lucro Bruto': 'sum'
            }).reset_index()
            st.dataframe(df_cnpj.style.format({'Total Venda': 'R$ {:,.2f}', 'Lucro Bruto': 'R$ {:,.2f}'}), use_container_width=True)
        else:
            st.info("Coluna 'CNPJ' não encontrada nos dados.")

    with tabs[2]: # BCG Geral
        st.subheader("Matriz BCG Geral")
        # Simulação simples de BCG baseada em volume e margem (já que não temos crescimento histórico completo)
        if 'Quantidade' in df_vendas.columns and 'Margem (%)' in df_vendas.columns:
            df_bcg = df_vendas.groupby('Produto').agg({
                'Quantidade': 'sum',
                'Margem (%)': 'mean',
                'Total Venda': 'sum'
            }).reset_index()
            
            # Classificação Simplificada
            med_qtd = df_bcg['Quantidade'].median()
            med_margem = df_bcg['Margem (%)'].median()
            
            def classificar_bcg(row):
                if row['Quantidade'] >= med_qtd and row['Margem (%)'] >= med_margem: return 'Estrela ⭐'
                if row['Quantidade'] >= med_qtd and row['Margem (%)'] < med_margem: return 'Vaca Leiteira 🐄'
                if row['Quantidade'] < med_qtd and row['Margem (%)'] >= med_margem: return 'Interrogação ❓'
                return 'Abacaxi 🍍'
            
            df_bcg['Classificação'] = df_bcg.apply(classificar_bcg, axis=1)
            
            # Gráfico Nativo Simples
            st.scatter_chart(
                df_bcg,
                x='Margem (%)',
                y='Quantidade',
                color='Classificação',
                size='Total Venda'
            )
            
            st.dataframe(df_bcg, use_container_width=True)
        else:
            st.info("Dados insuficientes para BCG (precisa de Quantidade e Margem).")

    with tabs[3]: # BCG por Canal
        st.subheader("BCG por Canal")
        if 'Canal' in df_vendas.columns:
            canal_sel = st.selectbox("Selecione o Canal", df_vendas['Canal'].unique())
            df_canal = df_vendas[df_vendas['Canal'] == canal_sel]
            
            if not df_canal.empty:
                # Reutiliza lógica BCG para o canal
                df_bcg_canal = df_canal.groupby('Produto').agg({
                    'Quantidade': 'sum',
                    'Margem (%)': 'mean',
                    'Total Venda': 'sum'
                }).reset_index()
                
                med_qtd_c = df_bcg_canal['Quantidade'].median()
                med_margem_c = df_bcg_canal['Margem (%)'].median()
                
                def classificar_bcg_canal(row):
                    if row['Quantidade'] >= med_qtd_c and row['Margem (%)'] >= med_margem_c: return 'Estrela ⭐'
                    if row['Quantidade'] >= med_qtd_c and row['Margem (%)'] < med_margem_c: return 'Vaca Leiteira 🐄'
                    if row['Quantidade'] < med_qtd_c and row['Margem (%)'] >= med_margem_c: return 'Interrogação ❓'
                    return 'Abacaxi 🍍'
                
                df_bcg_canal['Classificação'] = df_bcg_canal.apply(classificar_bcg_canal, axis=1)
                
                st.scatter_chart(
                    df_bcg_canal,
                    x='Margem (%)',
                    y='Quantidade',
                    color='Classificação',
                    size='Total Venda'
                )
                st.dataframe(df_bcg_canal, use_container_width=True)
            else:
                st.warning("Sem dados para este canal.")
        else:
            st.info("Coluna 'Canal' não encontrada.")

    with tabs[4]: # Preços
        st.subheader("Análise de Preços")
        if 'Total Venda' in df_vendas.columns and 'Quantidade' in df_vendas.columns:
            df_vendas['Preço Médio'] = df_vendas['Total Venda'] / df_vendas['Quantidade']
            st.scatter_chart(df_vendas, x='Quantidade', y='Preço Médio')
        else:
            st.info("Dados de preço indisponíveis.")

    with tabs[5]: # Detalhes
        st.subheader("Base de Dados Completa")
        st.dataframe(df_vendas, use_container_width=True)

    with tabs[6]: # Giro
        st.subheader("Giro de Produtos")
        if 'Quantidade' in df_vendas.columns:
            top_giro = df_vendas.groupby('Produto')['Quantidade'].sum().sort_values(ascending=False).head(20)
            st.bar_chart(top_giro)
        else:
            st.info("Dados de quantidade indisponíveis.")

    with tabs[7]: # Oportunidades
        st.subheader("🚀 Oportunidades de Melhoria")
        st.write("Produtos com alta margem e baixo volume (Interrogação) que podem ser promovidos:")
        # Lógica de filtro para Interrogação
        if 'Classificação' in df_bcg.columns:
            oportunidades = df_bcg[df_bcg['Classificação'] == 'Interrogação ❓'].sort_values('Margem (%)', ascending=False)
            st.dataframe(oportunidades, use_container_width=True)
        else:
            st.info("Classificação BCG não disponível.")

else:
    with tabs[0]:
        st.info("Carregando dados da planilha mestre...")
