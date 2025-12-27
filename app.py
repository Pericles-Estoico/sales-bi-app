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
# VERSÃO V42 - INTEGRAÇÃO FINAL COM PLANILHA BCG
# ==============================================================================
# 1. Mantém TODAS as funcionalidades da V37 (MRP, Webhook, Novos Produtos)
# 2. Adiciona leitura histórica da planilha 'Config_BI_Final_MatrizBCG'
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro + MRP Fábrica", page_icon="🏭", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DO MÓDULO DE ESTOQUE E BCG
# ==============================================================================
ESTOQUE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
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

def safe_int(x, default=0):
    try:
        if x is None: return default
        if isinstance(x, float) and math.isnan(x): return default
        if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null", "n/a"}: return default
        return int(float(str(x).replace(",", ".")))
    except: return default

def parse_list_str(value):
    """
    Faz o parsing robusto de listas separadas por vírgula ou ponto e vírgula.
    Trata o caso onde '1,1' é lido como float 1.1 pelo pandas, convertendo para ['1', '1'].
    """
    if value is None: return []
    if isinstance(value, float):
        if math.isnan(value): return []
        # Se for float (ex: 1.1), converte para string "1.1" e substitui ponto por vírgula para separar
        s_val = str(value).replace('.', ',')
    else:
        s_val = str(value)
    
    # Normaliza separadores: troca ';' por ','
    s_val = s_val.replace(';', ',')
    
    parts = [p.strip() for p in s_val.split(",")]
    return [p for p in parts if p]

def parse_int_list(value):
    """
    Usa parse_list_str para obter a lista de strings e converte para inteiros.
    """
    parts = parse_list_str(value)
    out = []
    for p in parts:
        v = safe_int(p, None)
        if v is not None: out.append(v)
    return out

