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
# VERSÃO V36 - CORREÇÃO DE PARSING DE LISTAS E RECURSÃO INFINITA
# ==============================================================================
# 1. Correção do parsing de 'quantidades' (1,1 lido como texto "1,1" e não float 1.1)
# 2. Proteção contra recursão infinita (Kit contendo a si mesmo)
# 3. Suporte a separadores ',' e ';'
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro + MRP Fábrica", page_icon="🏭", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DO MÓDULO DE ESTOQUE
# ==============================================================================
ESTOQUE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
ESTOQUE_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxTX9uUWnByw6sk6MtuJ5FbjV7zeBKYEoUPPlUlUDS738QqocfCd_NAlh9Eh25XhQywTw/exec"

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
                    # Passa uma cópia de visitados para o próximo nível, ou remove após retorno?
                    # Melhor passar o set atualizado para a recursão
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
    Mostra estoque atual e necessidade líquida (O que falta produzir/comprar).
    """
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # Formatos
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
    fmt_pai = workbook.add_format({'bold': True, 'bg_color': '#EFEFEF', 'border': 1})
    fmt_pai_alerta = workbook.add_format({'bold': True, 'bg_color': '#F4CCCC', 'border': 1, 'font_color': '#990000'})
    fmt_filho = workbook.add_format({'indent': 2, 'border': 1})
    fmt_filho_alerta = workbook.add_format({'indent': 2, 'border': 1, 'bg_color': '#FFF2CC', 'font_color': '#B45F06'})
    fmt_check = workbook.add_format({'border': 1})
    fmt_num = workbook.add_format({'border': 1, 'align': 'center'})
    
    # 1. Identificar o "Semi" de cada produto vendido e mapear componentes
    mapa_produto_semi = {}
    mapa_produto_insumos = {} # { 'prod_key': [ {'nome': 'Gola', 'qtd': 1}, ... ] }
    
    for _, row in df_estoque.iterrows():
        if str(row.get('eh_kit', '')).lower() == 'sim':
            comps_cods = [normalize_key(c) for c in parse_list_str(row.get('componentes', ''))]
            quants = parse_int_list(row.get('quantidades', ''))
            
            # Mapear Insumos (Componentes além do Semi)
            insumos_desc = []
            semi_cod = None
            
            if comps_cods:
                semi_cod = comps_cods[0] # Assumindo que o Semi é o primeiro
                
                # Busca o nome do Semi
                semi_row = df_estoque[df_estoque['codigo_key'] == semi_cod]
                if not semi_row.empty:
                    mapa_produto_semi[row['codigo_key']] = {'nome': semi_row.iloc[0]['nome'], 'key': semi_cod}
                else:
                    mapa_produto_semi[row['codigo_key']] = {'nome': f"Base ({semi_cod})", 'key': semi_cod}
                
                # Outros componentes são insumos (Golas, Bordados, etc)
                if len(comps_cods) > 1 and len(quants) == len(comps_cods):
                    for i in range(1, len(comps_cods)):
                        ins_cod = comps_cods[i]
                        ins_qtd = quants[i]
                        ins_row = df_estoque[df_estoque['codigo_key'] == ins_cod]
                        ins_nome = ins_row.iloc[0]['nome'] if not ins_row.empty else ins_cod
                        insumos_desc.append(f"{ins_qtd}x {ins_nome}")
            
            mapa_produto_insumos[row['codigo_key']] = ", ".join(insumos_desc)

    # 2. Agrupar vendas por Canal
    canais = df_vendas_fila['Canal'].unique()
    resumo_insumos_geral = {} # { 'Nome Insumo': qtd_total }
    
    for canal in canais:
        # Limpa nome da aba
        nome_aba = str(canal).replace('📊 ', '').replace('🛒 ', '').replace('🛍️ ', '').replace('🏪 ', '').replace('👗 ', '')
        for char in [':', '\\', '/', '?', '*', '[', ']']: nome_aba = nome_aba.replace(char, '-')
        nome_aba = nome_aba[:30]
        worksheet = workbook.add_worksheet(nome_aba)
        
        # Cabeçalhos
        headers = ["Item / Produto", "Venda", "Estoque", "A Produzir", "Insumos Necessários", "Check"]
        for col, h in enumerate(headers): worksheet.write(0, col, h, fmt_header)
        
        worksheet.set_column(0, 0, 50) # Item
        worksheet.set_column(1, 3, 10) # Números
        worksheet.set_column(4, 4, 40) # Insumos
        worksheet.set_column(5, 5, 8)  # Check
        
        vendas_canal = df_vendas_fila[df_vendas_fila['Canal'] == canal]
        
        # Agrupa por Semi
        arvore = {} 
        
        for _, row in vendas_canal.iterrows():
            prod_cod = str(row['Produto'])
            prod_key = normalize_key(prod_cod)
            qtd = row['Quantidade']
            
            prod_nome = prod_cod
            prod_row = df_estoque[df_estoque['codigo_key'] == prod_key]
            prod_estoque = 0
            if not prod_row.empty: 
                prod_nome = prod_row.iloc[0]['nome']
                prod_estoque = safe_int(prod_row.iloc[0]['estoque_atual'])
            
            semi_info = mapa_produto_semi.get(prod_key, {'nome': "Outros / Sem Base Definida", 'key': None})
            semi_nome = semi_info['nome']
            semi_key = semi_info['key']
            
            if semi_nome not in arvore: arvore[semi_nome] = {'key': semi_key, 'itens': []}
            
            insumos_txt = mapa_produto_insumos.get(prod_key, "")
            
            arvore[semi_nome]['itens'].append({
                'produto': prod_nome, 
                'qtd_venda': qtd,
                'estoque': prod_estoque,
                'insumos': insumos_txt,
                'key': prod_key
            })

        # Escreve na aba
        row_idx = 1
        for semi_nome, dados_semi in arvore.items():
            itens = dados_semi['itens']
            semi_key = dados_semi['key']
            
            # Calcula totais do Semi
            total_venda_semi = sum(item['qtd_venda'] for item in itens)
            
            # Busca estoque do Semi
            estoque_semi = 0
            if semi_key:
                s_row = df_estoque[df_estoque['codigo_key'] == semi_key]
                if not s_row.empty: estoque_semi = safe_int(s_row.iloc[0]['estoque_atual'])
            
            falta_semi = max(0, total_venda_semi - estoque_semi)
            
            # Formatação condicional para o Semi
            fmt_s = fmt_pai_alerta if falta_semi > 0 else fmt_pai
            msg_semi = f"CORTAR: {falta_semi}" if falta_semi > 0 else "OK"
            
            worksheet.write(row_idx, 0, f"{semi_nome}", fmt_s)
            worksheet.write(row_idx, 1, total_venda_semi, fmt_s)
            worksheet.write(row_idx, 2, estoque_semi, fmt_s)
            worksheet.write(row_idx, 3, msg_semi, fmt_s)
            worksheet.write(row_idx, 4, "", fmt_s)
            worksheet.write(row_idx, 5, "", fmt_s)
            row_idx += 1
            
            # Linhas dos Filhos
            for item in itens:
                qtd_venda = item['qtd_venda']
                estoque_prod = item['estoque']
                falta_prod = max(0, qtd_venda - estoque_prod)
                
                fmt_p = fmt_filho_alerta if falta_prod > 0 else fmt_filho
                msg_prod = f"MONTAR: {falta_prod}" if falta_prod > 0 else "OK"
                
                # Acumula insumos necessários para o Resumo Geral
                if falta_prod > 0 and item['insumos']:
                    partes = item['insumos'].split(', ')
                    for p in partes:
                        try:
                            qtd_ins_str, nome_ins = p.split('x ', 1)
                            qtd_total_ins = int(qtd_ins_str) * falta_prod
                            resumo_insumos_geral[nome_ins] = resumo_insumos_geral.get(nome_ins, 0) + qtd_total_ins
                        except: pass

                worksheet.write(row_idx, 0, f"  {item['produto']}", fmt_p)
                worksheet.write(row_idx, 1, qtd_venda, fmt_num)
                worksheet.write(row_idx, 2, estoque_prod, fmt_num)
                worksheet.write(row_idx, 3, msg_prod, fmt_num)
                worksheet.write(row_idx, 4, item['insumos'], fmt_p)
                worksheet.write(row_idx, 5, "[   ]", fmt_check)
                row_idx += 1
            
            row_idx += 1
            
    # 3. Aba de Resumo de Insumos
    if resumo_insumos_geral:
        ws_resumo = workbook.add_worksheet("RESUMO DE COMPRAS")
        ws_resumo.write(0, 0, "Insumo / Acabamento", fmt_header)
        ws_resumo.write(0, 1, "Qtd Total Necessária", fmt_header)
        ws_resumo.set_column(0, 0, 40)
        ws_resumo.set_column(1, 1, 20)
        
        r_idx = 1
        for insumo, qtd in sorted(resumo_insumos_geral.items()):
            ws_resumo.write(r_idx, 0, insumo, fmt_check)
            ws_resumo.write(r_idx, 1, qtd, fmt_num)
            r_idx += 1

    workbook.close()
    return output.getvalue()

# ==============================================================================
# CONEXÃO COM GOOGLE SHEETS
# ==============================================================================
@st.cache_resource
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    if "GOOGLE_SHEETS_CREDENTIALS" in st.secrets:
        creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        st.error("❌ Credenciais não encontradas no st.secrets.")
        st.stop()
    gc = gspread.authorize(creds)
    if "GOOGLE_SHEETS_URL" in st.secrets:
        ss = gc.open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
        return ss, gc
    else:
        st.error("❌ URL da planilha não encontrada.")
        st.stop()

@st.cache_data(ttl=60)
def carregar_dados_detalhes():
    try:
        ss, _ = conectar_google_sheets()
        ws = ss.worksheet("6. Detalhes")
        all_values = ws.get_all_values()
        if not all_values: return pd.DataFrame(columns=COLUNAS_ESPERADAS)
        
        header_idx = -1
        for i, row in enumerate(all_values[:5]):
            if 'Total Venda' in row and 'Lucro Bruto' in row and 'Produto' in row:
                header_idx = i
                break
        
        if header_idx == -1: return pd.DataFrame(columns=COLUNAS_ESPERADAS)
            
        df = pd.DataFrame(all_values[header_idx+1:], columns=all_values[header_idx])
        
        cols_money = ['Total Venda', 'Custo Total', 'Lucro Bruto', 'Investimento Ads', 'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas', 'Embalagem']
        for col in cols_money:
            if col in df.columns: df[col] = df[col].apply(clean_currency)
            
        if 'Margem (%)' in df.columns:
            df['Margem (%)'] = df['Margem (%)'].apply(clean_percent_read)
            
        if 'Quantidade' in df.columns:
            df['Quantidade'] = df['Quantidade'].apply(clean_float)
            
        return df
    except: return pd.DataFrame(columns=COLUNAS_ESPERADAS)

@st.cache_data(ttl=3600)
def carregar_configuracoes():
    try:
        ss, gc = conectar_google_sheets()
        configs_data = {}
        estoque_produtos = set()
        
        if "TEMPLATE_ESTOQUE_URL" in st.secrets:
            try:
                ss_estoque = gc.open_by_url(st.secrets["TEMPLATE_ESTOQUE_URL"])
                ws_estoque = ss_estoque.worksheet('template_estoque')
                df_estoque = pd.DataFrame(ws_estoque.get_all_records())
                if 'codigo' in df_estoque.columns:
                    estoque_produtos = set(df_estoque['codigo'].tolist())
            except: pass
        
        abas_config = [("Produtos", "produtos"), ("Kits", "kits"), ("Canais", "canais"), 
                       ("Custos por Pedido", "custos_ped"), ("Impostos", "impostos"), 
                       ("Frete", "frete"), ("Metas", "metas")]
        
        for nome_aba, chave in abas_config:
            try:
                sh = ss.worksheet(nome_aba)
                data = sh.get_all_values()
                if len(data) > 1:
                    cols = data[0]
                    counts = {}
                    new_cols = []
                    for col in cols:
                        if col in counts: counts[col] += 1; new_cols.append(f"{col}_{counts[col]}")
                        else: counts[col] = 0; new_cols.append(col)
                    
                    df = pd.DataFrame(data[1:], columns=new_cols)
                    for col in df.columns:
                        if any(x in col for x in ['R$', '%', 'Peso', 'Custo', 'Preço', 'Taxa', 'Frete', 'Valor']):
                            df[col] = df[col].apply(clean_currency)
                    configs_data[chave] = df
            except: pass
        return configs_data, estoque_produtos
    except: return None, None

# ==============================================================================
# LÓGICA DE NEGÓCIO (BI FINANCEIRO)
# ==============================================================================
def classificar_bcg(row, median_vendas, median_margem):
    vendas = row['Total Venda']
    margem = row['Margem (%)']
    if vendas >= median_vendas and margem >= median_margem: return 'Estrela ⭐'
    elif vendas >= median_vendas and margem < median_margem: return 'Vaca Leiteira 🐄'
    elif vendas < median_vendas and margem >= median_margem: return 'Interrogação ❓'
    else: return 'Abacaxi 🍍'

def obter_status_meta(margem, metas):
    try:
        minima = float(metas.get('Margem Líquida Mínima (%)', 10)) / 100
        ideal = float(metas.get('Margem Líquida Ideal (%)', 15)) / 100
        
        if margem >= ideal: return '🟢 Ideal'
        elif margem >= minima: return '🟡 Atenção'
        else: return '🔴 Crítico'
    except: return '⚪ N/A'

def processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads_total):
    df_novo = pd.DataFrame()
    if 'Código' in df_orig.columns and 'Quantidade' in df_orig.columns:
        df_novo['Data'] = [data_venda] * len(df_orig)
        df_novo['Produto'] = df_orig['Código']
        df_novo['Quantidade'] = pd.to_numeric(df_orig['Quantidade'], errors='coerce').fillna(0)
        
        if 'Valor' in df_orig.columns: df_novo['Total'] = df_orig['Valor'].apply(clean_currency)
        elif 'Preço' in df_orig.columns: df_novo['Total'] = df_orig['Preço'].apply(clean_currency) * df_novo['Quantidade']
        else: df_novo['Total'] = 0.0
        df_novo['Preço Unitário'] = df_novo['Total'] / df_novo['Quantidade']
    else:
        st.error("Colunas obrigatórias não encontradas: 'Código', 'Quantidade', 'Valor' (ou 'Preço').")
        return None, None

    df_novo['Canal'] = CHANNELS[canal]
    df_novo['CNPJ'] = cnpj_regime

    produtos_df = st.session_state.get('produtos', pd.DataFrame())
    kits_df = st.session_state.get('kits', pd.DataFrame())
    impostos_df = st.session_state.get('impostos', pd.DataFrame())
    canais_df = st.session_state.get('canais', pd.DataFrame())
    custos_ped_df = st.session_state.get('custos_ped', pd.DataFrame())

    produtos_map = {}
    if not produtos_df.empty and 'Código' in produtos_df.columns:
        for _, row in produtos_df.iterrows():
            produtos_map[normalizar(str(row['Código']))] = {'custo': float(row.get('Custo (R$)', 0))}

    kits_map = {}
    if not kits_df.empty and 'Código Kit' in kits_df.columns:
        for _, row in kits_df.iterrows():
            cod_kit = normalizar(str(row['Código Kit']))
            comps = str(row.get('SKUs Componentes', '')).split(';') if ';' in str(row.get('SKUs Componentes', '')) else [str(row.get('SKUs Componentes', ''))]
            qtds = str(row.get('Qtd Componentes', '')).split(';') if ';' in str(row.get('Qtd Componentes', '')) else [str(row.get('Qtd Componentes', ''))]
            if len(qtds) < len(comps): qtds = [1]*len(comps)
            kits_map[cod_kit] = [{'sku': c.strip(), 'qtd': clean_float(q)} for c, q in zip(comps, qtds)]

    aliquota = 0.06
    if not impostos_df.empty and 'Tipo' in impostos_df.columns:
        m = impostos_df[impostos_df['Tipo'].str.contains(cnpj_regime.split()[0], case=False, na=False)]
        if not m.empty: aliquota = float(m.iloc[0]['Alíquota (%)']) / 100

    taxa_mp, taxa_fixa = 0.16, 5.0
    if not canais_df.empty and 'Canal' in canais_df.columns:
        m = canais_df[canais_df['Canal'].str.contains(canal.replace('_', ' '), case=False, na=False)]
        if not m.empty:
            taxa_mp = float(m.iloc[0].get('Taxa Marketplace (%)', 16)) / 100
            taxa_fixa = float(m.iloc[0].get('Taxa Fixa Pedido (R$)', 5))

    custo_emb = 0.0
    if not custos_ped_df.empty and 'Custo Unitário (R$)' in custos_ped_df.columns:
        custo_emb = custos_ped_df['Custo Unitário (R$)'].sum()

    resultados = []
    faltantes = []
    total_vendas_dia = df_novo['Total'].sum()

    for _, row in df_novo.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd = row['Quantidade']
        total_venda = row['Total']
        
        custo_produto = 0.0
        tipo = 'Produto'
        encontrado = False
        erro_motivo = ""
        
        if prod_norm in kits_map:
            tipo = 'Kit'
            encontrado = True
            for comp in kits_map[prod_norm]:
                c_norm = normalizar(comp['sku'])
                if c_norm in produtos_map:
                    c_custo = produtos_map[c_norm]['custo']
                    if c_custo <= 0:
                        encontrado = False
                        erro_motivo = f"Componente {comp['sku']} com Custo Zero"
                        break
                    custo_produto += c_custo * comp['qtd']
                else:
                    encontrado = False
                    erro_motivo = f"Componente {comp['sku']} não cadastrado"
                    break
        elif prod_norm in produtos_map:
            custo_produto = produtos_map[prod_norm]['custo']
            if custo_produto > 0:
                encontrado = True
            else:
                erro_motivo = "Custo Zero no Cadastro"
        else:
            erro_motivo = "Produto não cadastrado"
        
        if not encontrado:
            faltantes.append({'Código': prod_cod, 'Motivo': erro_motivo})
            continue

        custo_total_prod = custo_produto * qtd
        imposto_val = total_venda * aliquota
        comissao_val = total_venda * taxa_mp
        taxa_fixa_val = taxa_fixa * qtd
        ads_rateio = (total_venda / total_vendas_dia) * custo_ads_total if total_vendas_dia > 0 else 0.0
        
        custo_total_geral = custo_total_prod + imposto_val + comissao_val + taxa_fixa_val + (custo_emb * qtd) + ads_rateio
        lucro = total_venda - custo_total_geral
        margem = (lucro / total_venda) if total_venda > 0 else 0.0
        
        resultados.append({
            'Data': row['Data'], 'Canal': row['Canal'], 'CNPJ': row['CNPJ'],
            'Produto': prod_cod, 'Tipo': tipo, 'Quantidade': qtd, 'Total Venda': total_venda,
            'Custo Produto': custo_total_prod, 'Impostos': imposto_val, 'Comissão': comissao_val,
            'Taxas Fixas': taxa_fixa_val, 'Embalagem': custo_emb * qtd, 'Investimento Ads': ads_rateio,
            'Custo Total': custo_total_geral, 'Lucro Bruto': lucro, 'Margem (%)': margem
        })
        
    return pd.DataFrame(resultados), pd.DataFrame(faltantes)

def calcular_giro_produtos(df_detalhes):
    kits_df = st.session_state.get('kits', pd.DataFrame())
    kits_map = {}
    if not kits_df.empty and 'Código Kit' in kits_df.columns:
        for _, row in kits_df.iterrows():
            cod_kit = normalizar(str(row['Código Kit']))
            comps = str(row.get('SKUs Componentes', '')).split(';') if ';' in str(row.get('SKUs Componentes', '')) else [str(row.get('SKUs Componentes', ''))]
            qtds = str(row.get('Qtd Componentes', '')).split(';') if ';' in str(row.get('Qtd Componentes', '')) else [str(row.get('Qtd Componentes', ''))]
            if len(qtds) < len(comps): qtds = [1]*len(comps)
            kits_map[cod_kit] = [{'sku': c.strip(), 'qtd': clean_float(q)} for c, q in zip(comps, qtds)]

    giro_real = []
    
    for _, row in df_detalhes.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd_venda = row['Quantidade']
        
        if prod_norm in kits_map:
            for comp in kits_map[prod_norm]:
                giro_real.append({
                    'SKU Real': comp['sku'],
                    'Qtd Vendida': qtd_venda * comp['qtd'],
                    'Origem': 'Kit'
                })
        else:
            giro_real.append({
                'SKU Real': prod_cod,
                'Qtd Vendida': qtd_venda,
                'Origem': 'Avulso'
            })
            
    if not giro_real: return pd.DataFrame()
    
    df_giro = pd.DataFrame(giro_real)
    df_agrupado = df_giro.groupby('SKU Real')['Qtd Vendida'].sum().reset_index()
    df_agrupado = df_agrupado.sort_values('Qtd Vendida', ascending=False)
    
    return df_agrupado

def calcular_oportunidades(df_detalhes):
    kits_df = st.session_state.get('kits', pd.DataFrame())
    kits_map = {}
    if not kits_df.empty and 'Código Kit' in kits_df.columns:
        for _, row in kits_df.iterrows():
            cod_kit = normalizar(str(row['Código Kit']))
            comps = str(row.get('SKUs Componentes', '')).split(';') if ';' in str(row.get('SKUs Componentes', '')) else [str(row.get('SKUs Componentes', ''))]
            qtds = str(row.get('Qtd Componentes', '')).split(';') if ';' in str(row.get('Qtd Componentes', '')) else [str(row.get('Qtd Componentes', ''))]
            if len(qtds) < len(comps): qtds = [1]*len(comps)
            kits_map[cod_kit] = [{'sku': c.strip(), 'qtd': clean_float(q)} for c, q in zip(comps, qtds)]

    giro_canal = []
    
    for _, row in df_detalhes.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd_venda = row['Quantidade']
        canal = row['Canal']
        
        if prod_norm in kits_map:
            for comp in kits_map[prod_norm]:
                giro_canal.append({
                    'SKU Real': comp['sku'],
                    'Canal': canal,
                    'Qtd Vendida': qtd_venda * comp['qtd']
                })
        else:
            giro_canal.append({
                'SKU Real': prod_cod,
                'Canal': canal,
                'Qtd Vendida': qtd_venda
            })
            
    if not giro_canal: return pd.DataFrame()
    
    df_giro_canal = pd.DataFrame(giro_canal)
    df_pivot = df_giro_canal.pivot_table(index='SKU Real', columns='Canal', values='Qtd Vendida', aggfunc='sum', fill_value=0).reset_index()
    
    cols_canais = [c for c in df_pivot.columns if c != 'SKU Real']
    df_pivot['Total Geral'] = df_pivot[cols_canais].sum(axis=1)
    df_pivot = df_pivot.sort_values('Total Geral', ascending=False)
    
    return df_pivot

def atualizar_dashboards_resumo(df_detalhes, metas_dict):
    if df_detalhes.empty: return None, None, None, None, None, None, None
    
    cols_req = ['Canal', 'Total Venda', 'Lucro Bruto', 'Quantidade', 'Margem (%)', 'CNPJ', 'Produto']
    if not all(c in df_detalhes.columns for c in cols_req): return None, None, None, None, None, None, None

    dash_geral = df_detalhes.groupby('Canal').agg({
        'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Quantidade': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    dash_geral['Status Meta'] = dash_geral['Margem (%)'].apply(lambda x: obter_status_meta(x, metas_dict))
    
    dash_cnpj = df_detalhes.groupby(['CNPJ', 'Canal']).agg({
        'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    
    dash_exec = df_detalhes.groupby('Produto').agg({
        'Quantidade': 'sum', 'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    med_v = dash_exec['Total Venda'].median()
    med_m = dash_exec['Margem (%)'].median()
    dash_exec['Classificação BCG'] = dash_exec.apply(lambda x: classificar_bcg(x, med_v, med_m), axis=1)
    dash_exec['Status Meta'] = dash_exec['Margem (%)'].apply(lambda x: obter_status_meta(x, metas_dict))
    
    dash_exec['Classificação BCG'] = pd.Categorical(dash_exec['Classificação BCG'], categories=ORDEM_BCG, ordered=True)
    dash_exec = dash_exec.sort_values(['Classificação BCG', 'Total Venda'], ascending=[True, False])
    dash_exec.insert(0, 'Ranking', range(1, len(dash_exec) + 1))
    
    dash_bcg_canal = df_detalhes.groupby(['Canal', 'Produto']).agg({
        'Total Venda': 'sum', 'Margem (%)': 'mean', 'Quantidade': 'sum'
    }).reset_index()
    bcg_final = []
    for canal in dash_bcg_canal['Canal'].unique():
        subset = dash_bcg_canal[dash_bcg_canal['Canal'] == canal].copy()
        med_v_c = subset['Total Venda'].median()
        med_m_c = subset['Margem (%)'].median()
        subset['Classificação'] = subset.apply(lambda x: classificar_bcg(x, med_v_c, med_m_c), axis=1)
        subset['Status Meta'] = subset['Margem (%)'].apply(lambda x: obter_status_meta(x, metas_dict))
        
        subset['Classificação'] = pd.Categorical(subset['Classificação'], categories=ORDEM_BCG, ordered=True)
        subset = subset.sort_values(['Classificação', 'Total Venda'], ascending=[True, False])
        subset.insert(0, 'Ranking', range(1, len(subset) + 1))
        
        bcg_final.append(subset)
    
    df_bcg_final = pd.concat(bcg_final) if bcg_final else pd.DataFrame()
    if not df_bcg_final.empty:
        df_bcg_final = df_bcg_final.sort_values(['Canal', 'Ranking'])

    df_precos = df_detalhes.groupby(['Produto', 'Canal']).agg({
        'Total Venda': 'sum', 'Quantidade': 'sum'
    }).reset_index()
    df_precos['Preço Médio'] = df_precos['Total Venda'] / df_precos['Quantidade']
    df_precos_pivot = df_precos.pivot(index='Produto', columns='Canal', values='Preço Médio').reset_index()

    df_giro = calcular_giro_produtos(df_detalhes)
    df_oportunidades = calcular_oportunidades(df_detalhes)

    return dash_geral, dash_cnpj, dash_exec, df_bcg_final, df_precos_pivot, df_giro, df_oportunidades

def salvar_todos_dashboards(ss, d_geral, d_cnpj, d_exec, d_precos, d_bcg, d_giro, d_oportunidades):
    def salvar_aba(nome, df):
        try:
            try:
                ws = ss.worksheet(nome)
            except:
                ws = ss.add_worksheet(title=nome, rows=1000, cols=20)
            
            ws.clear()
            df_fmt = df.copy()
            
            if nome == "4. Preços Marketplaces":
                for col in df_fmt.columns:
                    if col != 'Produto':
                        df_fmt[col] = df_fmt[col].apply(lambda x: format_currency_br(x) if pd.notna(x) and x != 0 else "-")
            else:
                for c in df_fmt.columns:
                    if 'Margem' in c: df_fmt[c] = df_fmt[c].apply(format_percent_br)
                    elif any(x in c for x in ['Venda', 'Lucro', 'Custo', 'Preço']): df_fmt[c] = df_fmt[c].apply(format_currency_br)
            
            ws.update([df_fmt.columns.values.tolist()] + df_fmt.astype(str).values.tolist())
        except Exception as e: st.error(f"Erro ao salvar aba {nome}: {e}")

    if d_geral is not None: salvar_aba("1. Dashboard Geral", d_geral)
    if d_cnpj is not None: salvar_aba("2. Análise por CNPJ", d_cnpj)
    if d_exec is not None: salvar_aba("3. Análise Executiva", d_exec)
    if d_precos is not None: salvar_aba("4. Preços Marketplaces", d_precos)
    if d_bcg is not None: salvar_aba("5. Matriz BCG", d_bcg)
    if d_giro is not None: salvar_aba("7. Giro de Produtos", d_giro)
    if d_oportunidades is not None: salvar_aba("8. Oportunidades", d_oportunidades)

# ==============================================================================
# INTERFACE
# ==============================================================================
try:
    ss, gc = conectar_google_sheets()
    configs, estoque_produtos = carregar_configuracoes()
    metas_dict = {}
    if configs:
        for key, df in configs.items(): st.session_state[key] = df
        st.session_state['estoque_produtos'] = estoque_produtos
        
        if 'metas' in configs and not configs['metas'].empty:
            for _, row in configs['metas'].iterrows():
                try:
                    metas_dict[row['Indicador']] = float(row['Valor'])
                except: pass
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

st.title("📊 Sales BI Pro + 🏭 MRP Fábrica")

with st.sidebar:
    st.header("🔌 Status da Conexão")
    
    # MODO SIMULAÇÃO
    modo_simulacao = st.checkbox("🧪 MODO SIMULAÇÃO (Sandbox)", value=False, help="Ative para testar uploads sem salvar nada na planilha.")
    
    if modo_simulacao:
        st.warning("⚠️ MODO SIMULAÇÃO ATIVO: Nenhuma alteração será salva!")
    
    if ss:
        st.success(f"Conectado a: **{ss.title}**")
        
        qtd_prod = len(st.session_state.get('produtos', []))
        qtd_kits = len(st.session_state.get('kits', []))
        
        if qtd_prod > 0: st.info(f"📦 Produtos Carregados: {qtd_prod}")
        else: st.error("❌ Nenhum Produto encontrado! Verifique a aba 'Produtos'.")
        
        if qtd_kits > 0: st.info(f"🧩 Kits Carregados: {qtd_kits}")
        else: st.warning("⚠️ Nenhum Kit encontrado (ou aba 'Kits' vazia).")
    else:
        st.error("❌ Desconectado")

    st.divider()
    st.header("📥 Importar Vendas")
    
    if st.button("🔄 Atualizar Dados (Limpar Cache)"):
        carregar_dados_detalhes.clear()
        carregar_configuracoes.clear()
        carregar_estoque_externo.clear()
        st.success("Cache limpo! Recarregando...")
        time.sleep(1)
        st.rerun()
        
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    cnpj_regime = st.selectbox("CNPJ/Regime", ['Simples Nacional', 'Lucro Presumido', 'Lucro Real'])
    data_venda = st.date_input("Data", datetime.now()) if formato == 'Bling' else datetime.now()
    custo_ads = st.number_input("💰 Ads (R$)", min_value=0.0, step=10.0)
    uploaded_file = st.file_uploader("Arquivo Excel", type=['xlsx'])
    
    # Variáveis de sessão para filas
    if 'fila_baixa_estoque' not in st.session_state: st.session_state['fila_baixa_estoque'] = pd.DataFrame()
    if 'fila_simulacao' not in st.session_state: st.session_state['fila_simulacao'] = pd.DataFrame()

    btn_label = "🚀 Simular Processamento" if modo_simulacao else "🚀 Processar e Salvar"
    
    if uploaded_file and st.button(btn_label):
        with st.spinner("Processando..."):
            try:
                df_orig = pd.read_excel(uploaded_file)
                df_processado, df_faltantes = processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads)
                
                if not df_faltantes.empty:
                    st.error("⛔ OPERAÇÃO CANCELADA: Foram encontrados produtos com erros ou não cadastrados!")
                    st.dataframe(df_faltantes)
                    st.download_button("📥 Baixar Relatório de Erros", data=to_excel(df_faltantes), file_name="erros_impediram_salvamento.xlsx")
                
                elif df_processado is not None and not df_processado.empty:
                    df_novo_lote = df_processado.copy()
                    df_novo_lote['Canal'] = CHANNELS[canal]
                    
                    if modo_simulacao:
                        # MODO SIMULAÇÃO: Salva apenas na fila temporária de simulação
                        if st.session_state['fila_simulacao'].empty:
                            st.session_state['fila_simulacao'] = df_novo_lote
                        else:
                            st.session_state['fila_simulacao'] = pd.concat([st.session_state['fila_simulacao'], df_novo_lote], ignore_index=True)
                        st.success(f"🧪 SIMULAÇÃO: {len(df_processado)} vendas processadas na memória. Nada foi salvo.")
                        
                    else:
                        # MODO REAL: Salva no Sheets e na fila real
                        if st.session_state['fila_baixa_estoque'].empty:
                            st.session_state['fila_baixa_estoque'] = df_novo_lote
                        else:
                            st.session_state['fila_baixa_estoque'] = pd.concat([st.session_state['fila_baixa_estoque'], df_novo_lote], ignore_index=True)
                        
                        ws_detalhes = ss.worksheet("6. Detalhes")
                        first_row = ws_detalhes.row_values(1)
                        if not first_row or 'Total Venda' not in first_row:
                            ws_detalhes.clear()
                            ws_detalhes.append_row(COLUNAS_ESPERADAS)
                        
                        df_salvar = df_processado.copy()
                        for c in df_salvar.columns:
                            if 'Margem' in c: df_salvar[c] = df_salvar[c].apply(format_percent_br)
                            elif any(x in c for x in ['Venda', 'Lucro', 'Custo', 'Preço', 'Impostos', 'Comissão', 'Taxas', 'Embalagem', 'Ads']): 
                                df_salvar[c] = df_salvar[c].apply(format_currency_br)
                        
                        df_salvar = df_salvar[COLUNAS_ESPERADAS]
                        ws_detalhes.append_rows(df_salvar.astype(str).values.tolist())
                        st.success(f"✅ {len(df_processado)} vendas salvas com sucesso!")
                        
                        carregar_dados_detalhes.clear()
                        df_historico = carregar_dados_detalhes()
                        if not df_historico.empty:
                            d_geral, d_cnpj, d_exec, d_bcg, d_precos, d_giro, d_oportunidades = atualizar_dashboards_resumo(df_historico, metas_dict)
                            salvar_todos_dashboards(ss, d_geral, d_cnpj, d_exec, d_precos, d_bcg, d_giro, d_oportunidades)
                            st.success("Dashboards atualizados!")
                            time.sleep(1)
                            st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    st.header("💾 Manutenção")
    if st.button("💾 Forçar Salvar Dashboards", disabled=modo_simulacao):
        if modo_simulacao: st.error("Desative o Modo Simulação para salvar.")
        else:
            with st.spinner("Recalculando e salvando abas..."):
                df_historico = carregar_dados_detalhes()
                if not df_historico.empty:
                    d_geral, d_cnpj, d_exec, d_bcg, d_precos, d_giro, d_oportunidades = atualizar_dashboards_resumo(df_historico, metas_dict)
                    salvar_todos_dashboards(ss, d_geral, d_cnpj, d_exec, d_precos, d_bcg, d_giro, d_oportunidades)
                    st.success("Todas as abas foram atualizadas na planilha!")

st.divider()
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(["📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", "💲 Preços", "📋 Detalhes", "📦 Giro de Produtos", "🚀 Oportunidades", "🏭 MRP Fábrica"])
df_detalhes = carregar_dados_detalhes()

if not df_detalhes.empty and 'Total Venda' in df_detalhes.columns:
    d_geral, d_cnpj, d_exec, d_bcg, d_precos, d_giro, d_oportunidades = atualizar_dashboards_resumo(df_detalhes, metas_dict)

    with tab1:
        total_venda = df_detalhes['Total Venda'].sum()
        margem_media = df_detalhes['Margem (%)'].mean()
        ticket_medio = df_detalhes['Total Venda'].mean()
        col1, col2, col3 = st.columns(3)
        col1.metric("Vendas Totais", format_currency_br(total_venda))
        col2.metric("Margem Média", format_percent_br(margem_media))
        col3.metric("Ticket Médio", format_currency_br(ticket_medio))
        st.bar_chart(df_detalhes.groupby('Canal')['Total Venda'].sum())
    with tab2: st.dataframe(d_cnpj)
    with tab3: st.dataframe(d_exec)
    with tab4: st.dataframe(d_bcg)
    with tab5: st.dataframe(d_precos)
    with tab6: st.dataframe(df_detalhes)
    with tab7: st.dataframe(d_giro)
    with tab8: st.dataframe(d_oportunidades)
    
    with tab9:
        st.subheader("🏭 MRP - Planejamento de Produção em Cascata")
        
        if modo_simulacao:
            st.warning("🧪 EXIBINDO DADOS DE SIMULAÇÃO (NADA SERÁ SALVO)")
            df_vendas_fila = st.session_state.get('fila_simulacao', pd.DataFrame())
        else:
            df_vendas_fila = st.session_state.get('fila_baixa_estoque', pd.DataFrame())
            
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            if st.button("🔄 Carregar Estoque Externo"):
                carregar_estoque_externo.clear()
                st.success("Estoque recarregado!")
        with col_ctrl2:
            if st.button("🗑️ Limpar Fila"):
                if modo_simulacao: st.session_state['fila_simulacao'] = pd.DataFrame()
                else: st.session_state['fila_baixa_estoque'] = pd.DataFrame()
                st.success("Fila limpa!")
                time.sleep(1)
                st.rerun()
            
        df_estoque_ext = carregar_estoque_externo()
        
        if df_estoque_ext.empty:
            st.error("Não foi possível carregar o estoque externo.")
        else:
            if df_vendas_fila.empty:
                st.info("ℹ️ A fila de vendas está vazia.")
            else:
                st.subheader(f"Plano de Produção ({len(df_vendas_fila)} vendas na fila)")
                
                # PROCESSAMENTO MRP
                df_mrp = processar_mrp_fila(df_vendas_fila, df_estoque_ext)
                
                if df_mrp.empty:
                    st.warning("Nenhuma ação necessária.")
                else:
                    st.write("### 📋 O que precisa ser feito?")
                    acoes_order = ['SEPARAR_ESTOQUE', 'PRODUZIR_MONTAR', 'COMPRAR_PRODUZIR_EXTERNO', 'ERRO_CADASTRO', 'ERRO_RECEITA']
                    for acao in acoes_order:
                        itens = df_mrp[df_mrp['acao'] == acao]
                        if not itens.empty:
                            itens_agrupados = itens.groupby(['codigo', 'nome'])['qtd'].sum().reset_index()
                            with st.expander(f"{acao.replace('_', ' ')} ({len(itens_agrupados)} itens)", expanded=True):
                                st.dataframe(itens_agrupados)
                    
                    st.divider()
                    
                    # GERAÇÃO DE EXCEL HIERÁRQUICO
                    try:
                        excel_bytes = gerar_excel_hierarquico(df_vendas_fila, df_estoque_ext)
                        st.download_button(
                            label="📥 Baixar Ordem de Produção (Excel Hierárquico)",
                            data=excel_bytes,
                            file_name=f"ordem_producao_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                    except Exception as e:
                        st.error(f"Erro ao gerar Excel: {e}")
