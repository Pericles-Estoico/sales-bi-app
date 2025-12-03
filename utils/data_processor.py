import pandas as pd
from datetime import datetime

class DataProcessor:
    def __init__(self):
        self.required_columns = ['Produto', 'Quantidade', 'Data']
    
    def load_data(self, file):
        """
        Carrega e processa arquivo de vendas
        Suporta Excel (.xlsx, .xls) e CSV
        """
        try:
            # Detectar tipo de arquivo
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            # Normalizar nomes de colunas
            df.columns = df.columns.str.strip().str.title()
            
            # Tentar identificar colunas automaticamente
            df = self._identify_columns(df)
            
            # Validar colunas necessárias
            if not all(col in df.columns for col in self.required_columns):
                raise ValueError(f"Arquivo deve conter as colunas: {', '.join(self.required_columns)}")
            
            # Processar dados
            df = self._process_data(df)
            
            return df
        
        except Exception as e:
            raise Exception(f"Erro ao processar arquivo: {str(e)}")
    
    def _identify_columns(self, df):
        """
        Identifica colunas automaticamente baseado em padrões comuns
        """
        column_mapping = {}
        
        for col in df.columns:
            col_lower = col.lower()
            
            # Identificar coluna de produto
            if any(term in col_lower for term in ['produto', 'item', 'descricao', 'description']):
                column_mapping[col] = 'Produto'
            
            # Identificar coluna de quantidade
            elif any(term in col_lower for term in ['quantidade', 'qtd', 'qty', 'quantity', 'vendas']):
                column_mapping[col] = 'Quantidade'
            
            # Identificar coluna de data
            elif any(term in col_lower for term in ['data', 'date', 'dia']):
                column_mapping[col] = 'Data'
        
        # Renomear colunas
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        return df
    
    def _process_data(self, df):
        """
        Processa e limpa os dados
        """
        # Remover linhas com valores nulos nas colunas essenciais
        df = df.dropna(subset=self.required_columns)
        
        # Converter quantidade para numérico
        df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce')
        df = df[df['Quantidade'] > 0]
        
        # Converter data
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        
        # Se não houver data, usar data atual
        if df['Data'].isna().all():
            df['Data'] = datetime.now()
        
        # Remover duplicatas
        df = df.drop_duplicates()
        
        # Ordenar por data
        df = df.sort_values('Data')
        
        return df
    
    def aggregate_data(self, df, by='Produto'):
        """
        Agrega dados por produto ou outra dimensão
        """
        if by not in df.columns:
            raise ValueError(f"Coluna '{by}' não encontrada no DataFrame")
        
        df_agg = df.groupby(by).agg({
            'Quantidade': 'sum',
            'Data': ['min', 'max', 'count']
        }).reset_index()
        
        df_agg.columns = [by, 'Total_Vendas', 'Primeira_Venda', 'Ultima_Venda', 'Num_Vendas']
        
        return df_agg
    
    def filter_by_date(self, df, start_date=None, end_date=None):
        """
        Filtra dados por período
        """
        df_filtered = df.copy()
        
        if start_date:
            df_filtered = df_filtered[df_filtered['Data'] >= pd.to_datetime(start_date)]
        
        if end_date:
            df_filtered = df_filtered[df_filtered['Data'] <= pd.to_datetime(end_date)]
        
        return df_filtered
    
    def get_summary_stats(self, df):
        """
        Retorna estatísticas resumidas dos dados
        """
        stats = {
            'total_vendas': df['Quantidade'].sum(),
            'media_vendas': df['Quantidade'].mean(),
            'mediana_vendas': df['Quantidade'].median(),
            'total_produtos': df['Produto'].nunique(),
            'periodo_inicio': df['Data'].min(),
            'periodo_fim': df['Data'].max(),
            'num_dias': (df['Data'].max() - df['Data'].min()).days + 1
        }
        
        return stats
