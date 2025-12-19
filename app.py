import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import unicodedata
import io

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

CHANNELS = {'geral': '📊 Vendas Gerais', 'mercado_livre': '🛒 Mercado Livre', 'shopee_matriz': '🛍️ Shopee Matriz', 'shopee_150': '🏪 Shopee 1:50', 'shein': '👗 Shein'}

def normalizar(texto):
    if pd.isna(texto): return ''
    texto = str(texto)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

def converter_bling(df, data):
    d = pd.DataFrame()
    d['Data'] = data
    d['Produto'] = df['Código']
    d['Quantidade'] = df['Quantidade']
    d['Total'] = df['Valor'].apply(lambda x: float(str(x).replace('R$','').replace('.','').replace(',','.').strip()))
    d['Preço Unitário'] = d['Total'] / d['Quantidade']
    return d

# Conectar com Cache
@st.cache_resource
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
    return ss, gc

@st.cache_data(ttl=3600)  # Cache por 1 hora
def carregar_configuracoes():
    try:
        ss, gc = conectar_google_sheets()
        configs_data = {}
        
        # Carregar Estoque
        estoque_produtos = set()
        if "TEMPLATE_ESTOQUE_URL" in st.secrets:
            try:
                ss_estoque = gc.open_by_url(st.secrets["TEMPLATE_ESTOQUE_URL"])
                ws_estoque = ss_estoque.worksheet('template_estoque')
                df_estoque = pd.DataFrame(ws_estoque.get_all_records())
                if 'codigo' in df_estoque.columns:
                    estoque_produtos = set(df_estoque['codigo'].tolist())
            except: pass
        
        # Carregar Abas de Configuração
        for nome, key in [("Produtos", "produtos"), ("Kits", "kits"), ("Canais", "canais"), 
                          ("Custos por Pedido", "custos_ped"), ("Impostos", "impostos"), ("Frete", "frete"), ("Metas", "metas")]:
            try:
                sh = ss.worksheet(nome)
                data = sh.get_all_values()
                if len(data) > 1:
                    # Tratar colunas duplicadas
                    cols = data[0]
                    seen = {}
                    new_cols = []
                    for c in cols:
                        c = c.strip()
                        if c in seen:
                            seen[c] += 1
                            new_cols.append(f"{c}_{seen[c]}")
                        else:
                            seen[c] = 0
                            new_cols.append(c)
                    
                    df = pd.DataFrame(data[1:], columns=new_cols)
                    
                    # Limpar colunas numéricas
                    for col in df.columns:
                        if any(x in col for x in ['R$', '%', 'Peso', 'Custo', 'Preço', 'Taxa', 'Frete', 'Valor']):
                            df[col] = df[col].apply(lambda x: str(x).replace('R$', '').replace(' ', '').replace(',', '.') if pd.notna(x) else x)
                            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    configs_data[key] = df
            except Exception as e:
                st.error(f"⚠️ Erro ao carregar aba '{nome}': {str(e)}")
            
        return configs_data, estoque_produtos
    except Exception as e:
        st.error(f"❌ Erro geral ao carregar configurações: {str(e)}")
        return None, None

def get_or_create_worksheet(ss, title, rows=1000, cols=20):
    try:
        return ss.worksheet(title)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title, rows, cols)

configs = {}
ss = None
estoque_produtos = set()

# Botão para limpar cache
with st.sidebar:
    if st.button("🔄 Recarregar Configurações (Limpar Cache)"):
        st.cache_data.clear()
        st.rerun()

try:
    ss, gc = conectar_google_sheets()
    configs, estoque_produtos = carregar_configuracoes()
    
    if configs:
        for key, df in configs.items():
            st.session_state[key] = df
        st.session_state['estoque_produtos'] = estoque_produtos
    else:
        st.error("❌ Erro ao carregar configurações. Verifique a conexão.")
        
except Exception as e:
    st.error(f"❌ Erro conexão: {str(e)}")

st.title("📊 Sales BI Pro - Dashboard Executivo")

