import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class StockProjection:
    def __init__(self, df_vendas):
        self.df_vendas = df_vendas
        
    def projetar_estoque(self, dias=30):
        """Projeta necessidade de estoque para os próximos X dias"""
        if self.df_vendas.empty:
            return pd.DataFrame()
        
        # Calcular média de vendas por dia
        vendas_por_dia = self.df_vendas.groupby('Data')['Quantidade'].sum()
        media_diaria = vendas_por_dia.mean()
        
        # Calcular média por produto
        vendas_por_produto = self.df_vendas.groupby('Produto')['Quantidade'].sum()
        total_vendas = vendas_por_produto.sum()
        
        # Calcular proporção de cada produto
        proporcao = vendas_por_produto / total_vendas
        
        # Projetar para os próximos dias
        projecao_total = media_diaria * dias
        
        # Distribuir por produto
        projecao_por_produto = (projecao_total * proporcao).round().astype(int)
        
        # Criar DataFrame de resultado
        df_projecao = pd.DataFrame({
            'Produto': projecao_por_produto.index,
            'Vendas_Historicas': vendas_por_produto.values,
            'Media_Diaria': (vendas_por_produto / len(vendas_por_dia)).round(2).values,
            f'Projecao_{dias}_dias': projecao_por_produto.values
        })
        
        return df_projecao.sort_values(f'Projecao_{dias}_dias', ascending=False)
    
    def calcular_tendencia(self):
        """Calcula tendência de crescimento/queda"""
        if self.df_vendas.empty or len(self.df_vendas['Data'].unique()) < 2:
            return pd.DataFrame()
        
        # Agrupar por data e produto
        vendas_temporal = self.df_vendas.groupby(['Data', 'Produto'])['Quantidade'].sum().reset_index()
        
        resultados = []
        for produto in vendas_temporal['Produto'].unique():
            df_produto = vendas_temporal[vendas_temporal['Produto'] == produto].sort_values('Data')
            
            if len(df_produto) < 2:
                continue
            
            # Calcular crescimento simples
            primeira_metade = df_produto.iloc[:len(df_produto)//2]['Quantidade'].mean()
            segunda_metade = df_produto.iloc[len(df_produto)//2:]['Quantidade'].mean()
            
            if primeira_metade > 0:
                crescimento = ((segunda_metade - primeira_metade) / primeira_metade) * 100
            else:
                crescimento = 0
            
            # Classificar tendência
            if crescimento > 20:
                tendencia = "📈 Forte Crescimento"
            elif crescimento > 5:
                tendencia = "↗️ Crescimento"
            elif crescimento > -5:
                tendencia = "➡️ Estável"
            elif crescimento > -20:
                tendencia = "↘️ Queda"
            else:
                tendencia = "📉 Forte Queda"
            
            resultados.append({
                'Produto': produto,
                'Crescimento_%': round(crescimento, 2),
                'Tendencia': tendencia,
                'Media_Inicial': round(primeira_metade, 2),
                'Media_Recente': round(segunda_metade, 2)
            })
        
        return pd.DataFrame(resultados).sort_values('Crescimento_%', ascending=False)
    
    def alertas_ruptura(self, estoque_atual=None, dias_cobertura=7):
        """Gera alertas de possível ruptura de estoque"""
        projecao = self.projetar_estoque(dias=dias_cobertura)
        
        if projecao.empty:
            return pd.DataFrame()
        
        if estoque_atual is None:
            # Se não tiver estoque atual, usar média histórica como referência
            estoque_atual = projecao['Vendas_Historicas'] * 0.5
        
        projecao['Estoque_Atual'] = estoque_atual
        projecao['Dias_Cobertura'] = (projecao['Estoque_Atual'] / projecao['Media_Diaria']).round(1)
        
        # Classificar alerta
        def classificar_alerta(dias):
            if dias < 3:
                return "🔴 Crítico"
            elif dias < 7:
                return "🟡 Atenção"
            else:
                return "🟢 OK"
        
        projecao['Alerta'] = projecao['Dias_Cobertura'].apply(classificar_alerta)
        
        return projecao.sort_values('Dias_Cobertura')
