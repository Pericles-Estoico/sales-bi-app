import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

CHANNELS = {'geral': '📊 Vendas Gerais', 'mercado_livre': '🛒 Mercado Livre', 'shopee_matriz': '🛍️ Shopee Matriz', 'shopee_150': '🏪 Shopee 1:50', 'shein': '👗 Shein'}

def converter_bling(df, data):
    d = pd.DataFrame()
    d['Data'] = data
    d['Produto'] = df['Código']
    d['Quantidade'] = df['Quantidade']
    d['Total'] = df['Valor'].apply(lambda x: float(str(x).replace('R$','').replace('.','').replace(',','.').strip()))
    d['Preço Unitário'] = d['Total'] / d['Quantidade']
    return d

def calcular_custo_kit(codigo, kits_df, produtos_df):
    kit = kits_df[kits_df['Código Kit'] == codigo]
    if len(kit) == 0: return 0, 0, []
    componentes = kit.iloc[0]['SKUs Componentes'].split(';')
    qtds = [int(q) for q in kit.iloc[0]['Qtd Componentes'].split(';')]
    custo = 0
    peso = 0
    detalhes = []
    for comp, qtd in zip(componentes, qtds):
        prod = produtos_df[produtos_df['Código'] == comp]
        if len(prod) > 0:
            c = prod.iloc[0]['Custo (R$)']
            p = prod.iloc[0]['Peso (g)']
            custo += c * qtd
            peso += p * qtd
            detalhes.append(f"{comp} x{qtd}")
    return custo, peso, detalhes

def calcular_frete(peso_g, frete_df):
    for _, row in frete_df.iterrows():
        if peso_g <= row['Peso Até (g)']:
            return row['Frete PAC (R$)']
    return frete_df.iloc[-1]['Frete PAC (R$)']

# Conectar
try:
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
    ss = gspread.authorize(creds).open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
    
    # Carregar configs
    configs = {}
    for nome, key in [("Produtos", "produtos"), ("Kits", "kits"), 
                      ("Canais", "canais"), ("Custos por Pedido", "custos_ped"), ("Impostos", "impostos"),
                      ("Frete", "frete"), ("Metas", "metas")]:
        try:
            sh = ss.worksheet(nome)
            data = sh.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                for col in df.columns:
                    if 'R$' in col or '%' in col or 'Peso' in col or 'Custo' in col or 'Preço' in col or 'Taxa' in col or 'Frete' in col:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                configs[key] = df
                st.session_state[key] = df
        except: pass
except: st.error("❌ Erro conexão")

