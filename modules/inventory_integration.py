"""
Módulo de Integração com Estoque
Responsável por ler, processar e sincronizar dados entre BCG e template_estoque
"""

import pandas as pd
import requests
from io import StringIO, BytesIO
import streamlit as st
import unicodedata


class InventoryIntegration:
    """
    Classe para gerenciar integração entre planilhas BCG e template_estoque
    
    IMPORTANTE:
    - template_estoque: SOMENTE LEITURA no app (escrita manual por operador)
    - BCG: Leitura e escrita para análises
    - Sincronização: Detecta produtos faltantes e gera Excel para upload manual
    """
    
    # URL da planilha template_estoque
    ESTOQUE_BASE_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
    ESTOQUE_GID = "1456159896"
    
    def __init__(self):
        """Inicializa integração"""
        self.estoque_url = f"{self.ESTOQUE_BASE_URL}&gid={self.ESTOQUE_GID}"
    
    @staticmethod
    def normalizar_decimal(valor):
        """
        Normaliza valores decimais de diferentes formatos
        
        Converte:
        - "7,24" → 7.24
        - "14.9" → 14.9
        - "1.234,56" → 1234.56
        - "1,234.56" → 1234.56
        
        Args:
            valor: String ou número a ser normalizado
            
        Returns:
            float: Valor normalizado
        """
        if pd.isna(valor) or valor == '':
            return 0.0
        
        s = str(valor).strip()
        
        # Remove espaços
        s = s.replace(' ', '')
        
        # Detecta formato
        if ',' in s and '.' in s:
            # Verifica qual é o separador decimal
            pos_virgula = s.rfind(',')
            pos_ponto = s.rfind('.')
            
            if pos_virgula > pos_ponto:
                # Formato brasileiro: 1.234,56
                s = s.replace('.', '').replace(',', '.')
            else:
                # Formato internacional: 1,234.56
                s = s.replace(',', '')
        elif ',' in s:
            # Apenas vírgula - assumir decimal brasileiro
            s = s.replace(',', '.')
        
        try:
            return float(s)
        except:
            return 0.0
    
    @staticmethod
    def normalizar_texto(texto):
        """
        Normaliza texto removendo acentos e convertendo para lowercase
        
        Args:
            texto: String a ser normalizada
            
        Returns:
            str: Texto normalizado
        """
        if pd.isna(texto):
            return ''
        
        texto = str(texto)
        # Remove acentos
        texto = unicodedata.normalize('NFD', texto)
        texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
        return texto.lower().strip()
    
    @st.cache_data(ttl=600)  # Cache por 10 minutos
    def carregar_estoque(_self):
        """
        Carrega dados da planilha template_estoque
        
        Aplica normalizações:
        - Decimais (vírgula → ponto)
        - Textos (lowercase, sem acentos)
        - Tipos de dados corretos
        
        Returns:
            pd.DataFrame: Dados de estoque normalizados
        """
        try:
            # Fazer request
            r = requests.get(_self.estoque_url, timeout=15)
            r.raise_for_status()
            
            # Ler CSV
            df = pd.read_csv(StringIO(r.text))
            
            # Normalizar colunas numéricas
            colunas_numericas = ['estoque_atual', 'estoque_min', 'estoque_max', 'custo_unitario']
            for col in colunas_numericas:
                if col in df.columns:
                    df[col] = df[col].apply(_self.normalizar_decimal)
            
            # Normalizar código para matching
            if 'codigo' in df.columns:
                df['codigo_normalizado'] = df['codigo'].apply(_self.normalizar_texto)
            
            # Converter eh_kit para boolean
            if 'eh_kit' in df.columns:
                df['eh_kit'] = df['eh_kit'].fillna('').astype(str).str.lower().isin(['sim', 'yes', 'true', '1'])
            
            # Preencher valores vazios
            df = df.fillna({
                'componentes': '',
                'quantidades': '',
                'nome': '',
                'categoria': ''
            })
            
            return df
            
        except Exception as e:
            st.error(f"❌ Erro ao carregar estoque: {e}")
            return pd.DataFrame()
    
    def detectar_produtos_faltantes(self, df_bcg, df_estoque):
        """
        Identifica produtos que existem em BCG mas não em template_estoque
        
        Args:
            df_bcg: DataFrame da planilha BCG
            df_estoque: DataFrame da planilha template_estoque
            
        Returns:
            pd.DataFrame: Produtos faltantes com informações da BCG
        """
        # Se DataFrames vazios, retornar vazio
        if df_bcg.empty or df_estoque.empty:
            return pd.DataFrame()
        
        # Detectar coluna de código na BCG (pode ser 'Código', 'codigo', 'Cdigo', etc.)
        col_codigo_bcg = None
        for possivel_col in ['Código', 'Codigo', 'codigo', 'Cdigo', 'CODIGO']:
            if possivel_col in df_bcg.columns:
                col_codigo_bcg = possivel_col
                break
        
        # Se não encontrou coluna de código, retornar vazio
        if col_codigo_bcg is None:
            return pd.DataFrame()
        
        # Normalizar códigos para comparação
        codigos_bcg = set(df_bcg[col_codigo_bcg].apply(self.normalizar_texto))
        
        codigos_estoque = set()
        if 'codigo' in df_estoque.columns:
            codigos_estoque = set(df_estoque['codigo'].apply(self.normalizar_texto))
        
        # Encontrar faltantes
        faltantes_norm = codigos_bcg - codigos_estoque
        
        # Se não há faltantes, retornar vazio
        if not faltantes_norm:
            return pd.DataFrame()
        
        # Filtrar DataFrame original
        df_bcg_norm = df_bcg.copy()
        df_bcg_norm['codigo_normalizado'] = df_bcg_norm[col_codigo_bcg].apply(self.normalizar_texto)
        
        df_faltantes = df_bcg_norm[df_bcg_norm['codigo_normalizado'].isin(faltantes_norm)].copy()
        
        return df_faltantes
    
    def gerar_excel_para_upload(self, df_faltantes):
        """
        Gera arquivo Excel formatado para upload em template_estoque
        
        Formato:
        - codigo: Código do produto (da BCG)
        - nome: Nome descritivo
        - categoria: "Produtos BCG" (padrão)
        - estoque_atual: 0
        - estoque_min: 0
        - estoque_max: 0
        - custo_unitario: Custo da BCG
        - eh_kit: (vazio)
        - componentes: (vazio)
        - quantidades: (vazio)
        
        Args:
            df_faltantes: DataFrame com produtos faltantes da BCG
            
        Returns:
            BytesIO: Arquivo Excel em memória
        """
        if df_faltantes.empty:
            return None
        
        # Detectar coluna de código
        col_codigo = None
        for possivel_col in ['Código', 'Codigo', 'codigo', 'Cdigo', 'CODIGO']:
            if possivel_col in df_faltantes.columns:
                col_codigo = possivel_col
                break
        
        if col_codigo is None:
            return None
        
        # Detectar coluna de custo
        col_custo = None
        for possivel_col in ['Custo (R$)', 'Custo', 'custo', 'custo_unitario']:
            if possivel_col in df_faltantes.columns:
                col_custo = possivel_col
                break
        
        # Criar DataFrame no formato template_estoque
        df_upload = pd.DataFrame({
            'codigo': df_faltantes[col_codigo].values,
            'nome': df_faltantes[col_codigo].apply(lambda x: f"Produto {x}").values,  # Nome genérico
            'categoria': 'Produtos BCG',
            'estoque_atual': 0,
            'estoque_min': 0,
            'estoque_max': 0,
            'custo_unitario': df_faltantes[col_custo].apply(self.normalizar_decimal).values if col_custo else 0,
            'eh_kit': '',
            'componentes': '',
            'quantidades': ''
        })
        
        # Gerar Excel em memória
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_upload.to_excel(writer, sheet_name='Produtos_Faltantes', index=False)
            
            # Formatar
            workbook = writer.book
            worksheet = writer.sheets['Produtos_Faltantes']
            
            # Formato de cabeçalho
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1
            })
            
            # Aplicar formato ao cabeçalho
            for col_num, col_name in enumerate(df_upload.columns):
                worksheet.write(0, col_num, col_name, header_format)
                
            # Ajustar largura das colunas
            worksheet.set_column('A:A', 30)  # codigo
            worksheet.set_column('B:B', 35)  # nome
            worksheet.set_column('C:C', 20)  # categoria
            worksheet.set_column('D:G', 15)  # estoques e custo
            worksheet.set_column('H:J', 20)  # kit e componentes
        
        output.seek(0)
        return output
    
    def calcular_estatisticas_estoque(self, df_estoque):
        """
        Calcula estatísticas gerais do estoque
        
        Args:
            df_estoque: DataFrame do estoque
            
        Returns:
            dict: Estatísticas calculadas
        """
        stats = {}
        
        if df_estoque.empty:
            return stats
        
        # Total de produtos
        stats['total_produtos'] = len(df_estoque)
        
        # Produtos com estoque
        stats['produtos_com_estoque'] = len(df_estoque[df_estoque['estoque_atual'] > 0])
        stats['produtos_sem_estoque'] = len(df_estoque[df_estoque['estoque_atual'] == 0])
        
        # Produtos abaixo do mínimo
        if 'estoque_min' in df_estoque.columns:
            stats['produtos_abaixo_minimo'] = len(
                df_estoque[df_estoque['estoque_atual'] < df_estoque['estoque_min']]
            )
        
        # Valor total em estoque
        if 'custo_unitario' in df_estoque.columns:
            stats['valor_total_estoque'] = (
                df_estoque['estoque_atual'] * df_estoque['custo_unitario']
            ).sum()
        
        # Produtos que são kits
        if 'eh_kit' in df_estoque.columns:
            stats['total_kits'] = df_estoque['eh_kit'].sum()
        
        # Categorias
        if 'categoria' in df_estoque.columns:
            stats['categorias'] = df_estoque['categoria'].nunique()
            stats['distribuicao_categorias'] = df_estoque['categoria'].value_counts().to_dict()
        
        return stats
