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
from modules.sheets_reader import SheetsReader

# ==============================================================================
# VERSÃO V56 - INTEGRAÇÃO COM GESTÃO DE ESTOQUE
# ==============================================================================
# 1. Adiciona integração com planilha template_estoque
# 2. Nova aba "Gestão de Estoque" com análise de ruptura
# 3. Detecta produtos faltantes (BCG → template_estoque)
# 4. Exporta Excel formatado para upload manual
# 5. Normalização automática de separadores decimais
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DE GOOGLE SHEETS
# ==============================================================================
SPREADSHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"

# Mapeamento: tipo → (GID, Nome da Aba)
SHEET_MAPPING = {
    'produtos': (1037607798, 'Produtos'),
    'kits': (1569485799, 'Kits'),
    'custos_pedido': (1720329296, 'Custos por Pedido'),
    'canais': (1639432432, 'Canais'),
    'impostos': (260097325, 'Impostos'),
    'frete': (1928835495, 'Frete'),
    'metas': (1477190272, 'Metas'),
    'dashboard': (749174572, '1. Dashboard Geral'),
    'detalhes': (961459380, '6. Detalhes'),
    'cnpj': (1218055125, '2. Análise por CNPJ'),
    'executiva': (175434857, '3. Análise Executiva'),
    'precos': (1141986740, '4. Preços Marketplaces'),
    'bcg': (1589145111, '5. Matriz BCG'),
    'giro': (364031804, '7. Giro de Produtos'),
    'oportunidades': (563501913, '8. Oportunidades')
}

# URLs para fallback CSV (mantido para compatibilidade)
URLS = {k: f"{BASE_URL}&gid={v[0]}" for k, v in SHEET_MAPPING.items()}

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
# INICIALIZAÇÃO DO LEITOR DE SHEETS
# ==============================================================================
@st.cache_resource
def get_sheets_reader():
    """Inicializa o leitor de Google Sheets (cached)"""
    return SheetsReader(SPREADSHEET_ID)

# ==============================================================================
# FUNÇÃO DE CARREGAMENTO DE DADOS (CACHEADA)
# ==============================================================================
@st.cache_data(ttl=300)
def carregar_dados(tipo):
    """
    Carrega dados de uma aba do Google Sheets
    Tenta usar Google Sheets API primeiro, cai de volta para CSV export
    """
    if tipo not in SHEET_MAPPING:
        return pd.DataFrame()
    
    gid, sheet_name = SHEET_MAPPING[tipo]
    
    try:
        # Usa o leitor inteligente
        reader = get_sheets_reader()
        df = reader.read_sheet_by_gid(gid, sheet_name)
        
        if df.empty:
            return df
        
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

# Mostra status do leitor
try:
    reader = get_sheets_reader()
    status = reader.get_status()
    
    if status['realtime']:
        st.sidebar.success(f"**{status['method']}**")
        st.sidebar.info("✅ Dados em tempo real das abas originais")
    else:
        st.sidebar.warning(f"**{status['method']}**")
        st.sidebar.warning("⚠️ Algumas abas podem não funcionar (fórmulas complexas)")
        st.sidebar.info("💡 Configure Google Sheets API para acesso completo")
except Exception as e:
    st.sidebar.error(f"❌ Erro: {e}")

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
    "💲 Preços", "📝 Detalhes", "🔄 Giro de Produtos", "🚀 Oportunidades", "📦 Gestão de Estoque"
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

