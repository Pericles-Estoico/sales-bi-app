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

# Conectar
configs = {}
try:
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
    
    estoque_produtos = set()
    if "TEMPLATE_ESTOQUE_URL" in st.secrets:
        try:
            ss_estoque = gc.open_by_url(st.secrets["TEMPLATE_ESTOQUE_URL"])
            ws_estoque = ss_estoque.worksheet('template_estoque')
            df_estoque = pd.DataFrame(ws_estoque.get_all_records())
            if 'codigo' in df_estoque.columns:
                estoque_produtos = set(df_estoque['codigo'].tolist())
            st.session_state['estoque_produtos'] = estoque_produtos
        except: pass
    
    configs = {}
    for nome, key in [("Produtos", "produtos"), ("Kits", "kits"), ("Canais", "canais"), 
                      ("Custos por Pedido", "custos_ped"), ("Impostos", "impostos"), ("Frete", "frete"), ("Metas", "metas")]:
        try:
            sh = ss.worksheet(nome)
            data = sh.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                for col in df.columns:
                    if any(x in col for x in ['R$', '%', 'Peso', 'Custo', 'Preço', 'Taxa', 'Frete', 'Valor']):
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                configs[key] = df
                st.session_state[key] = df
        except: pass
except: st.error("❌ Erro conexão")

st.title("📊 Sales BI Pro - Dashboard Executivo")

