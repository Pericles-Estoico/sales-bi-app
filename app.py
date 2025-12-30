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
# VERSÃO V50 - CORREÇÃO CRÍTICA COMPLETA
# ==============================================================================
# 1. Autenticação blindada contra erros de serialização
# 2. Salvamento seguro com validação de colunas
# 3. Preparação automática de dados antes de salvar
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
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
# CORREÇÃO 1: AUTENTICAÇÃO BLINDADA
# ==============================================================================
def get_gspread_client():
    """
    Versão corrigida que GARANTE compatibilidade com qualquer formato de credenciais.
    """
    try:
        if "GOOGLE_SHEETS_CREDENTIALS" not in st.secrets:
            st.error("❌ Credenciais não configuradas. Vá em Settings > Secrets e adicione GOOGLE_SHEETS_CREDENTIALS")
            return None

        creds_input = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]
        
        # CONVERSÃO UNIVERSAL PARA DICIONÁRIO PYTHON
        creds_dict = None
        
        # Caso 1: AttrDict do Streamlit (mais comum)
        if hasattr(creds_input, "_data"):
            creds_dict = dict(creds_input._data)
        elif hasattr(creds_input, "to_dict"):
            creds_dict = creds_input.to_dict()
        # Caso 2: Dicionário Python
        elif isinstance(creds_input, dict):
            creds_dict = dict(creds_input)  # Cria cópia limpa
        # Caso 3: String JSON
        elif isinstance(creds_input, str):
            creds_dict = json.loads(creds_input.strip())
        else:
            st.error(f"❌ Formato de credenciais inválido: {type(creds_input)}")
            return None

        # NORMALIZAÇÃO DO PRIVATE_KEY (crítico!)
        if 'private_key' in creds_dict:
            pk = creds_dict['private_key']
            # Remove escapes duplicados e garante quebras de linha corretas
            pk = pk.replace('\\\\n', '\n').replace('\\n', '\n')
            creds_dict['private_key'] = pk

        # VALIDAÇÃO DE CAMPOS OBRIGATÓRIOS
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing = [f for f in required_fields if f not in creds_dict]
        if missing:
            st.error(f"❌ Campos faltando nas credenciais: {missing}")
            return None

        # AUTENTICAÇÃO
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # TESTE DE CONEXÃO
        try:
            client.openall()  # Testa se consegue listar planilhas
            return client
        except Exception as e:
            st.error(f"❌ Autenticação OK, mas sem permissão: {str(e)}")
            return None

    except json.JSONDecodeError as e:
        st.error(f"❌ JSON inválido nas credenciais: {str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ Erro na autenticação: {str(e)}")
        st.info("💡 Verifique se o service account tem acesso à planilha!")
        return None

# ==============================================================================
# CORREÇÃO 2: SALVAMENTO SEGURO
# ==============================================================================
def salvar_dados_sheets(df_novos_dados):
    """
    Salva dados garantindo compatibilidade de colunas e formato.
    """
    client = get_gspread_client()
    if not client:
        st.error("❌ Falha na autenticação. Verifique as credenciais.")
        return False
    
    try:
        sheet_id = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
        sh = client.open_by_key(sheet_id)
        
        # Tenta acessar a aba '6. Detalhes'
        try:
            worksheet = sh.worksheet("6. Detalhes")
        except gspread.exceptions.WorksheetNotFound:
            st.error("❌ Aba '6. Detalhes' não encontrada na planilha!")
            return False
        
        # GARANTE QUE AS COLUNAS ESTEJAM NA ORDEM CERTA
        colunas_planilha = worksheet.row_values(1)  # Lê o header da planilha
        
        # Se a planilha estiver vazia, adiciona o header
        if not colunas_planilha:
            worksheet.append_row(COLUNAS_ESPERADAS)
            colunas_planilha = COLUNAS_ESPERADAS
        
        # AJUSTA O DATAFRAME PARA COINCIDIR COM AS COLUNAS DA PLANILHA
        df_preparado = pd.DataFrame()
        for col in colunas_planilha:
            if col in df_novos_dados.columns:
                df_preparado[col] = df_novos_dados[col]
            else:
                df_preparado[col] = ""  # Preenche colunas faltantes com vazio
        
        # CONVERTE PARA FORMATO COMPATÍVEL (strings e números)
        df_preparado = df_preparado.fillna("")
        df_preparado = df_preparado.astype(str)
        
        # Converte para lista de listas
        dados_lista = df_preparado.values.tolist()
        
        # SALVA EM LOTE (mais eficiente)
        if dados_lista:
            worksheet.append_rows(dados_lista, value_input_option='USER_ENTERED')
            st.success(f"✅ {len(dados_lista)} registros salvos com sucesso!")
            return True
        else:
            st.warning("⚠️ Nenhum dado para salvar.")
            return False
            
    except gspread.exceptions.APIError as e:
        st.error(f"❌ Erro da API do Google Sheets: {str(e)}")
        st.info("💡 Verifique se a conta de serviço tem permissão de EDITOR na planilha!")
        return False
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {str(e)}")
        return False

