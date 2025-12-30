"""
═══════════════════════════════════════════════════════════════════════════════
    SALES BI PRO - V55 FINAL (RECONSTRUÍDO DO ZERO)
═══════════════════════════════════════════════════════════════════════════════

✅ CORREÇÕES IMPLEMENTADAS:
   1. Separação completa: Upload vs. Dashboard
   2. Upload salva em "Detalhes_Canais" (dados brutos)
   3. Dashboard lê abas PROCESSADAS (com cálculos corretos)
   4. Integração com abas de referência (Custos, Impostos, Taxas)
   5. Status de Metas (🟢🟡🔴)
   6. Cache inteligente por aba
   7. Limpeza robusta de dados brasileiros (R$, vírgulas)

📊 PLANILHA:
   ID: 1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E
   Nome: Config_BI_Final_MatrizBCG

🔐 AUTENTICAÇÃO:
   Service Account: sales-bi-bot@sales-bi-analytics.iam.gserviceaccount.com
   Secrets: GOOGLE_SHEETS_CREDENTIALS configurado no Streamlit Cloud

═══════════════════════════════════════════════════════════════════════════════
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import io
import re

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURAÇÕES GLOBAIS
# ═══════════════════════════════════════════════════════════════════════════════

SHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid="

# Mapeamento de TODAS as abas com seus GIDs
ABAS = {
    # Abas de REFERÊNCIA (dados mestres)
    "produtos": {"gid": "1037607798", "nome": "Produtos"},
    "kits": {"gid": "1569485799", "nome": "Kits"},
    "custos": {"gid": "1720329296", "nome": "Custo por pedido"},
    "canais": {"gid": "1639432432", "nome": "Canais"},
    "impostos": {"gid": "260097325", "nome": "Impostos"},
    "frete": {"gid": "1928835495", "nome": "Frete"},
    "metas": {"gid": "1477190272", "nome": "Metas"},
    
    # Aba de ENTRADA (onde salvamos uploads)
    "detalhes_canais": {"gid": "961459380", "nome": "Detalhes_Canais"},
    
    # Abas PROCESSADAS (dashboard lê daqui)
    "dashboard_geral": {"gid": "749174572", "nome": "Dashboard_Geral"},
    "resultado_cnpj": {"gid": "1830625125", "nome": "Resultado_CNPJ"},
    "executiva_simples": {"gid": "1734348857", "nome": "Executiva_Simples"},
    "preco_simples_mktp": {"gid": "2119792312", "nome": "Preço_Simples_MKTP"},
    "bcg_canal_mkt": {"gid": "914780374", "nome": "BCG_Canal_Mkt"},
    "vendas_sku_geral": {"gid": "1138113192", "nome": "Vendas_sku_geral"},
    "oportunidades_canais_mkt": {"gid": "706549654", "nome": "Oportunidades_canais_mkt"},
}

# URLs de exportação CSV
ABAS_URLS = {k: BASE_URL + v["gid"] for k, v in ABAS.items()}

# Canais de venda
CHANNELS = {
    "geral": "Geral",
    "mercado_livre": "Mercado Livre",
    "shopee_matriz": "Shopee Matriz",
    "shopee_150": "Shopee 150",
    "shein": "Shein"
}

# Colunas esperadas para upload
COLUNAS_ESPERADAS = [
    "Data", "Canal", "CNPJ", "Produto", "Tipo", "Quantidade", 
    "Total Venda", "Custo Produto", "Impostos", "Comissão", 
    "Taxas Fixas", "Embalagem", "Investimento Ads", 
    "Custo Total", "Lucro Bruto", "Margem (%)"
]

# Ordem BCG
ORDEM_BCG = [
    "Vaca Leiteira 🐄",
    "Estrela ⭐",
    "Interrogação ❓",
    "Abacaxi 🍍"
]

# Metas
METAS = {
    "margem_minima": 0.20,   # 20%
    "margem_ideal": 0.30,    # 30%
    "ticket_minimo": 45.0,   # R$ 45
    "ticket_ideal": 60.0     # R$ 60
}

# ═══════════════════════════════════════════════════════════════════════════════
# 2. FUNÇÕES UTILITÁRIAS
# ═══════════════════════════════════════════════════════════════════════════════

def clean_currency(value):
    """Remove R$, espaços e converte vírgula para ponto"""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    
    # Remove R$, espaços, pontos de milhares
    cleaned = str(value).replace('R$', '').replace(' ', '').replace('.', '')
    # Troca vírgula por ponto
    cleaned = cleaned.replace(',', '.')
    
    try:
        return float(cleaned)
    except:
        return 0.0

def clean_percent(value):
    """Converte percentual brasileiro para decimal"""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        # Se já é número, assume que está em decimal
        if value <= 1:
            return float(value)
        # Se > 1, assume que está em percentual
        return float(value) / 100
    
    # Remove %, espaços
    cleaned = str(value).replace('%', '').replace(' ', '')
    # Troca vírgula por ponto
    cleaned = cleaned.replace(',', '.')
    
    try:
        num = float(cleaned)
        # Se > 1, divide por 100
        return num / 100 if num > 1 else num
    except:
        return 0.0

def format_currency_br(value):
    """Formata número para moeda brasileira"""
    if pd.isna(value) or value == 0:
        return "R$ 0,00"
    try:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def format_percent_br(value):
    """Formata decimal para percentual brasileiro"""
    if pd.isna(value):
        return "0,00%"
    try:
        return f"{value * 100:.2f}%".replace(".", ",")
    except:
        return "0,00%"

def normalizar(texto):
    """Normaliza texto para comparação"""
    if pd.isna(texto):
        return ""
    return str(texto).strip().lower()

def safe_int(value):
    """Converte para inteiro de forma segura"""
    try:
        return int(float(value))
    except:
        return 0

def get_status_meta(valor, minimo, ideal):
    """Retorna status visual baseado nas metas"""
    if valor >= ideal:
        return "🟢"
    elif valor >= minimo:
        return "🟡"
    else:
        return "🔴"

# ═══════════════════════════════════════════════════════════════════════════════
# 3. AUTENTICAÇÃO GOOGLE SHEETS
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_gspread_client():
    """
    Autentica com Google Sheets usando service account
    Retorna cliente gspread autenticado
    """
    try:
        # Busca credenciais do Streamlit Secrets
        creds_raw = st.secrets.get("GOOGLE_SHEETS_CREDENTIALS")
        
        if not creds_raw:
            st.error("❌ GOOGLE_SHEETS_CREDENTIALS não encontrado nos Secrets")
            return None
        
        # Converte para dict
        if hasattr(creds_raw, '_data'):
            creds_dict = dict(creds_raw._data)
        elif hasattr(creds_raw, 'to_dict'):
            creds_dict = creds_raw.to_dict()
        elif isinstance(creds_raw, dict):
            creds_dict = creds_raw
        else:
            # Tenta parsear como JSON
            try:
                creds_dict = json.loads(str(creds_raw))
            except:
                st.error("❌ Formato de credenciais não reconhecido")
                return None
        
        # Normaliza private_key
        if 'private_key' in creds_dict:
            pk = creds_dict['private_key']
            if isinstance(pk, str):
                # Garante quebras de linha corretas
                pk = pk.replace('\\n', '\n')
                creds_dict['private_key'] = pk
        
        # Valida campos obrigatórios
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing = [f for f in required_fields if f not in creds_dict]
        if missing:
            st.error(f"❌ Campos obrigatórios ausentes: {', '.join(missing)}")
            return None
        
        # Define scopes
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Cria credenciais
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=scopes
        )
        
        # Autentica com gspread
        client = gspread.authorize(credentials)
        
        # Testa conexão
        try:
            client.openall()
            return client
        except Exception as e:
            st.error(f"❌ Erro ao testar conexão: {str(e)}")
            return None
            
    except Exception as e:
        st.error(f"❌ Erro na autenticação: {str(e)}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# 4. FUNÇÕES DE LEITURA DE DADOS (DASHBOARD)
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def carregar_aba(nome_aba):
    """
    Carrega uma aba da planilha via CSV export
    Aplica limpeza automática de dados brasileiros
    """
    try:
        url = ABAS_URLS.get(nome_aba)
        if not url:
            st.error(f"❌ Aba '{nome_aba}' não encontrada no mapeamento")
            return pd.DataFrame()
        
        # Lê CSV
        df = pd.read_csv(url, on_bad_lines='skip')
        
        if df.empty:
            return pd.DataFrame()
        
        # Identifica e limpa colunas monetárias
        colunas_monetarias = [
            'Total Venda', 'Custo Produto', 'Impostos', 'Comissão',
            'Taxas Fixas', 'Embalagem', 'Investimento Ads', 
            'Custo Total', 'Lucro Bruto', 'Valor', 'Custo', 'Preço'
        ]
        
        for col in df.columns:
            if any(mon in col for mon in colunas_monetarias):
                df[col] = df[col].apply(clean_currency)
        
        # Limpa coluna de Margem
        if 'Margem (%)' in df.columns or 'Margem' in df.columns:
            col_margem = 'Margem (%)' if 'Margem (%)' in df.columns else 'Margem'
            df[col_margem] = df[col_margem].apply(clean_percent)
        
        # Limpa Quantidade
        if 'Quantidade' in df.columns:
            df['Quantidade'] = df['Quantidade'].apply(lambda x: safe_int(x) if pd.notna(x) else 0)
        
        return df
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar aba '{nome_aba}': {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_dashboard_geral():
    """Carrega a aba Dashboard_Geral (dados consolidados por canal)"""
    return carregar_aba("dashboard_geral")

@st.cache_data(ttl=300)
def carregar_bcg_canal():
    """Carrega a aba BCG_Canal_Mkt (matriz BCG por canal)"""
    return carregar_aba("bcg_canal_mkt")

@st.cache_data(ttl=300)
def carregar_vendas_sku():
    """Carrega a aba Vendas_sku_geral (giro de produtos)"""
    return carregar_aba("vendas_sku_geral")

@st.cache_data(ttl=300)
def carregar_oportunidades():
    """Carrega a aba Oportunidades_canais_mkt"""
    return carregar_aba("oportunidades_canais_mkt")

@st.cache_data(ttl=300)
def carregar_resultado_cnpj():
    """Carrega a aba Resultado_CNPJ"""
    return carregar_aba("resultado_cnpj")

@st.cache_data(ttl=300)
def carregar_precos_mktp():
    """Carrega a aba Preço_Simples_MKTP"""
    return carregar_aba("preco_simples_mktp")

@st.cache_data(ttl=300)
def carregar_metas():
    """Carrega metas da planilha ou usa valores padrão"""
    try:
        df_metas = carregar_aba("metas")
        if not df_metas.empty and len(df_metas) > 0:
            # Tenta extrair valores da primeira linha
            metas_custom = {}
            if 'Margem Mínima' in df_metas.columns:
                metas_custom['margem_minima'] = clean_percent(df_metas['Margem Mínima'].iloc[0])
            if 'Margem Ideal' in df_metas.columns:
                metas_custom['margem_ideal'] = clean_percent(df_metas['Margem Ideal'].iloc[0])
            if 'Ticket Mínimo' in df_metas.columns:
                metas_custom['ticket_minimo'] = clean_currency(df_metas['Ticket Mínimo'].iloc[0])
            if 'Ticket Ideal' in df_metas.columns:
                metas_custom['ticket_ideal'] = clean_currency(df_metas['Ticket Ideal'].iloc[0])
            
            # Mescla com valores padrão
            return {**METAS, **metas_custom}
    except:
        pass
    
    return METAS

# ═══════════════════════════════════════════════════════════════════════════════
# 5. FUNÇÕES DE UPLOAD (SALVAR DADOS)
# ═══════════════════════════════════════════════════════════════════════════════

def preparar_dados_para_salvar(df_raw, canal, cnpj, data_venda):
    """
    Prepara dados do upload para salvar na aba Detalhes_Canais
    Garante todas as colunas esperadas
    """
    try:
        df = df_raw.copy()
        
        # Adiciona metadados
        df['Data'] = data_venda
        df['Canal'] = CHANNELS.get(canal, canal)
        df['CNPJ'] = cnpj
        
        # Valida colunas obrigatórias
        if 'Produto' not in df.columns:
            st.error("❌ Coluna 'Produto' não encontrada")
            return None
        
        if 'Quantidade' not in df.columns:
            st.error("❌ Coluna 'Quantidade' não encontrada")
            return None
        
        # Converte Quantidade para inteiro
        df['Quantidade'] = df['Quantidade'].apply(safe_int)
        
        # Total Venda
        if 'Total Venda' not in df.columns:
            df['Total Venda'] = 0.0
        else:
            df['Total Venda'] = df['Total Venda'].apply(clean_currency)
        
        # Preenche colunas financeiras com 0 (planilha calculará)
        df['Tipo'] = 'Venda'
        df['Custo Produto'] = 0.0
        df['Impostos'] = 0.0
        df['Comissão'] = 0.0
        df['Taxas Fixas'] = 0.0
        df['Embalagem'] = 0.0
        df['Investimento Ads'] = 0.0
        df['Custo Total'] = 0.0
        df['Lucro Bruto'] = 0.0
        df['Margem (%)'] = '0%'
        
        # Garante ordem das colunas
        df_final = df[COLUNAS_ESPERADAS].copy()
        
        st.success(f"✅ {len(df_final)} registros preparados para salvar")
        return df_final
        
    except Exception as e:
        st.error(f"❌ Erro ao preparar dados: {str(e)}")
        return None

def salvar_dados_sheets(df_novos_dados):
    """
    Salva novos dados na aba Detalhes_Canais
    Usa gspread para append direto
    """
    try:
        client = get_gspread_client()
        if not client:
            st.error("❌ Falha na autenticação")
            return False
        
        # Abre a planilha
        sh = client.open_by_key(SHEET_ID)
        
        # Acessa a aba Detalhes_Canais
        try:
            worksheet = sh.worksheet("Detalhes_Canais")
        except:
            st.error("❌ Aba 'Detalhes_Canais' não encontrada na planilha!")
            return False
        
        # Lê headers existentes
        existing_headers = worksheet.row_values(1)
        
        # Se planilha vazia, insere headers
        if not existing_headers or len(existing_headers) == 0:
            worksheet.append_row(COLUNAS_ESPERADAS)
            existing_headers = COLUNAS_ESPERADAS
        
        # Alinha DataFrame com colunas da planilha
        df_aligned = pd.DataFrame(columns=existing_headers)
        for col in existing_headers:
            if col in df_novos_dados.columns:
                df_aligned[col] = df_novos_dados[col]
            else:
                df_aligned[col] = ''
        
        # Converte tudo para string
        df_aligned = df_aligned.astype(str)
        
        # Append em lote
        values = df_aligned.values.tolist()
        worksheet.append_rows(values)
        
        st.success(f"✅ {len(values)} registros salvos na aba 'Detalhes_Canais'!")
        st.info("⏳ Aguarde 1-2 minutos para as fórmulas da planilha processarem os dados")
        return True
        
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {str(e)}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# 6. INTERFACE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Sales BI Pro - V55",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Sales BI Pro - V55 FINAL")
    st.caption("✅ Dashboard lê abas processadas | Upload salva em Detalhes_Canais")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SIDEBAR - CONTROLES
    # ═══════════════════════════════════════════════════════════════════════════
    
    with st.sidebar:
        st.header("⚙️ Controles")
        
        # Teste de conexão
        if st.button("🔍 Testar Conexão", use_container_width=True):
            with st.spinner("Testando..."):
                client = get_gspread_client()
                if client:
                    try:
                        sh = client.open_by_key(SHEET_ID)
                        st.success(f"✅ Conectado!\n\n**Planilha:** {sh.title}")
                        
                        # Lista abas
                        worksheets = sh.worksheets()
                        st.info(f"📋 {len(worksheets)} abas encontradas")
                    except Exception as e:
                        st.error(f"❌ Erro: {str(e)}")
        
        st.divider()
        
        # Modo simulação
        modo_simulacao = st.toggle("🧪 Modo SIMULAÇÃO (não salva)", value=False)
        if modo_simulacao:
            st.warning("⚠️ Dados não serão salvos na planilha")
        
        st.divider()
        
        # Limpar cache
        if st.button("🔄 Atualizar Dados (Limpar Cache)", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABAS PRINCIPAIS
    # ═══════════════════════════════════════════════════════════════════════════
    
    tabs = st.tabs([
        "📤 Importar Vendas",
        "📊 Dashboard Geral",
        "🏢 Por CNPJ",
        "📈 BCG por Canal",
        "💰 Preços MKTP",
        "🔄 Giro SKU",
        "💡 Oportunidades"
    ])
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 1: IMPORTAR VENDAS
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[0]:
        st.header("📤 Importar Vendas")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            canal = st.selectbox(
                "Canal de Venda",
                options=list(CHANNELS.keys()),
                format_func=lambda x: CHANNELS[x]
            )
        
        with col2:
            cnpj = st.selectbox(
                "CNPJ / Regime",
                options=["Simples Nacional", "Lucro Presumido", "MEI"]
            )
        
        with col3:
            data_venda = st.date_input(
                "Data da Venda",
                value=datetime.now()
            ).strftime("%Y-%m-%d")
        
        st.divider()
        
        # Upload de arquivo
        uploaded_file = st.file_uploader(
            "📁 Selecione o arquivo Excel de vendas",
            type=['xlsx', 'xls'],
            help="Arquivo deve conter: Código/Produto, Quantidade, Valor"
        )
        
        if uploaded_file:
            try:
                # Lê Excel
                df_upload = pd.read_excel(uploaded_file)
                
                st.success(f"✅ Arquivo carregado: {len(df_upload)} linhas")
                
                # Mapeamento de colunas
                st.subheader("🔗 Mapeamento de Colunas")
                
                col_map1, col_map2, col_map3 = st.columns(3)
                
                with col_map1:
                    col_produto = st.selectbox(
                        "Coluna de PRODUTO:",
                        options=df_upload.columns.tolist(),
                        index=0
                    )
                
                with col_map2:
                    col_quantidade = st.selectbox(
                        "Coluna de QUANTIDADE:",
                        options=df_upload.columns.tolist(),
                        index=1 if len(df_upload.columns) > 1 else 0
                    )
                
                with col_map3:
                    col_valor = st.selectbox(
                        "Coluna de VALOR:",
                        options=df_upload.columns.tolist(),
                        index=2 if len(df_upload.columns) > 2 else 0
                    )
                
                # Renomeia colunas
                df_mapped = df_upload.rename(columns={
                    col_produto: 'Produto',
                    col_quantidade: 'Quantidade',
                    col_valor: 'Total Venda'
                })
                
                # Limpa valor
                df_mapped['Total Venda'] = df_mapped['Total Venda'].apply(clean_currency)
                df_mapped['Quantidade'] = df_mapped['Quantidade'].apply(safe_int)
                
                # Prepara dados
                df_preparado = preparar_dados_para_salvar(
                    df_mapped[['Produto', 'Quantidade', 'Total Venda']],
                    canal,
                    cnpj,
                    data_venda
                )
                
                if df_preparado is not None:
                    # Pré-visualização
                    st.subheader("👀 Pré-visualização")
                    
                    # Calcula totais
                    total_vendas = df_preparado['Total Venda'].sum()
                    total_pecas = df_preparado['Quantidade'].sum()
                    ticket_medio = total_vendas / len(df_preparado) if len(df_preparado) > 0 else 0
                    
                    col_tot1, col_tot2, col_tot3 = st.columns(3)
                    col_tot1.metric("💰 Total Vendas", format_currency_br(total_vendas))
                    col_tot2.metric("📦 Total Peças", f"{total_pecas}")
                    col_tot3.metric("🎯 Ticket Médio", format_currency_br(ticket_medio))
                    
                    st.dataframe(
                        df_preparado[['Data', 'Canal', 'CNPJ', 'Produto', 'Quantidade', 'Total Venda']],
                        use_container_width=True
                    )
                    
                    st.divider()
                    
                    # Botão de salvar
                    if modo_simulacao:
                        st.info("🧪 Modo SIMULAÇÃO ativo - dados não serão salvos")
                    else:
                        confirmar = st.checkbox("✅ Confirmo que os dados estão corretos")
                        
                        if confirmar:
                            if st.button("💾 SALVAR DADOS NA PLANILHA", type="primary", use_container_width=True):
                                with st.spinner("Salvando..."):
                                    sucesso = salvar_dados_sheets(df_preparado)
                                    if sucesso:
                                        st.balloons()
                                        st.success("✅ Dados salvos com sucesso!")
                                        st.info("💡 Clique em '🔄 Atualizar Dados' no sidebar após 1-2 minutos")
            
            except Exception as e:
                st.error(f"❌ Erro ao processar arquivo: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 2: DASHBOARD GERAL
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[1]:
        st.header("📊 Dashboard Geral")
        
        # Carrega dados processados
        df_dashboard = carregar_dashboard_geral()
        metas = carregar_metas()
        
        if df_dashboard.empty:
            st.warning("⚠️ Nenhum dado encontrado na aba 'Dashboard_Geral'")
        else:
            # Calcula métricas CORRETAS
            total_vendas = df_dashboard['Total Venda'].sum() if 'Total Venda' in df_dashboard.columns else 0
            total_lucro = df_dashboard['Lucro Bruto'].sum() if 'Lucro Bruto' in df_dashboard.columns else 0
            total_quantidade = df_dashboard['Quantidade'].sum() if 'Quantidade' in df_dashboard.columns else 0
            
            # Margem média ponderada
            if total_vendas > 0:
                margem_media = total_lucro / total_vendas
            else:
                margem_media = 0
            
            # Ticket médio
            num_vendas = len(df_dashboard)
            ticket_medio = total_vendas / num_vendas if num_vendas > 0 else 0
            
            # Exibe métricas com status
            col1, col2, col3, col4 = st.columns(4)
            
            col1.metric(
                "💰 Vendas Totais",
                format_currency_br(total_vendas)
            )
            
            status_margem = get_status_meta(
                margem_media,
                metas['margem_minima'],
                metas['margem_ideal']
            )
            col2.metric(
                f"{status_margem} Margem Média",
                format_percent_br(margem_media),
                help=f"Meta: {format_percent_br(metas['margem_minima'])} a {format_percent_br(metas['margem_ideal'])}"
            )
            
            status_ticket = get_status_meta(
                ticket_medio,
                metas['ticket_minimo'],
                metas['ticket_ideal']
            )
            col3.metric(
                f"{status_ticket} Ticket Médio",
                format_currency_br(ticket_medio),
                help=f"Meta: {format_currency_br(metas['ticket_minimo'])} a {format_currency_br(metas['ticket_ideal'])}"
            )
            
            col4.metric(
                "📦 Total Peças",
                f"{int(total_quantidade):,}".replace(",", ".")
            )
            
            st.divider()
            
            # Tabela por canal
            st.subheader("📊 Dados por Canal")
            
            # Formata DataFrame para exibição
            df_display = df_dashboard.copy()
            
            if 'Total Venda' in df_display.columns:
                df_display['Total Venda'] = df_display['Total Venda'].apply(format_currency_br)
            if 'Lucro Bruto' in df_display.columns:
                df_display['Lucro Bruto'] = df_display['Lucro Bruto'].apply(format_currency_br)
            if 'Margem' in df_display.columns or 'Margem (%)' in df_display.columns:
                col_margem = 'Margem (%)' if 'Margem (%)' in df_display.columns else 'Margem'
                df_display[col_margem] = df_display[col_margem].apply(format_percent_br)
            
            st.dataframe(df_display, use_container_width=True)
            
            # Gráfico de vendas por canal
            if 'Canal' in df_dashboard.columns and 'Total Venda' in df_dashboard.columns:
                st.subheader("📈 Vendas por Canal")
                st.bar_chart(
                    df_dashboard.set_index('Canal')['Total Venda'] if 'Canal' in df_dashboard.columns else df_dashboard['Total Venda']
                )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 3: POR CNPJ
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[2]:
        st.header("🏢 Resultado por CNPJ")
        
        df_cnpj = carregar_resultado_cnpj()
        
        if df_cnpj.empty:
            st.warning("⚠️ Nenhum dado encontrado na aba 'Resultado_CNPJ'")
        else:
            # Formata para exibição
            df_display = df_cnpj.copy()
            
            colunas_monetarias = ['Total Venda', 'Lucro Bruto', 'Custo Total', 'Impostos']
            for col in colunas_monetarias:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(format_currency_br)
            
            if 'Margem' in df_display.columns or 'Margem (%)' in df_display.columns:
                col_margem = 'Margem (%)' if 'Margem (%)' in df_display.columns else 'Margem'
                df_display[col_margem] = df_display[col_margem].apply(format_percent_br)
            
            st.dataframe(df_display, use_container_width=True)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 4: BCG POR CANAL
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[3]:
        st.header("📈 Matriz BCG por Canal")
        
        df_bcg = carregar_bcg_canal()
        
        if df_bcg.empty:
            st.warning("⚠️ Nenhum dado encontrado na aba 'BCG_Canal_Mkt'")
        else:
            # Formata para exibição
            df_display = df_bcg.copy()
            
            colunas_monetarias = ['Total Venda', 'Lucro Bruto']
            for col in colunas_monetarias:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(format_currency_br)
            
            if 'Margem' in df_display.columns or 'Margem (%)' in df_display.columns:
                col_margem = 'Margem (%)' if 'Margem (%)' in df_display.columns else 'Margem'
                df_display[col_margem] = df_display[col_margem].apply(format_percent_br)
            
            st.dataframe(df_display, use_container_width=True)
            
            # Se existir coluna de Classificação BCG, agrupa
            if 'Classificação' in df_bcg.columns or 'BCG' in df_bcg.columns:
                col_bcg = 'Classificação' if 'Classificação' in df_bcg.columns else 'BCG'
                
                st.subheader("📊 Distribuição BCG")
                
                bcg_counts = df_bcg[col_bcg].value_counts()
                st.bar_chart(bcg_counts)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 5: PREÇOS MKTP
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[4]:
        st.header("💰 Preços por Marketplace")
        
        df_precos = carregar_precos_mktp()
        
        if df_precos.empty:
            st.warning("⚠️ Nenhum dado encontrado na aba 'Preço_Simples_MKTP'")
        else:
            # Formata para exibição
            df_display = df_precos.copy()
            
            colunas_monetarias = ['Preço', 'Valor', 'Custo']
            for col in colunas_monetarias:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(format_currency_br)
            
            st.dataframe(df_display, use_container_width=True)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 6: GIRO SKU
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[5]:
        st.header("🔄 Giro de Produtos (SKU)")
        
        df_giro = carregar_vendas_sku()
        
        if df_giro.empty:
            st.warning("⚠️ Nenhum dado encontrado na aba 'Vendas_sku_geral'")
        else:
            # Ordena por quantidade vendida
            if 'Quantidade' in df_giro.columns:
                df_giro = df_giro.sort_values('Quantidade', ascending=False)
            
            # Top 20
            st.subheader("🏆 Top 20 Produtos Mais Vendidos")
            df_top20 = df_giro.head(20).copy()
            
            # Formata para exibição
            colunas_monetarias = ['Total Venda', 'Lucro Bruto']
            for col in colunas_monetarias:
                if col in df_top20.columns:
                    df_top20[col] = df_top20[col].apply(format_currency_br)
            
            st.dataframe(df_top20, use_container_width=True)
            
            # Gráfico
            if 'Produto' in df_top20.columns and 'Quantidade' in df_giro.columns:
                st.bar_chart(df_top20.set_index('Produto')['Quantidade'])
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ABA 7: OPORTUNIDADES
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tabs[6]:
        st.header("💡 Oportunidades de Melhoria")
        
        df_oportunidades = carregar_oportunidades()
        
        if df_oportunidades.empty:
            st.warning("⚠️ Nenhum dado encontrado na aba 'Oportunidades_canais_mkt'")
        else:
            st.info("💡 Produtos com classificação 'Interrogação ❓' são oportunidades para promoção")
            
            # Formata para exibição
            df_display = df_oportunidades.copy()
            
            colunas_monetarias = ['Total Venda', 'Lucro Bruto', 'Preço']
            for col in colunas_monetarias:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(format_currency_br)
            
            if 'Margem' in df_display.columns or 'Margem (%)' in df_display.columns:
                col_margem = 'Margem (%)' if 'Margem (%)' in df_display.columns else 'Margem'
                df_display[col_margem] = df_display[col_margem].apply(format_percent_br)
            
            st.dataframe(df_display, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# EXECUÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()

"""
═══════════════════════════════════════════════════════════════════════════════
    ✅ CÓDIGO V55 COMPLETO - PRONTO PARA USAR!
═══════════════════════════════════════════════════════════════════════════════