if configs:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Produtos", len(configs.get('produtos', [])))
        st.metric("Kits", len(configs.get('kits', [])))
    with col2:
        st.metric("Canais", len(configs.get('canais', [])))
    with col3:
        if 'metas' in configs:
            st.metric("Margem Meta", configs['metas'].iloc[0]['Valor'])
    with col4:
        if 'custos_ped' in configs:
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
            if not impostos_df.empty:
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
                
                # Buscar em kits
                if not prod_encontrado and not kits_df.empty:
                    for _, k in kits_df.iterrows():
                        if normalizar(k['Código Kit']) == prod_norm:
                            tipo = 'Kit'
                            comps = str(k.get('SKUs Componentes', '')).split(';')
                            qtds_str = str(k.get('Qtd Componentes', '1')).split(';')
                            qtds_comp = [int(q) if q.strip().isdigit() else 1 for q in qtds_str]
                            for comp, q in zip(comps, qtds_comp):
                                comp_norm = normalizar(comp)
                                for _, p in produtos_df.iterrows():
                                    if normalizar(p['Código']) == comp_norm:
                                        custo_unit += (p.get('Custo (R$)', 0) or 0) * q
                                        break
                            break
                
                custo_total = custo_unit * qtd
                margem_bruta = total - custo_total
                impostos = total * aliquota
                taxa_total = (total * taxa_mp) + taxa_fixa + custo_emb
                lucro = margem_bruta - impostos - taxa_total
                margem_pct = (lucro / total * 100) if total > 0 else 0
                
                resultados.append({
                    'Data': row.get('Data', ''),
                    'Produto': prod,
                    'Tipo': tipo,
                    'Quantidade': qtd,
                    'Total': total,
                    'Custo_Total': custo_total,
                    'Margem_Bruta': margem_bruta,
                    'Impostos': impostos,
                    'Lucro_Liquido': lucro,
                    'Margem_%': margem_pct,
                    'Canal': row['Canal'],
                    'CNPJ': row['CNPJ']
                })
            
            df_final = pd.DataFrame(resultados)
            st.session_state['data_novo'] = df_final
            st.success(f"✅ {len(df_final)} produtos processados!")
            st.dataframe(df_final)
        except Exception as e:
            st.error(f"❌ {e}")
    
    btn_label = "🧪 Simular Envio" if modo_teste else "📤 Enviar para Google Sheets"
    if st.button(btn_label) and 'data_novo' in st.session_state:
        if modo_teste:
            st.success("✅ SIMULAÇÃO: Dados processados!")
            st.info("📊 Preview:")
            st.dataframe(st.session_state['data_novo'])
            st.warning("⚠️ Modo Teste - dados NÃO salvos")
        else:
            try:
                df_novo = st.session_state['data_novo']
                
                try:
                    sh = ss.worksheet("6. Detalhes")
                    ex = sh.get_all_values()
                    df_ex = pd.DataFrame(ex[1:], columns=ex[0]) if len(ex) > 1 else pd.DataFrame()
                    for c in ['Quantidade','Total','Custo_Total','Margem_Bruta','Lucro_Liquido','Impostos']:
                        if c in df_ex.columns:
                            df_ex[c] = pd.to_numeric(df_ex[c], errors='coerce')
                except:
                    df_ex = pd.DataFrame()
                
                try:
                    sh = ss.worksheet("6. Detalhes")
                except:
                    sh = ss.add_worksheet("6. Detalhes", 5000, 20)
                
                df_full = pd.concat([df_ex, df_novo], ignore_index=True) if not df_ex.empty else df_novo
                
                agg = {'Quantidade':'sum','Total':'sum','Custo_Total':'sum','Margem_Bruta':'sum','Lucro_Liquido':'sum'}
                if 'Impostos' in df_full.columns:
                    agg['Impostos'] = 'sum'
                
                prods = df_full.groupby('Produto').agg(agg).reset_index()
                total = prods['Total'].sum()
                prods['Part%'] = (prods['Total']/total)*100
                
                med_q = prods['Quantidade'].median()
                med_p = prods['Part%'].median()
                
                def bcg(r):
                    if r['Quantidade'] >= med_q and r['Part%'] >= med_p: return 'Estrela'
                    elif r['Quantidade'] < med_q and r['Part%'] >= med_p: return 'Vaca Leiteira'
                    elif r['Quantidade'] >= med_q and r['Part%'] < med_p: return 'Interrogação'
                    else: return 'Abacaxi'
                
                prods['BCG'] = prods.apply(bcg, axis=1)
                
                try:
                    sh1 = ss.worksheet("1. Dashboard Geral")
                except:
                    sh1 = ss.add_worksheet("1. Dashboard Geral", 100, 5)
                
                dias = len(df_full['Data'].unique()) if 'Data' in df_full.columns else 1
                lucro = prods['Lucro_Liquido'].sum()
                margem = prods['Margem_Bruta'].sum()
                impostos_total = prods['Impostos'].sum() if 'Impostos' in prods.columns else 0
                
                d1 = [['DASHBOARD GERAL'],
                      [datetime.now().strftime("%d/%m/%Y %H:%M")], [],
                      ['Dias', dias],
                      ['Faturamento', f'R$ {total:,.2f}'],
                      ['Margem Bruta', f'R$ {margem:,.2f}'],
                      ['Impostos', f'R$ {impostos_total:,.2f}'],
                      ['Lucro Líquido', f'R$ {lucro:,.2f}'],
                      ['Margem %', f'{(lucro/total*100):.1f}%'],
                      ['Produtos', len(prods)], [],
                      ['BCG', 'Qtd', 'Faturamento', 'Lucro']]
                
                for cat in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
                    pc = prods[prods['BCG'] == cat]
                    lc = pc['Lucro_Liquido'].sum()
                    d1.append([cat, len(pc), f'R$ {pc["Total"].sum():,.2f}', f'R$ {lc:,.2f}'])
                
                sh1.clear()
                sh1.update('A1', d1)
                
                if 'CNPJ' in df_full.columns:
                    try:
                        sh_cnpj = ss.worksheet("2. Por CNPJ")
                    except:
                        sh_cnpj = ss.add_worksheet("2. Por CNPJ", 100, 8)
                    
                    cnpj_agg = df_full.groupby('CNPJ').agg({
                        'Total': 'sum', 'Custo_Total': 'sum', 'Margem_Bruta': 'sum',
                        'Impostos': 'sum', 'Lucro_Liquido': 'sum'
                    }).reset_index()
                    
                    cnpj_agg['Margem %'] = (cnpj_agg['Lucro_Liquido'] / cnpj_agg['Total'] * 100).fillna(0)
                    
                    d_cnpj = [['ANÁLISE POR CNPJ/REGIME'], [],
                              ['Regime', 'Faturamento', 'Custo', 'Margem Bruta', 'Impostos', 'Lucro Líquido', 'Margem %']]
                    
                    for _, row in cnpj_agg.iterrows():
                        d_cnpj.append([row['CNPJ'], f"R$ {row['Total']:,.2f}", f"R$ {row['Custo_Total']:,.2f}",
                                       f"R$ {row['Margem_Bruta']:,.2f}", f"R$ {row['Impostos']:,.2f}",
                                       f"R$ {row['Lucro_Liquido']:,.2f}", f"{row['Margem %']:.1f}%"])
                    
                    sh_cnpj.clear()
                    sh_cnpj.update('A1', d_cnpj)
                
                try:
                    sh_exec = ss.worksheet("3. Análise Executiva")
                except:
                    sh_exec = ss.add_worksheet("3. Análise Executiva", 200, 6)
                
                margem_media = (lucro / total * 100) if total > 0 else 0
                produtos_prejuizo = len(prods[prods['Lucro_Liquido'] <= 0])
                
                def semaforo(valor, meta_min, meta_ideal):
                    if valor >= meta_ideal: return '🟢'
                    elif valor >= meta_min: return '🟡'
                    else: return '🔴'
                
                top5 = prods.nlargest(5, 'Lucro_Liquido')[['Produto', 'Lucro_Liquido', 'BCG']]
                bottom5 = prods.nsmallest(5, 'Lucro_Liquido')[['Produto', 'Lucro_Liquido', 'BCG']]
                
                recomendacoes = []
                if produtos_prejuizo > 0:
                    recomendacoes.append(f"⚠️ {produtos_prejuizo} produtos em prejuízo")
                
                abacaxis = prods[prods['BCG'] == 'Abacaxi']
                if len(abacaxis) > 0:
                    recomendacoes.append(f"🗑️ {len(abacaxis)} produtos 'Abacaxi'")
                
                estrelas = prods[prods['BCG'] == 'Estrela']
                if len(estrelas) > 0:
                    recomendacoes.append(f"⭐ {len(estrelas)} produtos 'Estrela'")
                
                d_exec = [['ANÁLISE EXECUTIVA'], [datetime.now().strftime("%d/%m/%Y %H:%M")], [],
                          ['Indicador', 'Valor', 'Status'],
                          ['Margem Líquida', f'{margem_media:.1f}%', semaforo(margem_media, 10, 15)],
                          ['Lucro Líquido', f'R$ {lucro:,.2f}', '🟢' if lucro > 0 else '🔴'], [],
                          ['TOP 5 LUCRATIVOS'], ['Produto', 'Lucro', 'BCG']]
                
                for _, p in top5.iterrows():
                    d_exec.append([p['Produto'], f"R$ {p['Lucro_Liquido']:,.2f}", p['BCG']])
                
                d_exec.extend([[], ['TOP 5 MENOS LUCRATIVOS'], ['Produto', 'Lucro', 'BCG']])
                for _, p in bottom5.iterrows():
                    d_exec.append([p['Produto'], f"R$ {p['Lucro_Liquido']:,.2f}", p['BCG']])
                
                d_exec.extend([[], ['RECOMENDAÇÕES']])
                for rec in recomendacoes:
                    d_exec.append([rec])
                
                sh_exec.clear()
                sh_exec.update('A1', d_exec)
                
                # === ABA PREÇOS MARKETPLACES ===
                try:
                    sh_precos = ss.worksheet("4. Preços Marketplaces")
                except:
                    sh_precos = ss.add_worksheet("4. Preços Marketplaces", 1000, 20)
                
                # Ler preços existentes ou criar novo
                try:
                    precos_ex = sh_precos.get_all_values()
                    df_precos = pd.DataFrame(precos_ex[1:], columns=precos_ex[0]) if len(precos_ex) > 1 else pd.DataFrame()
                except:
                    df_precos = pd.DataFrame()
                
                # Calcular preço real por produto/canal
                canal_atual = df_novo['Canal'].iloc[0] if len(df_novo) > 0 else 'Geral'
                
                # Mapear canal para coluna
                canal_map = {
                    '📊 Vendas Gerais': 'Geral',
                    '🛒 Mercado Livre': 'ML',
                    '🛍️ Shopee Matriz': 'Shopee_Matriz',
                    '🏪 Shopee 1:50': 'Shopee_150',
                    '👗 Shein': 'Shein'
                }
                col_canal = canal_map.get(canal_atual, 'Geral')
                
                # Agregar por produto para obter preço médio real
                preco_real = df_novo.groupby('Produto').agg({
                    'Total': 'sum', 'Quantidade': 'sum'
                }).reset_index()
                preco_real['Preco_Unit'] = preco_real['Total'] / preco_real['Quantidade']
                
                # Obter custos dos produtos
                produtos_df = st.session_state.get('produtos', pd.DataFrame())
                canais_df = st.session_state.get('canais', pd.DataFrame())
                
                # Obter taxa do canal
                taxa_canal = 0.16
                if not canais_df.empty:
                    for _, c in canais_df.iterrows():
                        if col_canal.lower() in str(c.get('Canal', '')).lower():
                            taxa_canal = c.get('Taxa Marketplace (%)', 16) / 100
                            break
                
                # Criar/atualizar tabela de preços
                colunas_precos = ['Código', 'Custo (R$)', 'ML', 'M.C ML', 'Shopee_Matriz', 'M.C SM', 'Shopee_150', 'M.C S150', 'Shein', 'M.C Shein', 'Ecommerce', 'M.C Ecom', 'Média M.C']
                
                if df_precos.empty:
                    df_precos = pd.DataFrame(columns=colunas_precos)
                
                # Atualizar preços para o canal atual
                for _, row in preco_real.iterrows():
                    prod = row['Produto']
                    preco = row['Preco_Unit']
                    
                    # Buscar custo
                    custo = 0
                    prod_norm = normalizar(prod)
                    if not produtos_df.empty:
                        for _, p in produtos_df.iterrows():
                            if normalizar(p['Código']) == prod_norm:
                                custo = p.get('Custo (R$)', 0) or 0
                                break
                    
                    # Calcular M.C = (Preço - Custo - Taxas) / Preço * 100
                    mc = ((preco - custo - (preco * taxa_canal)) / preco * 100) if preco > 0 else 0
                    
                    # Verificar se produto já existe na tabela
                    if prod in df_precos['Código'].values:
                        idx = df_precos[df_precos['Código'] == prod].index[0]
                        df_precos.loc[idx, col_canal] = preco
                        df_precos.loc[idx, f'M.C {col_canal[:2]}'] = mc
                    else:
                        nova_linha = {c: '' for c in colunas_precos}
                        nova_linha['Código'] = prod
                        nova_linha['Custo (R$)'] = custo
                        nova_linha[col_canal] = preco
                        # Encontrar coluna M.C correta
                        mc_cols = {'ML': 'M.C ML', 'Shopee_Matriz': 'M.C SM', 'Shopee_150': 'M.C S150', 'Shein': 'M.C Shein', 'Ecommerce': 'M.C Ecom'}
                        if col_canal in mc_cols:
                            nova_linha[mc_cols[col_canal]] = mc
                        df_precos = pd.concat([df_precos, pd.DataFrame([nova_linha])], ignore_index=True)
                
                # Calcular Média M.C para cada produto
                mc_colunas = ['M.C ML', 'M.C SM', 'M.C S150', 'M.C Shein', 'M.C Ecom']
                for idx, row in df_precos.iterrows():
                    mcs = []
                    for mc_col in mc_colunas:
                        if mc_col in df_precos.columns:
                            val = row.get(mc_col, '')
                            if val != '' and pd.notna(val):
                                try:
                                    mcs.append(float(val))
                                except: pass
                    df_precos.loc[idx, 'Média M.C'] = sum(mcs) / len(mcs) if mcs else 0
                
                # Formatar e enviar
                d_precos = [colunas_precos]
                for _, row in df_precos.iterrows():
                    linha = []
                    for col in colunas_precos:
                        val = row.get(col, '')
                        if 'R$' in col or col in ['ML', 'Shopee_Matriz', 'Shopee_150', 'Shein', 'Ecommerce', 'Custo (R$)']:
                            linha.append(f'R$ {float(val):.2f}' if val != '' and pd.notna(val) else '')
                        elif 'M.C' in col or 'Média' in col:
                            linha.append(f'{float(val):.1f}%' if val != '' and pd.notna(val) else '')
                        else:
                            linha.append(str(val))
                    d_precos.append(linha)
                
                sh_precos.clear()
                sh_precos.update('A1', d_precos)
                
                # === FIM ABA PREÇOS MARKETPLACES ===
                
                cols = ['Data', 'Produto', 'Tipo', 'Qtd', 'Total', 'Custo', 'Lucro', 'Margem%', 'Canal', 'CNPJ', 'BCG']
                d6 = [cols]
                for _, r in df_full.iterrows():
                    cat = prods[prods['Produto'] == r['Produto']]['BCG'].values[0] if r['Produto'] in prods['Produto'].values else 'N/A'
                    d6.append([str(r.get('Data', '')), r['Produto'], r.get('Tipo', ''), int(r['Quantidade']),
                               float(r['Total']), float(r.get('Custo_Total', 0)), float(r.get('Lucro_Liquido', 0)),
                               f"{r.get('Margem_%', 0):.1f}%", r.get('Canal', ''), r.get('CNPJ', ''), cat])
                
                sh.clear()
                sh.update('A1', d6)
                
                st.success(f"✅ {len(df_full)} registros | Lucro: R$ {lucro:,.2f}")
                st.info(f"🔗 [Abrir Google Sheets]({st.secrets['GOOGLE_SHEETS_URL']})")
            except Exception as e:
                st.error(f"❌ {e}")

if not configs:
    st.info("👈 Configure a planilha Google Sheets primeiro")