if configs:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Produtos", len(configs.get('produtos', [])))
        st.metric("Kits", len(configs.get('kits', [])))
    with col2:
        st.metric("Canais", len(configs.get('canais', [])))
    with col3:
        if 'metas' in configs and not configs['metas'].empty:
            st.metric("Margem Meta", configs['metas'].iloc[0]['Valor'])
    with col4:
        if 'custos_ped' in configs and not configs['custos_ped'].empty:
            custo_emb = configs['custos_ped']['Custo Unitário (R$)'].sum()
            st.metric("Custo Embalagem", f"R$ {custo_emb:.2f}")

with st.sidebar:
    st.header("🎲 Controles")
    modo_teste = st.checkbox("🧪 Modo Teste (simulação)", value=False)
    if modo_teste:
        st.warning("⚠️ Simulação ativa - dados NÃO serão salvos")
    
    st.divider()
    st.header("📤 Vendas")
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    cnpj_regime = st.selectbox("CNPJ/Regime", ['Simples Nacional', 'Lucro Presumido', 'Lucro Real'])
    if formato == 'Bling':
        data_venda = st.date_input("Data", datetime.now())
    
    # Novo campo para Ads/Campanhas
    custo_ads = st.number_input("💰 Investimento em Ads/Campanhas do Dia (R$)", min_value=0.0, value=0.0, step=10.0)
    
    uploaded_file = st.file_uploader("Excel", type=['xlsx'])
    
    if uploaded_file and st.button("🔄 Processar"):
        try:
            df_orig = pd.read_excel(uploaded_file)
            df_novo = converter_bling(df_orig, data_venda.strftime('%Y-%m-%d')) if 'Código' in df_orig.columns else df_orig.copy()
            df_novo['Canal'] = CHANNELS[canal]
            df_novo['CNPJ'] = cnpj_regime
            
            # Normalizar e mapear produtos
            produtos_venda_orig = df_novo['Produto'].unique().tolist()
            produtos_venda_norm = {normalizar(p): p for p in produtos_venda_orig}
            
            produtos_config_norm = {}
            kits_config_norm = {}
            estoque_norm = {}
            
            estoque_produtos = st.session_state.get('estoque_produtos', set())
            if estoque_produtos:
                estoque_norm = {normalizar(p): p for p in estoque_produtos}
            
            if 'produtos' in st.session_state:
                for p in st.session_state['produtos']['Código'].tolist():
                    produtos_config_norm[normalizar(p)] = p
            if 'kits' in st.session_state:
                for k in st.session_state['kits']['Código Kit'].tolist():
                    kits_config_norm[normalizar(k)] = k
            
            todos_config_norm = {**produtos_config_norm, **kits_config_norm}
            
            mapeamento = {}
            for norm, orig in produtos_venda_norm.items():
                if norm in todos_config_norm:
                    mapeamento[orig] = todos_config_norm[norm]
                elif norm in estoque_norm:
                    mapeamento[orig] = estoque_norm[norm]
            
            df_novo['Produto'] = df_novo['Produto'].apply(lambda x: mapeamento.get(x, x))
            
            produtos_venda = set(df_novo['Produto'].unique())
            todos_config = set(produtos_config_norm.values()).union(set(kits_config_norm.values()))
            
            tem_erro = False
            estoque_set = set(estoque_norm.values()) if estoque_norm else set()
            
            if estoque_set:
                nao_existe_estoque = produtos_venda - estoque_set - set(kits_config_norm.values())
                if nao_existe_estoque:
                    tem_erro = True
                    st.error(f"❌ {len(nao_existe_estoque)} produto(s) NÃO EXISTEM no estoque!")
                    df_nao = pd.DataFrame({'Código': list(nao_existe_estoque)})
                    buf = io.BytesIO()
                    df_nao.to_excel(buf, index=False)
                    st.download_button("📥 Baixar para cadastrar no ESTOQUE", buf.getvalue(), "produtos_estoque.xlsx")
            
            produtos_sem_custo = produtos_venda - todos_config
            if estoque_set:
                produtos_sem_custo = produtos_sem_custo.intersection(estoque_set)
            
            if produtos_sem_custo:
                tem_erro = True
                st.error(f"❌ {len(produtos_sem_custo)} produto(s) SEM CUSTO!")
                df_sem = pd.DataFrame({'Código': list(produtos_sem_custo), 'Custo (R$)': 0, 'Preço Venda (R$)': 0, 'Peso (g)': 0})
                buf2 = io.BytesIO()
                df_sem.to_excel(buf2, index=False)
                st.download_button("📥 Baixar para adicionar CUSTO", buf2.getvalue(), "produtos_custo.xlsx")
            
            if tem_erro:
                st.stop()
            
            # Calcular custos
            produtos_df = st.session_state.get('produtos', pd.DataFrame())
            kits_df = st.session_state.get('kits', pd.DataFrame())
            impostos_df = st.session_state.get('impostos', pd.DataFrame())
            canais_df = st.session_state.get('canais', pd.DataFrame())
            custos_ped_df = st.session_state.get('custos_ped', pd.DataFrame())
            
            aliquota = 0.06
            if not impostos_df.empty and 'Tipo' in impostos_df.columns:
                imp = impostos_df[impostos_df['Tipo'].str.contains(cnpj_regime.split()[0], case=False, na=False)]
                if len(imp) > 0:
                    aliquota = imp.iloc[0]['Alíquota (%)'] / 100
            
            taxa_mp = 0.16
            taxa_fixa = 5.0
            if not canais_df.empty:
                can = canais_df[canais_df['Canal'].str.contains(canal.replace('_', ' '), case=False, na=False)]
                if len(can) > 0:
                    taxa_mp = can.iloc[0].get('Taxa Marketplace (%)', 16) / 100
                    taxa_fixa = can.iloc[0].get('Taxa Fixa Pedido (R$)', 5)
            
            custo_emb = custos_ped_df['Custo Unitário (R$)'].sum() if not custos_ped_df.empty else 0
            
            # Calcular rateio de Ads proporcional ao valor total da venda
            total_vendas_dia = df_novo['Total'].sum()
            
            resultados = []
            for _, row in df_novo.iterrows():
                prod = row['Produto']
                qtd = row['Quantidade']
                total = row['Total']
                
                custo_unit = 0
                tipo = 'Simples'
                
                # Normalizar para busca
                prod_norm = normalizar(prod)
                
                # Buscar em produtos
                prod_encontrado = False
                if not produtos_df.empty:
                    for _, p in produtos_df.iterrows():
                        if normalizar(p['Código']) == prod_norm:
                            custo_unit = p.get('Custo (R$)', 0) or 0
                            prod_encontrado = True
                            break
                
                # Se não achou, buscar em kits
                if not prod_encontrado and not kits_df.empty:
                    # Filtrar componentes do kit
                    comps = kits_df[kits_df['Código Kit'].apply(normalizar) == prod_norm]
                    if not comps.empty:
                        tipo = 'Kit'
                        custo_unit = 0
                        for _, comp in comps.iterrows():
                            cod_comp = comp['Código Componente']
                            qtd_comp = comp['Quantidade']
                            
                            # Buscar custo do componente
                            custo_comp = 0
                            for _, p in produtos_df.iterrows():
                                if normalizar(p['Código']) == normalizar(cod_comp):
                                    custo_comp = p.get('Custo (R$)', 0) or 0
                                    break
                            custo_unit += custo_comp * qtd_comp
                
                imposto = total * aliquota
                taxa = (total * taxa_mp) + taxa_fixa
                
                # Rateio de Ads proporcional ao valor da venda
                ads_rateio = 0
                if total_vendas_dia > 0:
                    ads_rateio = (total / total_vendas_dia) * custo_ads
                
                custo_total = (custo_unit * qtd) + custo_emb + imposto + taxa + ads_rateio
                lucro = total - custo_total
                margem = (lucro / total) * 100 if total > 0 else 0
                
                resultados.append({
                    'Data': row['Data'],
                    'Canal': row['Canal'],
                    'CNPJ': row['CNPJ'],
                    'Produto': prod,
                    'Tipo': tipo,
                    'Qtd': qtd,
                    'Total Venda': total,
                    'Custo Produto': custo_unit * qtd,
                    'Custo Emb.': custo_emb,
                    'Imposto': imposto,
                    'Taxa MP': taxa,
                    'Ads': ads_rateio,
                    'Custo Total': custo_total,
                    'Lucro Líquido': lucro,
                    'Margem %': margem
                })
            
            df_final = pd.DataFrame(resultados)
            
            # Preencher NaN com 0 para evitar erro JSON
            df_final = df_final.fillna(0)
            
            st.success("✅ Processamento concluído!")
            st.dataframe(df_final.style.format({
                'Total Venda': 'R$ {:.2f}',
                'Custo Total': 'R$ {:.2f}',
                'Lucro Líquido': 'R$ {:.2f}',
                'Margem %': '{:.1f}%',
                'Ads': 'R$ {:.2f}'
            }))
            
            if not modo_teste:
                # Salvar no Google Sheets
                try:
                    # 1. Dashboard Geral
                    ws_dash = get_or_create_worksheet(ss, "1. Dashboard Geral")
                    dados_existentes = ws_dash.get_all_values()
                    novo_conteudo = df_final.values.tolist()
                    
                    if len(dados_existentes) <= 1:
                        ws_dash.append_row(df_final.columns.tolist())
                    
                    ws_dash.append_rows(novo_conteudo)
                    
                    # 2. Análise por CNPJ
                    ws_cnpj = get_or_create_worksheet(ss, "2. Análise por CNPJ")
                    df_cnpj = df_final.groupby('CNPJ')[['Total Venda', 'Lucro Líquido']].sum().reset_index()
                    df_cnpj['Margem Média %'] = (df_cnpj['Lucro Líquido'] / df_cnpj['Total Venda']) * 100
                    ws_cnpj.clear()
                    ws_cnpj.update([df_cnpj.columns.values.tolist()] + df_cnpj.fillna(0).values.tolist())
                    
                    # 3. Análise Executiva
                    ws_exec = get_or_create_worksheet(ss, "3. Análise Executiva")
                    df_exec = df_final.groupby('Canal')[['Total Venda', 'Lucro Líquido']].sum().reset_index()
                    df_exec['Margem %'] = (df_exec['Lucro Líquido'] / df_exec['Total Venda']) * 100
                    ws_exec.clear()
                    ws_exec.update([df_exec.columns.values.tolist()] + df_exec.fillna(0).values.tolist())
                    
                    # 4. Preços Marketplaces
                    ws_precos = get_or_create_worksheet(ss, "4. Preços Marketplaces")
                    df_precos = df_final.groupby(['Produto', 'Canal'])['Total Venda'].mean().reset_index()
                    ws_precos.clear()
                    ws_precos.update([df_precos.columns.values.tolist()] + df_precos.fillna(0).values.tolist())
                    
                    # 6. Detalhes (com coluna Ads)
                    ws_detalhes = get_or_create_worksheet(ss, "6. Detalhes")
                    
                    # Verificar se cabeçalho existe e tem Ads
                    cabecalho_atual = []
                    try:
                        cabecalho_atual = ws_detalhes.row_values(1)
                    except: pass
                    
                    if not cabecalho_atual or 'Ads' not in cabecalho_atual:
                        ws_detalhes.clear()
                        ws_detalhes.append_row(df_final.columns.tolist())
                    
                    ws_detalhes.append_rows(novo_conteudo)
                    
                    st.toast("💾 Dados salvos no Google Sheets com sucesso!", icon="✅")
                    
                except Exception as e:
                    st.error(f"❌ Erro ao salvar no Google Sheets: {str(e)}")
        
        except Exception as e:
            st.error(f"❌ Erro no processamento: {str(e)}")