# ==============================================================================
# CORREÇÃO 3: PREPARAÇÃO DE DADOS
# ==============================================================================
def preparar_dados_para_salvar(df_raw, canal, cnpj, data_venda):
    """
    Garante que o DataFrame tenha TODAS as colunas esperadas antes de salvar.
    """
    df_prep = df_raw.copy()
    
    # Adiciona colunas obrigatórias se não existirem
    df_prep['Data'] = data_venda.strftime("%Y-%m-%d")
    df_prep['Canal'] = CHANNELS[canal]
    df_prep['CNPJ'] = cnpj
    
    # Preenche colunas financeiras faltantes com 0
    colunas_financeiras = [
        'Tipo', 'Custo Produto', 'Impostos', 'Comissão', 
        'Taxas Fixas', 'Embalagem', 'Investimento Ads', 
        'Custo Total', 'Lucro Bruto', 'Margem (%)'
    ]
    
    for col in colunas_financeiras:
        if col not in df_prep.columns:
            if col == 'Tipo':
                df_prep[col] = 'Venda'
            elif col == 'Margem (%)':
                df_prep[col] = '0%'
            else:
                df_prep[col] = 0.0
    
    # Garante ordem das colunas
    df_final = pd.DataFrame()
    for col in COLUNAS_ESPERADAS:
        if col in df_prep.columns:
            df_final[col] = df_prep[col]
        else:
            df_final[col] = ""
    
    return df_final

# ==============================================================================
# CARREGAMENTO DE DADOS
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

# TESTE DE DIAGNÓSTICO
if st.sidebar.button("🔍 Testar Conexão"):
    client = get_gspread_client()
    if client:
        try:
            sh = client.open_by_key("1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E")
            st.sidebar.success(f"✅ Conectado! Planilha: {sh.title}")
            ws = sh.worksheet("6. Detalhes")
            st.sidebar.info(f"📊 Linhas na aba: {ws.row_count}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro: {e}")

st.sidebar.divider()

# MODO SIMULAÇÃO
if 'sandbox_mode' not in st.session_state:
    st.session_state.sandbox_mode = False

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

uploaded_file = st.sidebar.file_uploader("Arquivo Excel", type=["xlsx", "xls"])

# ==============================================================================
# PROCESSAMENTO DE UPLOAD (CORRIGIDO)
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
            
            # Botão de Processamento (Texto Dinâmico)
            btn_label = "🧪 Simular (Teste)" if st.session_state.sandbox_mode else "🔍 Pré-visualizar Importação"
            
            if st.sidebar.button(btn_label):
                # APLICA A PREPARAÇÃO DE DADOS (CORREÇÃO CRÍTICA)
                df_preparado = preparar_dados_para_salvar(df, canal, cnpj, data_venda)
                
                # Mesclar com dados existentes se houver
                if 'processed_data' in st.session_state:
                    df_final = pd.concat([st.session_state.processed_data, df_preparado], ignore_index=True)
                else:
                    df_final = df_preparado
                
                st.session_state.processed_data = df_final
                st.session_state.novos_dados_temp = df_preparado  # Salva dados PREPARADOS
                
                if st.session_state.sandbox_mode:
                    st.success(f"TESTE: {len(df_preparado)} vendas simuladas na memória. Nada será salvo.")
                    st.markdown("### 🧪 Dados Simulados")
                    st.dataframe(df_preparado, use_container_width=True)
                else:
                    st.info(f"PRÉ-VISUALIZAÇÃO: {len(df_preparado)} vendas prontas para importar. Confira os dados e use o botão abaixo para SALVAR.")
                    st.markdown("### 📋 Dados Prontos para Importação")
                    st.dataframe(df_preparado, use_container_width=True)
                
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
                                del st.session_state.novos_dados_temp
                                time.sleep(2)
                                st.cache_data.clear()
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

