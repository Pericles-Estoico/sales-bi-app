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

# ============================================
# CONFIGURAÇÃO
# ============================================
st.set_page_config(
    page_title="Sales BI Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# IDs e URLs
SHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid="

# GIDs das abas
ABAS_URLS = {
    'produtos': BASE_URL + "1037607798",
    'kits': BASE_URL + "1569485799",
    'custo_pedido': BASE_URL + "1720329296",
    'canais': BASE_URL + "1639432432",
    'impostos': BASE_URL + "260097325",
    'frete': BASE_URL + "1928835495",
    'metas': BASE_URL + "1477190272",
    'dashboard_geral': BASE_URL + "749174572",
    'detalhes_canais': BASE_URL + "961459380",
    'resultado_cnpj': BASE_URL + "1830625125",
    'executiva_simples': BASE_URL + "1734348857",
    'precos_simples_mktp': BASE_URL + "2119792312",
    'bcg_canal_mkt': BASE_URL + "914780374",
    'vendas_sku_geral': BASE_URL + "1138113192",
    'oportunidades_canais_mkt': BASE_URL + "706549654"
}

# Canais disponíveis
CHANNELS = {
    "Geral": "geral",
    "Mercado Livre": "mercado_livre",
    "Shopee Matriz": "shopee_matriz",
    "Shopee 1:50": "shopee_150",
    "Shein": "shein"
}

# Colunas esperadas
COLUNAS_ESPERADAS = [
    'Data', 'Canal', 'CNPJ', 'Produto', 'Tipo', 'Quantidade',
    'Total Venda', 'Custo Produto', 'Impostos', 'Comissão',
    'Taxas Fixas', 'Embalagem', 'Investimento Ads', 'Custo Total',
    'Lucro Bruto', 'Margem (%)'
]

# Ordem BCG
ORDEM_BCG = ['Vaca Leiteira 🐄', 'Estrela ⭐', 'Interrogação ❓', 'Abacaxi 🍍']

# ============================================
# FUNÇÕES UTILITÁRIAS
# ============================================
def clean_currency(val):
    """Remove R$, pontos e converte vírgula para ponto"""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    val = val.replace('R$', '').replace(' ', '').replace('\xa0', '')
    val = val.replace('.', '')  # Remove separador de milhar
    val = val.replace(',', '.')  # Vírgula vira ponto
    try:
        return float(val)
    except:
        return 0.0

def clean_percent_read(val):
    """Remove % e converte para decimal (ex: 45,5% -> 0.455)"""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    val = val.replace('%', '').replace(' ', '')
    val = val.replace(',', '.')
    try:
        num = float(val)
        if num > 1:  # Se veio como 45.5 em vez de 0.455
            num = num / 100
        return num
    except:
        return 0.0

def clean_float(val):
    """Converte string para float (vírgula -> ponto)"""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    val = val.replace(',', '.')
    try:
        return float(val)
    except:
        return 0.0

def format_currency_br(val):
    """Formata número como moeda brasileira"""
    if pd.isna(val) or val == 0:
        return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')

def format_percent_br(val):
    """Formata número como percentual brasileiro"""
    if pd.isna(val):
        return "0,00%"
    return f"{val*100:.2f}%".replace('.', ',')

def to_excel(df):
    """Converte DataFrame para Excel em memória"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
    return output.getvalue()

def normalizar(texto):
    """Remove acentos e caracteres especiais"""
    if pd.isna(texto):
        return ""
    texto = str(texto)
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

def normalize_key(key):
    """Normaliza chave para comparação"""
    return normalizar(str(key).lower().strip())

def safe_int(val):
    """Converte para int com segurança"""
    try:
        return int(float(val))
    except:
        return 0

# ============================================
# AUTENTICAÇÃO GOOGLE SHEETS
# ============================================
@st.cache_resource
def get_gspread_client():
    """Conecta ao Google Sheets com autenticação blindada"""
    try:
        creds_raw = st.secrets.get("GOOGLE_SHEETS_CREDENTIALS")
        
        if creds_raw is None:
            st.error("❌ ERRO CRÍTICO: Credenciais não encontradas em st.secrets")
            st.stop()
        
        # Converter para dict
        if hasattr(creds_raw, 'to_dict'):
            creds_dict = creds_raw.to_dict()
        elif isinstance(creds_raw, dict):
            creds_dict = creds_raw
        else:
            creds_dict = json.loads(str(creds_raw))
        
        # Normalizar private_key
        if 'private_key' in creds_dict:
            pk = creds_dict['private_key']
            pk = pk.replace('\\n', '\n')
            if not pk.startswith('-----BEGIN PRIVATE KEY-----'):
                pk = '-----BEGIN PRIVATE KEY-----\n' + pk
            if not pk.endswith('-----END PRIVATE KEY-----\n'):
                pk = pk + '\n-----END PRIVATE KEY-----\n'
            creds_dict['private_key'] = pk
        
        # Validar campos obrigatórios
        required = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing = [f for f in required if f not in creds_dict]
        if missing:
            st.error(f"❌ Campos faltando: {', '.join(missing)}")
            st.stop()
        
        # Autenticar
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        
        # Testar conexão
        try:
            client.open_by_key(SHEET_ID)
        except Exception as e:
            st.error(f"❌ Erro ao abrir planilha: {str(e)}")
            st.stop()
        
        return client
        
    except Exception as e:
        st.error(f"❌ ERRO DE AUTENTICAÇÃO: {str(e)}")
        st.stop()

# ============================================
# SALVAMENTO DE DADOS
# ============================================
def salvar_dados_sheets(df):
    """Salva DataFrame na aba 'Detalhes_Canais' do Google Sheets"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        
        # Tentar múltiplos nomes de aba
        nomes_possiveis = ["Detalhes_Canais", "Detalhes Canais", "6. Detalhes", "DetalhesCanais"]
        worksheet = None
        
        for nome in nomes_possiveis:
            try:
                worksheet = sh.worksheet(nome)
                break
            except:
                continue
        
        if worksheet is None:
            st.error(f"❌ Nenhuma aba encontrada. Tentou: {', '.join(nomes_possiveis)}")
            return False
        
        # Obter cabeçalho atual
        headers = worksheet.row_values(1)
        if not headers:
            worksheet.append_row(COLUNAS_ESPERADAS)
            headers = COLUNAS_ESPERADAS
        
        # Alinhar DataFrame com as colunas da planilha
        df_aligned = pd.DataFrame(columns=headers)
        for col in headers:
            if col in df.columns:
                df_aligned[col] = df[col]
            else:
                df_aligned[col] = ""
        
        # Preencher vazios
        df_aligned = df_aligned.fillna("")
        
        # Converter para lista de listas
        rows = df_aligned.values.tolist()
        
        # Salvar em lote
        if rows:
            worksheet.append_rows(rows, value_input_option='RAW')
        
        st.success(f"✅ {len(rows)} linhas salvas na aba '{worksheet.title}'!")
        
        # ⏱️ AGUARDAR PROCESSAMENTO DAS FÓRMULAS
        with st.spinner("⏱️ Aguardando Google Sheets processar fórmulas..."):
            time.sleep(3)
        
        # 🔄 LIMPAR CACHE
        st.cache_data.clear()
        st.info("🔄 Cache limpo! Atualizando dados...")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {str(e)}")
        return False

# ============================================
# PREPARAÇÃO DOS DADOS
# ============================================
def preparar_dados_para_salvar(df_raw, canal, cnpj, data_venda):
    """Prepara DataFrame para salvar no Google Sheets"""
    df = df_raw.copy()
    
    # Garantir colunas obrigatórias
    df['Data'] = data_venda.strftime('%Y-%m-%d')
    df['Canal'] = canal
    df['CNPJ'] = cnpj
    
    # Verificar Produto
    if 'Produto' not in df.columns:
        st.error("❌ Coluna 'Produto' não encontrada!")
        return None
    
    # Verificar e converter Quantidade
    if 'Quantidade' not in df.columns:
        st.error("❌ Coluna 'Quantidade' não encontrada!")
        return None
    
    df['Quantidade'] = df['Quantidade'].apply(lambda x: safe_int(x))
    df = df[df['Quantidade'] > 0]  # Remover linhas inválidas
    
    if df.empty:
        st.error("❌ Nenhuma linha válida após filtrar Quantidade > 0")
        return None
    
    # Total Venda
    if 'Total Venda' not in df.columns:
        st.warning("⚠️ 'Total Venda' não encontrado. Calculando: Quantidade × 50")
        df['Total Venda'] = df['Quantidade'] * 50.0
    else:
        df['Total Venda'] = df['Total Venda'].apply(clean_currency)
    
    # Garantir colunas financeiras com defaults
    colunas_financeiras = [
        'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas',
        'Embalagem', 'Investimento Ads', 'Custo Total', 'Lucro Bruto'
    ]
    for col in colunas_financeiras:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].apply(clean_currency)
    
    # Tipo e Margem
    df['Tipo'] = 'Venda'
    if 'Margem (%)' not in df.columns:
        df['Margem (%)'] = 0.0
    else:
        df['Margem (%)'] = df['Margem (%)'].apply(clean_percent_read)
    
    # Reordenar para COLUNAS_ESPERADAS
    df_final = pd.DataFrame()
    for col in COLUNAS_ESPERADAS:
        if col in df.columns:
            df_final[col] = df[col]
        else:
            df_final[col] = 0.0 if col not in ['Data', 'Canal', 'CNPJ', 'Produto', 'Tipo'] else ""
    
    return df_final