# DASHBOARD
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
            st.metric("Ticket Meta", configs['metas'].iloc[3]['Valor'])
    with col4:
        if 'custos_ped' in configs:
            custo_emb = configs['custos_ped']['Custo Unitário (R$)'].sum()
            st.metric("Custo Embalagem", f"R$ {custo_emb:.2f}")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configurações")
    
    config_file = st.file_uploader("📋 Atualizar Config", type=['xlsx'])
    if config_file and st.button("💾 Salvar"):
        try:
            sheets_map = {
                'Produtos': 'Produtos',
                'Kits': 'Kits',
                'Custos por Pedido': 'Custos por Pedido',
                'Canais': 'Canais',
                'Impostos': 'Impostos',
                'Frete': 'Frete',
                'Metas': 'Metas'
            }
            
            for sheet_orig, sheet_dest in sheets_map.items():
                try:
                    df = pd.read_excel(config_file, sheet_name=sheet_orig)
                    try: sh = ss.worksheet(sheet_dest)
                    except: sh = ss.add_worksheet(sheet_dest, 500, 15)
                    dados = [df.columns.tolist()] + df.values.tolist()
                    sh.clear()
                    sh.update('A1', dados)
                except: pass
            
            st.success("✅ Config salva")
            st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")
    
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
            df_novo['Data_Upload'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Processar
            df_novo['Tipo'] = 'Desconhecido'
            df_novo['Custo_Produto'] = 0.0
            df_novo['Peso_g'] = 0
            df_novo['Preco_Cadastrado'] = 0.0
            
            if 'kits' in st.session_state and 'produtos' in st.session_state:
                for idx, row in df_novo.iterrows():
                    prod = row['Produto']
                    
                    # Kit?
                    kit_match = st.session_state['kits'][st.session_state['kits']['Código Kit'] == prod]
                    if len(kit_match) > 0:
                        df_novo.at[idx, 'Tipo'] = 'Kit'
                        custo, peso, _ = calcular_custo_kit(prod, st.session_state['kits'], st.session_state['produtos'])
                        df_novo.at[idx, 'Custo_Produto'] = custo
                        df_novo.at[idx, 'Peso_g'] = peso
                        df_novo.at[idx, 'Preco_Cadastrado'] = kit_match.iloc[0]['Preço Venda (R$)']
                        continue
                    
                    # Produto simples?
                    prod_match = st.session_state['produtos'][st.session_state['produtos']['Código'] == prod]
                    if len(prod_match) > 0:
                        df_novo.at[idx, 'Tipo'] = 'Produto'
                        df_novo.at[idx, 'Custo_Produto'] = prod_match.iloc[0]['Custo (R$)']
                        df_novo.at[idx, 'Peso_g'] = prod_match.iloc[0]['Peso (g)']
                        df_novo.at[idx, 'Preco_Cadastrado'] = prod_match.iloc[0]['Preço Venda (R$)']
            
            # Custos fixos por pedido (1x, não por produto)
            custo_embalagem = st.session_state.get('custos_ped', pd.DataFrame())
            if not custo_embalagem.empty:
                custo_emb_total = custo_embalagem['Custo Unitário (R$)'].sum()
                df_novo['Custo_Embalagem'] = custo_emb_total / len(df_novo)
            else:
                df_novo['Custo_Embalagem'] = 0
            
            # Frete por peso
            if 'frete' in st.session_state:
                df_novo['Frete'] = df_novo['Peso_g'].apply(lambda p: calcular_frete(p, st.session_state['frete']))
            else:
                df_novo['Frete'] = 0
            
            df_novo['Custo_Total'] = (df_novo['Custo_Produto'] * df_novo['Quantidade']) + df_novo['Custo_Embalagem']
            df_novo['Margem_Bruta'] = df_novo['Total'] - df_novo['Custo_Total']
            
            # Taxas canal
            if 'canais' in st.session_state:
                canal_match = st.session_state['canais'][st.session_state['canais']['Canal'].str.lower().str.contains(canal.replace('_',' '))]
                if len(canal_match) > 0:
                    info = canal_match.iloc[0]
                    df_novo['Taxa_Marketplace'] = df_novo['Total'] * (info['Taxa Marketplace (%)'] / 100)
                    df_novo['Taxa_Gateway'] = df_novo['Total'] * (info['Taxa Gateway (%)'] / 100)
                    df_novo['Taxa_Fixa'] = info['Taxa Fixa Pedido (R$)'] / len(df_novo)
            
            # Impostos por regime escolhido
            df_novo['Impostos'] = 0.0
            if 'impostos' in st.session_state:
                impostos_df = st.session_state['impostos']
                regime_match = impostos_df[impostos_df['Regime'] == cnpj_regime]
                if len(regime_match) > 0:
                    aliquota = regime_match.iloc[0]['Alíquota (%)'] / 100
                    df_novo['Impostos'] = df_novo['Total'] * aliquota
            
            df_novo['Lucro_Liquido'] = df_novo['Margem_Bruta'] - df_novo.get('Taxa_Marketplace', 0) - df_novo.get('Taxa_Gateway', 0) - df_novo.get('Taxa_Fixa', 0) - df_novo.get('Frete', 0) - df_novo.get('Impostos', 0)
            df_novo['Margem_%'] = (df_novo['Lucro_Liquido'] / df_novo['Total'] * 100).fillna(0)
            
            # Divergência
            df_novo['Preco_Real'] = df_novo['Preço Unitário']
            df_novo['Divergencia_%'] = ((df_novo['Preco_Real'] - df_novo['Preco_Cadastrado']) / df_novo['Preco_Cadastrado'] * 100).fillna(0)
            
            st.session_state['data_novo'] = df_novo
            
            # Preview
            st.success(f"✅ {len(df_novo)} produtos processados")
            st.dataframe(df_novo[['Produto','Tipo','Total','Custo_Total','Lucro_Liquido','Margem_%']].head())
            
            col1,col2,col3 = st.columns(3)
            col1.metric("Faturamento", f"R$ {df_novo['Total'].sum():,.2f}")
            col2.metric("Lucro Líquido", f"R$ {df_novo['Lucro_Liquido'].sum():,.2f}")
            col3.metric("Margem Média", f"{df_novo['Margem_%'].mean():.1f}%")
            
        except Exception as e:
            st.error(f"❌ {e}")

if 'data_novo' in st.session_state:
    if st.button("📤 Enviar para Google Sheets"):
        try:
            df_novo = st.session_state['data_novo']
            
            # Ler dados existentes
            try:
                sh = ss.worksheet("6. Detalhes")
                ex = sh.get_all_values()
                df_ex = pd.DataFrame(ex[1:], columns=ex[0]) if len(ex)>1 else pd.DataFrame()
                for c in ['Quantidade','Total','Custo_Total','Margem_Bruta','Lucro_Liquido','Impostos']:
                    if c in df_ex.columns: df_ex[c] = pd.to_numeric(df_ex[c], errors='coerce')
            except:
                df_ex = pd.DataFrame()
            
            try: sh = ss.worksheet("6. Detalhes")
            except: sh = ss.add_worksheet("6. Detalhes", 5000, 20)
            
            df_full = pd.concat([df_ex, df_novo], ignore_index=True) if not df_ex.empty else df_novo
            
            # Análise geral
            agg = {'Quantidade':'sum','Total':'sum','Custo_Total':'sum','Margem_Bruta':'sum','Lucro_Liquido':'sum'}
            if 'Impostos' in df_full.columns: agg['Impostos'] = 'sum'
            
            prods = df_full.groupby('Produto').agg(agg).reset_index()
            total = prods['Total'].sum()
            prods['Part%'] = (prods['Total']/total)*100
            
            med_q = prods['Quantidade'].median()
            med_p = prods['Part%'].median()
            
            def bcg(r):
                if r['Quantidade']>=med_q and r['Part%']>=med_p: return 'Estrela'
                elif r['Quantidade']<med_q and r['Part%']>=med_p: return 'Vaca Leiteira'
                elif r['Quantidade']>=med_q and r['Part%']<med_p: return 'Interrogação'
                else: return 'Abacaxi'
            
            prods['BCG'] = prods.apply(bcg, axis=1)
            
            # Dashboard Geral
            try: sh1 = ss.worksheet("1. Dashboard Geral")
            except: sh1 = ss.add_worksheet("1. Dashboard Geral", 100, 5)
            
            dias = len(df_full['Data'].unique()) if 'Data' in df_full.columns else 1
            lucro = prods['Lucro_Liquido'].sum()
            margem = prods['Margem_Bruta'].sum()
            impostos_total = prods['Impostos'].sum() if 'Impostos' in prods.columns else 0
            
            d1 = [['DASHBOARD GERAL'],
                  [datetime.now().strftime("%d/%m/%Y %H:%M")],[],
                  ['Dias',dias],
                  ['Faturamento',f'R$ {total:,.2f}'],
                  ['Margem Bruta',f'R$ {margem:,.2f}'],
                  ['Impostos',f'R$ {impostos_total:,.2f}'],
                  ['Lucro Líquido',f'R$ {lucro:,.2f}'],
                  ['Margem %',f'{(lucro/total*100):.1f}%'],
                  ['Produtos',len(prods)],[],
                  ['BCG','Qtd','Faturamento','Lucro']]
            
            for cat in ['Estrela','Vaca Leiteira','Interrogação','Abacaxi']:
                pc = prods[prods['BCG']==cat]
                lc = pc['Lucro_Liquido'].sum()
                d1.append([cat, len(pc), f'R$ {pc["Total"].sum():,.2f}', f'R$ {lc:,.2f}'])
            
            sh1.clear()
            sh1.update('A1', d1)
            
            # Análise por CNPJ
            if 'CNPJ' in df_full.columns:
                try: sh_cnpj = ss.worksheet("2. Por CNPJ")
                except: sh_cnpj = ss.add_worksheet("2. Por CNPJ", 100, 8)
                
                cnpj_agg = df_full.groupby('CNPJ').agg({
                    'Total':'sum',
                    'Custo_Total':'sum',
                    'Margem_Bruta':'sum',
                    'Impostos':'sum',
                    'Lucro_Liquido':'sum'
                }).reset_index()
                
                cnpj_agg['Margem %'] = (cnpj_agg['Lucro_Liquido'] / cnpj_agg['Total'] * 100).fillna(0)
                cnpj_agg['Alíquota Efetiva %'] = (cnpj_agg['Impostos'] / cnpj_agg['Total'] * 100).fillna(0)
                
                d_cnpj = [['ANÁLISE POR CNPJ/REGIME'],[],
                          ['Regime','Faturamento','Custo','Margem Bruta','Impostos','Lucro Líquido','Margem %','Alíquota %']]
                
                for _, row in cnpj_agg.iterrows():
                    d_cnpj.append([
                        row['CNPJ'],
                        f"R$ {row['Total']:,.2f}",
                        f"R$ {row['Custo_Total']:,.2f}",
                        f"R$ {row['Margem_Bruta']:,.2f}",
                        f"R$ {row['Impostos']:,.2f}",
                        f"R$ {row['Lucro_Liquido']:,.2f}",
                        f"{row['Margem %']:.1f}%",
                        f"{row['Alíquota Efetiva %']:.1f}%"
                    ])
                
                d_cnpj.append([])
                melhor = cnpj_agg.loc[cnpj_agg['Lucro_Liquido'].idxmax()]
                d_cnpj.append(['RECOMENDAÇÃO'])
                d_cnpj.append([f"Regime mais lucrativo: {melhor['CNPJ']} (Margem {melhor['Margem %']:.1f}%)"])
                
                sh_cnpj.clear()
                sh_cnpj.update('A1', d_cnpj)
            
            # Análise Executiva
            try: sh_exec = ss.worksheet("3. Análise Executiva")
            except: sh_exec = ss.add_worksheet("3. Análise Executiva", 200, 6)
            
            margem_media = (lucro / total * 100) if total > 0 else 0
            ticket_medio = total / len(df_full) if len(df_full) > 0 else 0
            produtos_lucrativos = len(prods[prods['Lucro_Liquido'] > 0])
            produtos_prejuizo = len(prods[prods['Lucro_Liquido'] <= 0])
            
            # Ler metas
            margem_min = 10.0
            margem_ideal = 15.0
            ticket_min = 100.0
            ticket_ideal = 150.0
            
            if 'metas' in st.session_state:
                metas_df = st.session_state['metas']
                for _, m in metas_df.iterrows():
                    if 'Mínima' in m['Indicador'] and 'Margem' in m['Indicador']:
                        margem_min = m['Valor']
                    elif 'Ideal' in m['Indicador'] and 'Margem' in m['Indicador']:
                        margem_ideal = m['Valor']
                    elif 'Mínimo' in m['Indicador'] and 'Ticket' in m['Indicador']:
                        ticket_min = m['Valor']
                    elif 'Ideal' in m['Indicador'] and 'Ticket' in m['Indicador']:
                        ticket_ideal = m['Valor']
            
            def semaforo(valor, meta_min, meta_ideal):
                if valor >= meta_ideal: return '🟢'
                elif valor >= meta_min: return '🟡'
                else: return '🔴'
            
            margem_semaforo = semaforo(margem_media, margem_min, margem_ideal)
            lucro_semaforo = '🟢' if lucro > 0 else '🔴'
            
            top5 = prods.nlargest(5, 'Lucro_Liquido')[['Produto','Lucro_Liquido','BCG']]
            bottom5 = prods.nsmallest(5, 'Lucro_Liquido')[['Produto','Lucro_Liquido','BCG']]
            
            recomendacoes = []
            if produtos_prejuizo > 0:
                recomendacoes.append(f"⚠️ {produtos_prejuizo} produtos em prejuízo - revisar preço ou descontinuar")
            if margem_media < margem_ideal:
                recomendacoes.append(f"📈 Margem {margem_media:.1f}% abaixo da meta ({margem_ideal:.0f}%) - aumentar preços ou reduzir custos")
            
            abacaxis = prods[prods['BCG'] == 'Abacaxi']
            if len(abacaxis) > 0:
                recomendacoes.append(f"🗑️ {len(abacaxis)} produtos 'Abacaxi' - considerar promoção ou descontinuar")
            
            estrelas = prods[prods['BCG'] == 'Estrela']
            if len(estrelas) > 0:
                recomendacoes.append(f"⭐ {len(estrelas)} produtos 'Estrela' - aumentar estoque e investir em marketing")
            
            d_exec = [
                ['ANÁLISE EXECUTIVA - TOMADA DE DECISÃO'],
                [datetime.now().strftime("%d/%m/%Y %H:%M")],
                [],
                ['INDICADORES PRINCIPAIS', 'Valor', 'Meta', 'Status'],
                ['Margem Líquida (%)', f'{margem_media:.1f}%', f'{margem_ideal:.0f}%', margem_semaforo],
                ['Lucro Líquido (R$)', f'R$ {lucro:,.2f}', '> 0', lucro_semaforo],
                ['Ticket Médio (R$)', f'R$ {ticket_medio:.2f}', f'R$ {ticket_ideal:.0f}', semaforo(ticket_medio, ticket_min, ticket_ideal)],
                ['Produtos Lucrativos', produtos_lucrativos, f'{len(prods)}', '🟢' if produtos_lucrativos == len(prods) else '🟡'],
                [],
                ['TOP 5 MAIS LUCRATIVOS'],
                ['Produto', 'Lucro', 'BCG']
            ]
            
            for _, p in top5.iterrows():
                d_exec.append([p['Produto'], f"R$ {p['Lucro_Liquido']:,.2f}", p['BCG']])
            
            d_exec.append([])
            d_exec.append(['TOP 5 MENOS LUCRATIVOS'])
            d_exec.append(['Produto', 'Lucro', 'BCG'])
            
            for _, p in bottom5.iterrows():
                d_exec.append([p['Produto'], f"R$ {p['Lucro_Liquido']:,.2f}", p['BCG']])
            
            d_exec.append([])
            d_exec.append(['RECOMENDAÇÕES ESTRATÉGICAS'])
            
            for rec in recomendacoes:
                d_exec.append([rec])
            
            if not recomendacoes:
                d_exec.append(['✅ Operação saudável - manter estratégia atual'])
            
            sh_exec.clear()
            sh_exec.update('A1', d_exec)
            
            # Detalhes
            cols = ['Data','Produto','Tipo','Qtd','Total','Custo','Lucro','Margem%','Canal','CNPJ','BCG']
            d6 = [cols]
            for _,r in df_full.iterrows():
                cat = prods[prods['Produto']==r['Produto']]['BCG'].values[0] if r['Produto'] in prods['Produto'].values else 'N/A'
                d6.append([
                    str(r.get('Data','')),
                    r['Produto'],
                    r.get('Tipo',''),
                    int(r['Quantidade']),
                    float(r['Total']),
                    float(r.get('Custo_Total',0)),
                    float(r.get('Lucro_Liquido',0)),
                    f"{r.get('Margem_%',0):.1f}%",
                    r.get('Canal',''),
                    r.get('CNPJ',''),
                    cat
                ])
            
            sh.clear()
            sh.update('A1', d6)
            
            st.success(f"✅ {len(df_full)} registros | Lucro: R$ {lucro:,.2f}")
            st.info(f"🔗 [Abrir Google Sheets]({st.secrets['GOOGLE_SHEETS_URL']})")
        except Exception as e:
            st.error(f"❌ {e}")

else:
    if not configs:
        st.info("👈 Faça upload da configuração primeiro")