# 9. GESTÃO DE ESTOQUE (NOVA)
with tabs[8]:
    st.subheader("📦 Gestão de Estoque")
    
    # Importar módulos (import local para evitar erro se módulos não existirem)
    try:
        from modules.inventory_integration import InventoryIntegration
        from modules.rupture_analysis import RuptureAnalysis
        
        # Inicializar integração
        inv_integration = InventoryIntegration()
    except ImportError as e:
        st.error(f"❌ Erro ao importar módulos de gestão de estoque: {e}")
        st.info("💡 Aguarde alguns minutos para o Streamlit atualizar os arquivos do GitHub.")
        st.stop()
    
    # Carregar dados de estoque
    with st.spinner("Carregando dados de estoque..."):
        df_estoque = inv_integration.carregar_estoque()
    
    if df_estoque.empty:
        st.error("❌ Não foi possível carregar dados de estoque da planilha template_estoque")
    else:
        # ==============================================================
        # SEÇÃO 1: ESTATÍSTICAS GERAIS
        # ==============================================================
        st.markdown("### 📊 Visão Geral do Estoque")
        
        stats = inv_integration.calcular_estatisticas_estoque(df_estoque)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Produtos", stats.get('total_produtos', 0))
        col2.metric("Com Estoque", stats.get('produtos_com_estoque', 0), 
                   delta=f"-{stats.get('produtos_sem_estoque', 0)} sem estoque",
                   delta_color="inverse")
        col3.metric("Abaixo do Mínimo", stats.get('produtos_abaixo_minimo', 0))
        col4.metric("Valor em Estoque", format_currency_br(stats.get('valor_total_estoque', 0)))
        
        st.divider()
        
        # ==============================================================
        # SEÇÃO 2: ANÁLISE DE RUPTURA
        # ==============================================================
        st.markdown("### ⚠️ Análise de Ruptura")
        
        # Carregar dados de vendas para análise
        df_detalhes_vendas = carregar_dados('detalhes')
        
        if not df_detalhes_vendas.empty:
            # Inicializar análise de ruptura
            ruptura_analysis = RuptureAnalysis(df_detalhes_vendas, df_estoque)
            
            # Calcular cobertura
            df_cobertura = ruptura_analysis.calcular_cobertura()
            
            if not df_cobertura.empty:
                # Resumo executivo
                resumo = ruptura_analysis.gerar_resumo_executivo()
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("🔴 Críticos", resumo.get('criticos', 0), 
                           help="Produtos com menos de 3 dias de estoque")
                col2.metric("🟡 Atenção", resumo.get('atencao', 0),
                           help="Produtos com 3-7 dias de estoque")
                col3.metric("🟢 OK", resumo.get('ok', 0),
                           help="Produtos com mais de 7 dias de estoque")
                col4.metric("⚪ Sem Vendas", resumo.get('sem_vendas', 0),
                           help="Produtos sem vendas no período")
                
                # Tabela de cobertura
                st.markdown("#### 📋 Dias de Cobertura por Produto")
                
                # Filtros
                filtro_alerta = st.multiselect(
                    "Filtrar por status:",
                    options=['🔴 Crítico', '🟡 Atenção', '🟢 OK', '⚪ Sem Vendas'],
                    default=['🔴 Crítico', '🟡 Atenção']
                )
                
                df_filtrado = df_cobertura[df_cobertura['alerta'].isin(filtro_alerta)]
                
                # Selecionar colunas relevantes para exibição
                colunas_exibir = [
                    'codigo', 'nome', 'categoria', 'estoque_atual', 
                    'media_vendas_dia', 'dias_cobertura', 'alerta'
                ]
                colunas_disponiveis = [col for col in colunas_exibir if col in df_filtrado.columns]
                
                st.dataframe(
                    df_filtrado[colunas_disponiveis],
                    use_container_width=True,
                    height=400
                )
                
                # Projeção de ruptura
                st.markdown("#### 📅 Previsão de Rupturas (Próximos 30 dias)")
                df_ruptura = ruptura_analysis.projetar_ruptura(dias_futuros=30)
                
                if not df_ruptura.empty:
                    st.warning(f"⚠️ {len(df_ruptura)} produtos com previsão de ruptura nos próximos 30 dias")
                    
                    colunas_ruptura = [
                        'codigo', 'nome', 'estoque_atual', 'dias_cobertura',
                        'data_ruptura_prevista', 'qtd_reposicao_sugerida', 'valor_reposicao'
                    ]
                    colunas_disp_ruptura = [col for col in colunas_ruptura if col in df_ruptura.columns]
                    
                    st.dataframe(
                        df_ruptura[colunas_disp_ruptura],
                        use_container_width=True
                    )
                    
                    if 'investimento_reposicao' in resumo:
                        st.info(f"💰 Investimento estimado para reposição: {format_currency_br(resumo['investimento_reposicao'])}")
                else:
                    st.success("✅ Nenhuma ruptura prevista nos próximos 30 dias!")
            else:
                st.info("📊 Não há dados de vendas suficientes para análise de ruptura")
        else:
            st.info("📊 Carregue dados de vendas na aba 'Detalhes' para habilitar análise de ruptura")
        
        st.divider()
        
        # ==============================================================
        # SEÇÃO 3: SINCRONIZAÇÃO DE PRODUTOS
        # ==============================================================
        st.markdown("### 🔄 Sincronização de Produtos")
        st.info("💡 Esta seção identifica produtos que existem na planilha BCG mas não estão cadastrados no estoque")
        
        # Carregar dados da BCG para comparação
        df_bcg_produtos = carregar_dados('bcg')
        
        # Tentar carregar da aba principal também
        if df_bcg_produtos.empty:
            # Tentar ler diretamente a aba de produtos
            try:
                url_produtos = f"{BASE_URL}&gid=1037607798"  # GID da aba de produtos
                r = requests.get(url_produtos, timeout=15)
                r.raise_for_status()
                df_bcg_produtos = pd.read_csv(StringIO(r.text))
            except:
                pass
        
        if not df_bcg_produtos.empty:
            # Detectar produtos faltantes
            df_faltantes = inv_integration.detectar_produtos_faltantes(df_bcg_produtos, df_estoque)
            
            if not df_faltantes.empty:
                st.warning(f"⚠️ {len(df_faltantes)} produtos encontrados na BCG mas não no estoque")
                
                # Mostrar produtos faltantes
                st.markdown("#### Produtos Faltantes")
                # Mostrar apenas colunas que existem
                cols_disponiveis = [col for col in df_faltantes.columns if col not in ['codigo_normalizado', 'ordem_alerta']]
                st.dataframe(df_faltantes[cols_disponiveis[:5]].head(20), 
                           use_container_width=True)
                
                # Gerar Excel para download
                st.markdown("#### 📥 Exportar para Upload Manual")
                st.write("""
                    Clique no botão abaixo para baixar um arquivo Excel com os produtos faltantes
                    no formato correto para upload na planilha template_estoque.
                    
                    ✅ Formato correto das colunas
                    ✅ Estoque inicial = 0
                    ✅ Custo importado da BCG
                    ✅ Pronto para copiar e colar
                """)
                
                excel_file = inv_integration.gerar_excel_para_upload(df_faltantes)
                
                if excel_file:
                    st.download_button(
                        label="📥 Baixar Excel de Produtos Faltantes",
                        data=excel_file,
                        file_name=f"produtos_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="Baixe este arquivo e faça upload manual na planilha template_estoque"
                    )
            else:
                st.success("✅ Todos os produtos da BCG estão cadastrados no estoque!")
        else:
            st.info("📊 Carregue dados da BCG para habilitar sincronização")
        
        st.divider()
        
        # ==============================================================
        # SEÇÃO 4: VISUALIZAÇÃO COMPLETA DO ESTOQUE
        # ==============================================================
        st.markdown("### 📋 Estoque Completo")
        
        # Filtros
        col1, col2 = st.columns(2)
        
        with col1:
            if 'categoria' in df_estoque.columns:
                categorias_selecionadas = st.multiselect(
                    "Filtrar por categoria:",
                    options=df_estoque['categoria'].unique(),
                    default=df_estoque['categoria'].unique()
                )
        
        with col2:
            filtro_estoque = st.radio(
                "Filtrar estoque:",
                options=["Todos", "Com estoque", "Sem estoque", "Abaixo do mínimo"],
                horizontal=True
            )
        
        # Aplicar filtros
        df_estoque_filtrado = df_estoque.copy()
        
        if 'categoria' in df_estoque.columns and categorias_selecionadas:
            df_estoque_filtrado = df_estoque_filtrado[
                df_estoque_filtrado['categoria'].isin(categorias_selecionadas)
            ]
        
        if filtro_estoque == "Com estoque":
            df_estoque_filtrado = df_estoque_filtrado[df_estoque_filtrado['estoque_atual'] > 0]
        elif filtro_estoque == "Sem estoque":
            df_estoque_filtrado = df_estoque_filtrado[df_estoque_filtrado['estoque_atual'] == 0]
        elif filtro_estoque == "Abaixo do mínimo":
            if 'estoque_min' in df_estoque_filtrado.columns:
                df_estoque_filtrado = df_estoque_filtrado[
                    df_estoque_filtrado['estoque_atual'] < df_estoque_filtrado['estoque_min']
                ]
        
        # Exibir tabela
        st.dataframe(
            df_estoque_filtrado,
            use_container_width=True,
            height=500
        )
        
        st.caption(f"📊 Exibindo {len(df_estoque_filtrado)} de {len(df_estoque)} produtos")