# ============================================
# CARREGAMENTO DE DADOS
# ============================================
@st.cache_data(ttl=300)
def carregar_aba(nome_aba):
    """Carrega uma aba da planilha via CSV export"""
    try:
        if nome_aba not in ABAS_URLS:
            st.warning(f"⚠️ Aba '{nome_aba}' não encontrada em ABAS_URLS")
            return pd.DataFrame()
        
        url = ABAS_URLS[nome_aba]
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        df = pd.read_csv(StringIO(response.text))
        
        if df.empty:
            return df
        
        # Limpeza de colunas monetárias
        colunas_monetarias = [
            'Total Venda', 'Custo Produto', 'Impostos', 'Comissão',
            'Taxas Fixas', 'Embalagem', 'Investimento Ads',
            'Custo Total', 'Lucro Bruto'
        ]
        for col in colunas_monetarias:
            if col in df.columns:
                df[col] = df[col].apply(clean_currency)
        
        # Quantidade
        if 'Quantidade' in df.columns:
            df['Quantidade'] = df['Quantidade'].apply(lambda x: safe_int(clean_float(x)))
        
        # Margem (%)
        if 'Margem (%)' in df.columns:
            df['Margem (%)'] = df['Margem (%)'].apply(clean_percent_read)
        
        # Remover linhas inválidas
        if 'Produto' in df.columns:
            df = df[df['Produto'].notna()]
            df = df[df['Produto'] != '']
        
        if 'Quantidade' in df.columns:
            df = df[df['Quantidade'] > 0]
        
        return df
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar '{nome_aba}': {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_metas():
    """Carrega as metas da planilha"""
    df = carregar_aba('metas')
    if df.empty:
        return {
            'margem_minima': 0.20,
            'margem_ideal': 0.30,
            'ticket_minimo': 45.0,
            'ticket_ideal': 60.0
        }
    
    try:
        metas = {}
        for _, row in df.iterrows():
            chave = normalize_key(row.get('Métrica', ''))
            valor = clean_float(row.get('Valor', 0))
            
            if 'margem' in chave and 'minima' in chave:
                metas['margem_minima'] = valor / 100 if valor > 1 else valor
            elif 'margem' in chave and 'ideal' in chave:
                metas['margem_ideal'] = valor / 100 if valor > 1 else valor
            elif 'ticket' in chave and 'minimo' in chave:
                metas['ticket_minimo'] = valor
            elif 'ticket' in chave and 'ideal' in chave:
                metas['ticket_ideal'] = valor
        
        # Defaults se não encontrar
        metas.setdefault('margem_minima', 0.20)
        metas.setdefault('margem_ideal', 0.30)
        metas.setdefault('ticket_minimo', 45.0)
        metas.setdefault('ticket_ideal', 60.0)
        
        return metas
        
    except Exception as e:
        st.error(f"❌ Erro ao processar metas: {str(e)}")
        return {
            'margem_minima': 0.20,
            'margem_ideal': 0.30,
            'ticket_minimo': 45.0,
            'ticket_ideal': 60.0
        }

def get_status_meta(valor, minimo, ideal, inverso=False):
    """Retorna emoji de status baseado nas metas"""
    if inverso:  # Para valores onde menor é melhor
        if valor <= ideal:
            return "🟢"
        elif valor <= minimo:
            return "🟡"
        else:
            return "🔴"
    else:  # Para valores onde maior é melhor
        if valor >= ideal:
            return "🟢"
        elif valor >= minimo:
            return "🟡"
        else:
            return "🔴"

# ============================================
# INTERFACE PRINCIPAL
# ============================================
def main():
    st.title("📊 Sales BI Pro - V56")
    st.caption("✅ Integração Completa | Dados Reais da Planilha")
    
    # ============================================
    # SIDEBAR - DIAGNÓSTICO E IMPORTAÇÃO
    # ============================================
    with st.sidebar:
        st.header("🔧 Configuração")
        
        # DIAGNÓSTICO DE CONEXÃO
        if st.button("🔍 Testar Conexão"):
            with st.spinner("Testando conexão..."):
                try:
                    client = get_gspread_client()
                    sh = client.open_by_key(SHEET_ID)
                    st.success(f"✅ Conectado! Planilha: **{sh.title}**")
                    
                    # Testar todas as abas
                    st.info("📊 **Linhas por aba:**")
                    for nome_aba in ABAS_URLS.keys():
                        df = carregar_aba(nome_aba)
                        st.write(f"- {nome_aba}: {len(df)} linhas")
                    
                except Exception as e:
                    st.error(f"❌ Erro: {str(e)}")
        
        st.divider()
        
        # MODO SIMULAÇÃO
        st.header("🧪 Modo de Operação")
        modo_simulacao = st.checkbox(
            "🔒 MODO SIMULAÇÃO (Sandbox)",
            value=st.session_state.get('modo_simulacao', False),
            help="Ativado: dados não são salvos na planilha oficial"
        )
        st.session_state['modo_simulacao'] = modo_simulacao
        
        if modo_simulacao:
            st.warning("⚠️ **MODO SIMULAÇÃO ATIVO** - Dados não serão salvos!")
        
        st.divider()
        
        # ATUALIZAR DADOS
        st.header("🔄 Gerenciamento")
        if st.button("🔄 Atualizar Dados (Limpar Cache)"):
            st.cache_data.clear()
            st.success("✅ Cache limpo! Recarregando...")
            st.rerun()
        
        st.divider()
        
        # IMPORTAÇÃO DE VENDAS
        st.header("📥 Importar Novas Vendas")
        
        # Formato
        formato = st.radio(
            "Formato de Origem:",
            ["Padrão", "Bling"],
            help="Padrão: Produto, Quantidade, Valor | Bling: colunas do Bling"
        )
        
        # Canal
        canal_display = st.selectbox("Canal de Venda:", list(CHANNELS.keys()))
        canal = CHANNELS[canal_display]
        
        # CNPJ
        cnpj = st.selectbox(
            "CNPJ / Regime:",
            ["Simples Nacional", "Lucro Presumido"]
        )
        
        # Data
        data_venda = st.date_input(
            "Data da Venda:",
            value=datetime.now()
        )
        
        # Upload
        uploaded_file = st.file_uploader(
            "Arquivo Excel (.xlsx ou .xls):",
            type=['xlsx', 'xls'],
            help="Upload do arquivo de vendas"
        )
        
        if uploaded_file:
            try:
                # Ler Excel
                df_upload = pd.read_excel(uploaded_file)
                
                st.success(f"✅ Arquivo carregado: {len(df_upload)} linhas")
                
                # Detectar colunas
                colunas = df_upload.columns.tolist()
                colunas_norm = [normalize_key(c) for c in colunas]
                
                # Mapear Produto
                col_produto = None
                for i, cn in enumerate(colunas_norm):
                    if 'produto' in cn or 'item' in cn or 'codigo' in cn or 'sku' in cn:
                        col_produto = colunas[i]
                        break
                
                # Mapear Quantidade
                col_quantidade = None
                for i, cn in enumerate(colunas_norm):
                    if 'quantidade' in cn or 'qtde' in cn or 'qtd' in cn:
                        col_quantidade = colunas[i]
                        break
                
                # Mapear Total Venda
                col_valor = None
                for i, cn in enumerate(colunas_norm):
                    if 'valor' in cn or 'total' in cn or 'preco' in cn:
                        col_valor = colunas[i]
                        break
                
                # Renomear
                rename_map = {}
                if col_produto:
                    rename_map[col_produto] = 'Produto'
                if col_quantidade:
                    rename_map[col_quantidade] = 'Quantidade'
                if col_valor:
                    rename_map[col_valor] = 'Total Venda'
                
                if rename_map:
                    df_upload = df_upload.rename(columns=rename_map)
                
                # Verificar se tem as colunas mínimas
                if 'Produto' not in df_upload.columns or 'Quantidade' not in df_upload.columns:
                    st.error("❌ Colunas 'Produto' e 'Quantidade' não encontradas!")
                    st.info("**Colunas detectadas:**")
                    st.write(colunas)
                else:
                    # Mostrar mapeamento
                    st.info("**Mapeamento de colunas:**")
                    for old, new in rename_map.items():
                        st.write(f"- {old} → {new}")
                    
                    # Botões de ação
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("🧪 Simular", use_container_width=True):
                            st.session_state['modo_simulacao'] = True
                            df_prep = preparar_dados_para_salvar(df_upload, canal, cnpj, data_venda)
                            if df_prep is not None:
                                st.session_state['novos_dados_temp'] = df_prep
                                st.success(f"✅ Simulação: {len(df_prep)} linhas preparadas")
                    
                    with col2:
                        if st.button("🔍 Pré-visualizar", use_container_width=True):
                            df_prep = preparar_dados_para_salvar(df_upload, canal, cnpj, data_venda)
                            if df_prep is not None:
                                st.session_state['novos_dados_temp'] = df_prep
                                st.success(f"✅ Pré-visualização: {len(df_prep)} linhas")
                    
                    # Pré-visualização
                    if 'novos_dados_temp' in st.session_state:
                        st.divider()
                        st.subheader("👁️ Pré-visualização")
                        st.dataframe(
                            st.session_state['novos_dados_temp'].head(10),
                            use_container_width=True
                        )
                        
                        # Estatísticas
                        df_temp = st.session_state['novos_dados_temp']
                        total_vendas = df_temp['Total Venda'].sum()
                        total_pecas = df_temp['Quantidade'].sum()
                        ticket = total_vendas / len(df_temp) if len(df_temp) > 0 else 0
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total", format_currency_br(total_vendas))
                        col2.metric("Peças", f"{total_pecas:,}")
                        col3.metric("Ticket", format_currency_br(ticket))
                        
                        # Confirmação de salvamento
                        if not st.session_state.get('modo_simulacao', False):
                            confirmar = st.checkbox(
                                "✅ Confirmo que analisei a simulação e os dados estão corretos.",
                                key="confirmar_salvar"
                            )
                            
                            if confirmar:
                                if st.button("💾 SALVAR DADOS NA PLANILHA (OFICIAL)", type="primary", use_container_width=True):
                                    with st.spinner("Salvando na planilha..."):
                                        sucesso = salvar_dados_sheets(df_temp)
                                        if sucesso:
                                            # Limpar temporários
                                            del st.session_state['novos_dados_temp']
                                            st.balloons()
                                            st.success("🎉 Dados salvos com sucesso!")
                                            time.sleep(2)
                                            st.rerun()
                        else:
                            st.info("🔒 Modo Simulação ativo - desative para salvar")
                
            except Exception as e:
                st.error(f"❌ Erro ao processar arquivo: {str(e)}")
    
    # ============================================
    # ÁREA PRINCIPAL - DASHBOARD
    # ============================================
    
    # Carregar metas
    metas = carregar_metas()
    
    # Carregar dados EXECUTIVA SIMPLES (dados processados por produto)
    with st.spinner("📊 Carregando dados processados..."):
        df_executiva = carregar_aba('executiva_simples')
    
    if df_executiva.empty:
        st.warning("⚠️ Nenhum dado encontrado na aba Executiva Simples")
        st.info("💡 **Dica:** Faça upload de vendas ou verifique a planilha")
        return
    
    st.success(f"✅ {len(df_executiva)} produtos carregados")
    
    # MÉTRICAS PRINCIPAIS
    st.header("📈 Métricas Principais")
    
    # Calcular métricas
    total_vendas = df_executiva['Total Venda'].sum() if 'Total Venda' in df_executiva.columns else 0
    total_lucro = df_executiva['Lucro Bruto'].sum() if 'Lucro Bruto' in df_executiva.columns else 0
    total_qtd = df_executiva['Quantidade'].sum() if 'Quantidade' in df_executiva.columns else 0
    margem_media = (total_lucro / total_vendas) if total_vendas > 0 else 0
    ticket_medio = total_vendas / len(df_executiva) if len(df_executiva) > 0 else 0
    
    # Exibir métricas
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "💰 Vendas Totais",
            format_currency_br(total_vendas)
        )
    
    with col2:
        st.metric(
            "💵 Lucro Bruto",
            format_currency_br(total_lucro)
        )
    
    with col3:
        st.metric(
            "📦 Quantidade",
            f"{total_qtd:,.0f}"
        )
    
    with col4:
        status_margem = get_status_meta(margem_media, metas['margem_minima'], metas['margem_ideal'])
        st.metric(
            f"{status_margem} Margem Média",
            format_percent_br(margem_media)
        )
    
    with col5:
        status_ticket = get_status_meta(ticket_medio, metas['ticket_minimo'], metas['ticket_ideal'])
        st.metric(
            f"{status_ticket} Ticket Médio",
            format_currency_br(ticket_medio)
        )
    
    # ABAS DO DASHBOARD
    tabs = st.tabs([
        "📊 Top Produtos",
        "🎯 BCG por Canal",
        "💲 Preços MKTP",
        "🔄 Giro SKU",
        "💡 Oportunidades",
        "📋 Todos os Dados"
    ])
    
    # TAB 1: Top Produtos
    with tabs[0]:
        st.subheader("🏆 Top 20 Produtos")
        
        top20 = df_executiva.nlargest(20, 'Quantidade')
        
        # Gráfico
        st.bar_chart(top20.set_index('Produto')['Quantidade'])
        
        # Tabela
        st.dataframe(
            top20[[' Produto', 'Quantidade', 'Total Venda', 'Lucro Bruto', 'Margem (%)']].style.format({
                'Total Venda': format_currency_br,
                'Lucro Bruto': format_currency_br,
                'Margem (%)': format_percent_br,
                'Quantidade': '{:,.0f}'
            }),
            use_container_width=True
        )
    
    # TAB 2: BCG por Canal
    with tabs[1]:
        st.subheader("🎯 Matriz BCG por Canal")
        df_bcg = carregar_aba('bcg_canal_mkt')
        
        if not df_bcg.empty:
            st.dataframe(df_bcg, use_container_width=True)
        else:
            st.info("📭 Nenhum dado disponível")
    
    # TAB 3: Preços MKTP
    with tabs[2]:
        st.subheader("💲 Análise de Preços Marketplace")
        df_precos = carregar_aba('precos_simples_mktp')
        
        if not df_precos.empty:
            st.dataframe(df_precos, use_container_width=True)
        else:
            st.info("📭 Nenhum dado disponível")
    
    # TAB 4: Giro SKU
    with tabs[3]:
        st.subheader("🔄 Giro de Produtos (SKU)")
        df_giro = carregar_aba('vendas_sku_geral')
        
        if not df_giro.empty:
            st.dataframe(df_giro, use_container_width=True)
        else:
            st.info("📭 Nenhum dado disponível")
    
    # TAB 5: Oportunidades
    with tabs[4]:
        st.subheader("💡 Oportunidades de Melhoria")
        df_oport = carregar_aba('oportunidades_canais_mkt')
        
        if not df_oport.empty:
            st.dataframe(df_oport, use_container_width=True)
        else:
            st.info("📭 Nenhum dado disponível")
    
    # TAB 6: Todos os Dados
    with tabs[5]:
        st.subheader("📋 Tabela Completa - Executiva Simples")
        st.dataframe(df_executiva, use_container_width=True)
        
        # Botão de download
        excel_data = to_excel(df_executiva)
        st.download_button(
            label="📥 Baixar Excel",
            data=excel_data,
            file_name=f"executiva_simples_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    # RODAPÉ
    st.divider()
    st.caption("📊 Sales BI Pro V56 | ✅ Lendo Dados Reais da Planilha")

if __name__ == "__main__":
    main()