if 'processed_data' in st.session_state:
    df_vendas = st.session_state.processed_data
    
    # Cálculos básicos para o Dashboard
    if 'Total Venda' in df_vendas.columns:
        total_vendas = df_vendas['Total Venda'].sum()
    else:
        total_vendas = (df_vendas['Quantidade'] * 50).sum()
        
    ticket_medio = total_vendas / len(df_vendas) if len(df_vendas) > 0 else 0
    
    # Margem Média
    margem_media = 0
    if 'Margem (%)' in df_vendas.columns:
        margem_media = df_vendas['Margem (%)'].mean()
    
    with tabs[0]:  # Visão Geral
        c1, c2, c3 = st.columns(3)
        c1.metric("Vendas Totais", format_currency_br(total_vendas))
        c2.metric("Margem Média", format_percent_br(margem_media))
        c3.metric("Ticket Médio", format_currency_br(ticket_medio))
        
        if 'Canal' in df_vendas.columns:
            st.subheader("Vendas por Canal")
            st.bar_chart(df_vendas.groupby('Canal')['Quantidade'].sum())

    with tabs[1]:  # Por CNPJ
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

    with tabs[2]:  # BCG Geral
        st.subheader("Matriz BCG Geral")
        if 'Quantidade' in df_vendas.columns and 'Margem (%)' in df_vendas.columns:
            df_bcg = df_vendas.groupby('Produto').agg({
                'Quantidade': 'sum',
                'Margem (%)': 'mean',
                'Total Venda': 'sum'
            }).reset_index()
            
            med_qtd = df_bcg['Quantidade'].median()
            med_margem = df_bcg['Margem (%)'].median()
            
            def classificar_bcg(row):
                if row['Quantidade'] >= med_qtd and row['Margem (%)'] >= med_margem: return 'Estrela ⭐'
                if row['Quantidade'] >= med_qtd and row['Margem (%)'] < med_margem: return 'Vaca Leiteira 🐄'
                if row['Quantidade'] < med_qtd and row['Margem (%)'] >= med_margem: return 'Interrogação ❓'
                return 'Abacaxi 🍍'
            
            df_bcg['Classificação'] = df_bcg.apply(classificar_bcg, axis=1)
            
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

    with tabs[3]:  # BCG por Canal
        st.subheader("BCG por Canal")
        if 'Canal' in df_vendas.columns:
            canal_sel = st.selectbox("Selecione o Canal", df_vendas['Canal'].unique())
            df_canal = df_vendas[df_vendas['Canal'] == canal_sel]
            
            if not df_canal.empty and 'Quantidade' in df_canal.columns and 'Margem (%)' in df_canal.columns:
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
                st.warning("Sem dados suficientes para este canal.")
        else:
            st.info("Coluna 'Canal' não encontrada.")

    with tabs[4]:  # Preços
        st.subheader("Análise de Preços")
        if 'Total Venda' in df_vendas.columns and 'Quantidade' in df_vendas.columns:
            df_vendas['Preço Médio'] = df_vendas['Total Venda'] / df_vendas['Quantidade']
            st.scatter_chart(df_vendas, x='Quantidade', y='Preço Médio')
        else:
            st.info("Dados de preço indisponíveis.")

    with tabs[5]:  # Detalhes
        st.subheader("Base de Dados Completa")
        st.dataframe(df_vendas, use_container_width=True)

    with tabs[6]:  # Giro
        st.subheader("Giro de Produtos")
        if 'Quantidade' in df_vendas.columns:
            top_giro = df_vendas.groupby('Produto')['Quantidade'].sum().sort_values(ascending=False).head(20)
            st.bar_chart(top_giro)
        else:
            st.info("Dados de quantidade indisponíveis.")

    with tabs[7]:  # Oportunidades
        st.subheader("🚀 Oportunidades de Melhoria")
        st.write("Produtos com alta margem e baixo volume (Interrogação) que podem ser promovidos:")
        if 'Quantidade' in df_vendas.columns and 'Margem (%)' in df_vendas.columns:
            df_bcg_oport = df_vendas.groupby('Produto').agg({
                'Quantidade': 'sum',
                'Margem (%)': 'mean',
                'Total Venda': 'sum'
            }).reset_index()
            
            med_qtd_o = df_bcg_oport['Quantidade'].median()
            med_margem_o = df_bcg_oport['Margem (%)'].median()
            
            def classificar_bcg_oport(row):
                if row['Quantidade'] >= med_qtd_o and row['Margem (%)'] >= med_margem_o: return 'Estrela ⭐'
                if row['Quantidade'] >= med_qtd_o and row['Margem (%)'] < med_margem_o: return 'Vaca Leiteira 🐄'
                if row['Quantidade'] < med_qtd_o and row['Margem (%)'] >= med_margem_o: return 'Interrogação ❓'
                return 'Abacaxi 🍍'
            
            df_bcg_oport['Classificação'] = df_bcg_oport.apply(classificar_bcg_oport, axis=1)
            oportunidades = df_bcg_oport[df_bcg_oport['Classificação'] == 'Interrogação ❓'].sort_values('Margem (%)', ascending=False)
            st.dataframe(oportunidades, use_container_width=True)
        else:
            st.info("Classificação BCG não disponível.")

else:
    with tabs[0]:
        st.info("Carregando dados da planilha mestre...")