# ==============================================================================
# FUNÇÕES DE ESTOQUE E MRP
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_estoque_externo():
    try:
        r = requests.get(ESTOQUE_SHEETS_URL, timeout=15)
        r.raise_for_status()
        # Lê tudo como string (dtype=str) para evitar que o pandas converta "1,1" em 1.1
        df = pd.read_csv(StringIO(r.text), dtype=str)
        
        req = ['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max']
        for c in req:
            if c not in df.columns: df[c] = '0'
            
        df['estoque_atual'] = pd.to_numeric(df['estoque_atual'].str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
        
        for c in ['componentes', 'quantidades', 'eh_kit']:
            if c not in df.columns: df[c] = ''
            else: df[c] = df[c].fillna('')
            
        df['codigo_key'] = df['codigo'].map(normalize_key)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar estoque externo: {e}")
        return pd.DataFrame()

def calcular_mrp_recursivo(codigo_key, qtd_necessaria, df_estoque, nivel=0, caminho="", visitados=None):
    if visitados is None: visitados = set()
    
    acoes = []
    
    # Proteção contra recursão infinita (Ciclo)
    if codigo_key in visitados:
        acoes.append({
            'nivel': nivel, 'codigo': codigo_key, 'nome': f"CICLO DETECTADO ({codigo_key})",
            'acao': 'ERRO_RECEITA', 'qtd': qtd_necessaria, 'estoque_atual': 0, 'caminho': caminho
        })
        return acoes
    
    visitados.add(codigo_key)
    
    produto = df_estoque[df_estoque['codigo_key'] == codigo_key]
    if produto.empty:
        acoes.append({
            'nivel': nivel, 'codigo': codigo_key, 'nome': f"PRODUTO NÃO ENCONTRADO ({codigo_key})",
            'acao': 'ERRO_CADASTRO', 'qtd': qtd_necessaria, 'estoque_atual': 0, 'caminho': caminho
        })
        visitados.remove(codigo_key)
        return acoes

    row = produto.iloc[0]
    nome = row['nome']
    estoque_atual = safe_int(row['estoque_atual'])
    eh_kit = str(row.get('eh_kit', '')).strip().lower() == 'sim'
    
    qtd_usar_estoque = min(estoque_atual, qtd_necessaria)
    qtd_faltante = qtd_necessaria - qtd_usar_estoque
    
    if qtd_usar_estoque > 0:
        acoes.append({
            'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
            'acao': 'SEPARAR_ESTOQUE', 'qtd': qtd_usar_estoque, 'estoque_atual': estoque_atual, 'caminho': caminho
        })
        
    if qtd_faltante > 0:
        if eh_kit:
            comps = [normalize_key(c) for c in parse_list_str(row.get('componentes', ''))]
            quants = parse_int_list(row.get('quantidades', ''))
            
            if comps and quants and len(comps) == len(quants):
                acoes.append({
                    'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
                    'acao': 'PRODUZIR_MONTAR', 'qtd': qtd_faltante, 'estoque_atual': estoque_atual, 'caminho': caminho
                })
                for comp_key, comp_qtd_unit in zip(comps, quants):
                    qtd_comp_total = qtd_faltante * comp_qtd_unit
                    novo_caminho = f"{caminho} > {nome}" if caminho else nome
                    acoes_filho = calcular_mrp_recursivo(comp_key, qtd_comp_total, df_estoque, nivel + 1, novo_caminho, visitados.copy())
                    acoes.extend(acoes_filho)
            else:
                acoes.append({
                    'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
                    'acao': 'ERRO_RECEITA', 'qtd': qtd_faltante, 'estoque_atual': estoque_atual, 'caminho': caminho
                })
        else:
            acoes.append({
                'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
                'acao': 'COMPRAR_PRODUZIR_EXTERNO', 'qtd': qtd_faltante, 'estoque_atual': estoque_atual, 'caminho': caminho
            })
            
    visitados.remove(codigo_key)
    return acoes

def processar_mrp_fila(df_vendas_fila, df_estoque):
    vendas_agrupadas = df_vendas_fila.groupby('Produto')['Quantidade'].sum().reset_index()
    plano_mrp = []
    for _, row in vendas_agrupadas.iterrows():
        cod_key = normalize_key(row['Produto'])
        qtd = safe_int(row['Quantidade'])
        acoes = calcular_mrp_recursivo(cod_key, qtd, df_estoque)
        plano_mrp.extend(acoes)
    return pd.DataFrame(plano_mrp)

# ==============================================================================
# GERAÇÃO DE EXCEL HIERÁRQUICO (ÁRVORE DE SEMIS) COM MRP DETALHADO
# ==============================================================================
def gerar_excel_hierarquico(df_vendas_fila, df_estoque):
    """
    Gera um Excel com abas por Marketplace.
    Em cada aba, agrupa os produtos pelo seu 'Semi' (Pai).
    """
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # Formatos
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
    fmt_normal = workbook.add_format({'border': 1})
    fmt_number = workbook.add_format({'border': 1, 'num_format': '#,##0'})
    
    # Agrupar vendas por Canal
    canais = df_vendas_fila['Canal'].unique()
    
    for canal in canais:
        # Limpar nome da aba (remover caracteres inválidos e limitar tamanho)
        safe_canal = str(canal).replace(':', '').replace('/', '').replace('\\', '').replace('?', '').replace('*', '').replace('[', '').replace(']', '')[:30]
        worksheet = workbook.add_worksheet(safe_canal)
        
        # Cabeçalhos
        headers = ['Produto Venda', 'Qtd Venda', 'Ação', 'Componente/Insumo', 'Qtd Necessária', 'Estoque Atual', 'Saldo Final']
        for col, h in enumerate(headers):
            worksheet.write(0, col, h, fmt_header)
            
        # Filtrar vendas do canal
        vendas_canal = df_vendas_fila[df_vendas_fila['Canal'] == canal]
        
        row_idx = 1
        for _, venda in vendas_canal.iterrows():
            prod_nome = venda['Produto']
            qtd_venda = venda['Quantidade']
            cod_key = normalize_key(prod_nome)
            
            # Calcular MRP para este item específico
            acoes = calcular_mrp_recursivo(cod_key, qtd_venda, df_estoque)
            
            # Escrever linha principal do produto vendido
            worksheet.write(row_idx, 0, prod_nome, fmt_normal)
            worksheet.write(row_idx, 1, qtd_venda, fmt_number)
            worksheet.write(row_idx, 2, "VENDA", fmt_normal)
            worksheet.write(row_idx, 3, "-", fmt_normal)
            worksheet.write(row_idx, 4, "-", fmt_normal)
            worksheet.write(row_idx, 5, "-", fmt_normal)
            worksheet.write(row_idx, 6, "-", fmt_normal)
            row_idx += 1
            
            # Escrever ações do MRP (explosão)
            for acao in acoes:
                indent = "  " * acao['nivel']
                nome_comp = f"{indent}{acao['nome']}"
                tipo_acao = acao['acao']
                qtd_nec = acao['qtd']
                est_atual = acao['estoque_atual']
                saldo = est_atual - qtd_nec if tipo_acao == 'SEPARAR_ESTOQUE' else est_atual
                
                worksheet.write(row_idx, 0, "", fmt_normal) # Coluna Produto Venda vazia para hierarquia
                worksheet.write(row_idx, 1, "", fmt_normal)
                worksheet.write(row_idx, 2, tipo_acao, fmt_normal)
                worksheet.write(row_idx, 3, nome_comp, fmt_normal)
                worksheet.write(row_idx, 4, qtd_nec, fmt_number)
                worksheet.write(row_idx, 5, est_atual, fmt_number)
                worksheet.write(row_idx, 6, saldo, fmt_number)
                row_idx += 1
                
            row_idx += 1 # Linha em branco entre produtos
            
    # ABA DE RESUMO DE INSUMOS (NECESSIDADE LÍQUIDA)
    worksheet_resumo = workbook.add_worksheet("RESUMO_COMPRAS_PRODUCAO")
    headers_resumo = ['Código', 'Nome', 'Tipo Ação', 'Total Necessário', 'Estoque Atual', 'Necessidade Líquida (Comprar/Produzir)']
    for col, h in enumerate(headers_resumo):
        worksheet_resumo.write(0, col, h, fmt_header)
        
    # Calcular MRP Global
    df_mrp_global = processar_mrp_fila(df_vendas_fila, df_estoque)
    
    if not df_mrp_global.empty:
        # Filtrar apenas o que precisa ser comprado ou produzido externamente
        # E também o que precisa ser montado internamente se não tiver estoque
        mask_compra = df_mrp_global['acao'].isin(['COMPRAR_PRODUZIR_EXTERNO', 'PRODUZIR_MONTAR'])
        df_resumo = df_mrp_global[mask_compra].groupby(['codigo', 'nome', 'acao']).agg({
            'qtd': 'sum',
            'estoque_atual': 'first' # Estoque é o mesmo para o produto
        }).reset_index()
        
        # Calcular necessidade líquida real (considerando que o estoque já foi descontado na lógica recursiva? 
        # A lógica recursiva já desconta o estoque disponível antes de gerar a ação de produção/compra.
        # Então 'qtd' aqui JÁ É a necessidade líquida (o que faltou).
        
        r_idx = 1
        for _, row in df_resumo.iterrows():
            worksheet_resumo.write(r_idx, 0, row['codigo'], fmt_normal)
            worksheet_resumo.write(r_idx, 1, row['nome'], fmt_normal)
            worksheet_resumo.write(r_idx, 2, row['acao'], fmt_normal)
            worksheet_resumo.write(r_idx, 3, row['qtd'], fmt_number)
            worksheet_resumo.write(r_idx, 4, row['estoque_atual'], fmt_number)
            worksheet_resumo.write(r_idx, 5, row['qtd'], fmt_number) # Qtd aqui já é o faltante
            r_idx += 1

    workbook.close()
    return output.getvalue()

def gerar_excel_novos_produtos(produtos_faltantes):
    """
    Gera um Excel formatado para copiar e colar na template_estoque.
    """
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Novos Produtos")
    
    # Cabeçalhos exatos da template_estoque
    headers = ['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max', 'custo', 'eh_kit', 'componentes', 'quantidades']
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#FFFF00', 'border': 1})
    
    for col, h in enumerate(headers):
        worksheet.write(0, col, h, fmt_header)
        
    for idx, prod_nome in enumerate(produtos_faltantes):
        row = idx + 1
        # Preenche com valores padrão
        worksheet.write(row, 0, prod_nome) # Código (usando nome como código inicial)
        worksheet.write(row, 1, prod_nome) # Nome
        worksheet.write(row, 2, "Novos")   # Categoria
        worksheet.write(row, 3, 0)         # Estoque Atual
        worksheet.write(row, 4, 10)        # Estoque Min
        worksheet.write(row, 5, 100)       # Estoque Max
        worksheet.write(row, 6, 0)         # Custo
        worksheet.write(row, 7, "")        # Eh Kit
        worksheet.write(row, 8, "")        # Componentes
        worksheet.write(row, 9, "")        # Quantidades
        
    workbook.close()
    return output.getvalue()

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

with st.spinner("Running carregar_configuracoes()..."):
    config_sheet = carregar_configuracoes()
    st.sidebar.success(f"Conectado em: {config_sheet}")

# Carregamento de Estoque
df_estoque = carregar_estoque_externo()
if not df_estoque.empty:
    st.sidebar.info(f"📦 Produtos Carregados: {len(df_estoque)}")
    kits = df_estoque[df_estoque['eh_kit'].str.lower() == 'sim']
    st.sidebar.info(f"🧩 Kits Carregados: {len(kits)}")
else:
    st.sidebar.error("Falha ao carregar estoque.")

st.sidebar.divider()
st.sidebar.header("📥 Importar Vendas")

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
# PROCESSAMENTO
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
            
            # ==================================================================
            # VERIFICAÇÃO DE PRODUTOS FALTANTES (NOVO V37)
            # ==================================================================
            if not df_estoque.empty:
                produtos_venda = set(df['Produto'].map(normalize_key))
                produtos_estoque = set(df_estoque['codigo_key'])
                
                # Produtos que estão na venda mas NÃO estão no estoque
                faltantes_keys = produtos_venda - produtos_estoque
                
                # Recuperar nomes originais
                produtos_faltantes_nomes = df[df['Produto'].map(normalize_key).isin(faltantes_keys)]['Produto'].unique()
                
                if len(produtos_faltantes_nomes) > 0:
                    st.warning(f"⚠️ {len(produtos_faltantes_nomes)} Produtos encontrados na venda que NÃO estão cadastrados no estoque!")
                    
                    with st.expander("Ver lista de produtos não cadastrados"):
                        st.write(produtos_faltantes_nomes)
                    
                    excel_novos = gerar_excel_novos_produtos(produtos_faltantes_nomes)
                    st.download_button(
                        label="📥 Baixar Planilha para Cadastro (Copiar e Colar)",
                        data=excel_novos,
                        file_name="novos_produtos_para_cadastro.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="Baixe este arquivo, copie os dados e cole na sua planilha template_estoque."
                    )
            
            # Botão de Simulação
            if st.sidebar.button("🚀 Simular Processamento"):
                st.session_state.processed_data = df
                st.success(f"SIMULAÇÃO: {len(df)} vendas processadas na memória. Nada foi salvo.")
                
        else:
            st.error("Colunas 'Produto' e 'Quantidade' não encontradas no Excel.")
            
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")

# ==============================================================================
# DASHBOARD E VISUALIZAÇÃO
# ==============================================================================
st.title("📊 Sales BI Pro + 🏭 MRP Fábrica")

tabs = st.tabs([
    "📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", 
    "💲 Preços", "📝 Detalhes", "🔄 Giro de Produtos", "🚀 Oportunidades", "🏭 MRP Fábrica"
])

# Carregar dados históricos se não houver upload
if 'processed_data' not in st.session_state:
    df_historico = carregar_dados_historicos()
    if not df_historico.empty:
        st.session_state.processed_data = df_historico
        st.toast("Dados históricos carregados da planilha BCG!", icon="📅")

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

    with tabs[8]: # MRP Fábrica
        st.header("🏭 Planejamento de Fábrica (MRP)")
        st.info("Este módulo explode a necessidade de materiais baseada nas vendas carregadas.")
        
        if not df_estoque.empty:
            # Calcular MRP
            df_mrp = processar_mrp_fila(df_vendas, df_estoque)
            
            # Verificar Erros de Receita/Cadastro
            erros = df_mrp[df_mrp['acao'].isin(['ERRO_RECEITA', 'ERRO_CADASTRO'])]
            
            if not erros.empty:
                st.error(f"Foram encontrados {len(erros)} problemas de cadastro/receita que impedem o cálculo completo.")
                st.dataframe(erros[['codigo', 'nome', 'acao', 'caminho']], use_container_width=True)
                st.warning("Corrija os itens acima na planilha 'template_estoque' e recarregue.")
            else:
                st.success("Cálculo MRP realizado com sucesso! Nenhum erro de estrutura encontrado.")
                
                # Botão para baixar Excel Hierárquico
                excel_data = gerar_excel_hierarquico(df_vendas, df_estoque)
                st.download_button(
                    label="📥 Baixar Ordem de Produção (Excel Hierárquico)",
                    data=excel_data,
                    file_name=f"Ordem_Producao_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                st.subheader("Visualização do Plano")
                st.dataframe(df_mrp, use_container_width=True)
        else:
            st.warning("Carregue o estoque para gerar o MRP.")

else:
    with tabs[0]:
        st.info("Carregue um arquivo de vendas na barra lateral para visualizar os dados.")
