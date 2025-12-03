import pandas as pd
import plotly.graph_objects as go
import numpy as np

class BCGAnalysis:
    def __init__(self, data):
        self.data = data
    
    def analyze(self):
        """
        Realiza análise da Matriz BCG
        Retorna DataFrame com classificação dos produtos
        """
        # Agrupar por produto
        df_produtos = self.data.groupby('Produto').agg({
            'Quantidade': 'sum',
            'Data': ['min', 'max']
        }).reset_index()
        
        df_produtos.columns = ['Produto', 'Quantidade', 'Data_Inicio', 'Data_Fim']
        
        # Calcular participação de mercado
        total_vendas = df_produtos['Quantidade'].sum()
        df_produtos['Participacao_%'] = (df_produtos['Quantidade'] / total_vendas * 100).round(2)
        
        # Calcular crescimento (simplificado - comparar primeira e segunda metade do período)
        df_produtos['Crescimento_%'] = 0.0
        
        for idx, row in df_produtos.iterrows():
            produto = row['Produto']
            df_produto = self.data[self.data['Produto'] == produto].copy()
            df_produto['Data'] = pd.to_datetime(df_produto['Data'])
            df_produto = df_produto.sort_values('Data')
            
            # Dividir em duas metades
            mid_point = len(df_produto) // 2
            if mid_point > 0:
                vendas_primeira_metade = df_produto.iloc[:mid_point]['Quantidade'].sum()
                vendas_segunda_metade = df_produto.iloc[mid_point:]['Quantidade'].sum()
                
                if vendas_primeira_metade > 0:
                    crescimento = ((vendas_segunda_metade - vendas_primeira_metade) / vendas_primeira_metade * 100)
                    df_produtos.at[idx, 'Crescimento_%'] = round(crescimento, 2)
        
        # Calcular medianas para classificação
        mediana_participacao = df_produtos['Participacao_%'].median()
        mediana_crescimento = df_produtos['Crescimento_%'].median()
        
        # Classificar produtos
        def classificar(row):
            if row['Participacao_%'] >= mediana_participacao and row['Crescimento_%'] >= mediana_crescimento:
                return 'Estrela'
            elif row['Participacao_%'] >= mediana_participacao and row['Crescimento_%'] < mediana_crescimento:
                return 'Vaca Leiteira'
            elif row['Participacao_%'] < mediana_participacao and row['Crescimento_%'] >= mediana_crescimento:
                return 'Interrogação'
            else:
                return 'Abacaxi'
        
        df_produtos['Categoria'] = df_produtos.apply(classificar, axis=1)
        
        return df_produtos.sort_values('Quantidade', ascending=False)
    
    def plot_bcg_matrix(self, bcg_results):
        """
        Cria gráfico da Matriz BCG
        """
        # Cores por categoria
        colors = {
            'Estrela': '#FFD700',
            'Vaca Leiteira': '#90EE90',
            'Interrogação': '#87CEEB',
            'Abacaxi': '#FF6347'
        }
        
        fig = go.Figure()
        
        for categoria in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
            df_cat = bcg_results[bcg_results['Categoria'] == categoria]
            
            fig.add_trace(go.Scatter(
                x=df_cat['Participacao_%'],
                y=df_cat['Crescimento_%'],
                mode='markers+text',
                name=categoria,
                marker=dict(
                    size=df_cat['Quantidade'] / df_cat['Quantidade'].max() * 50 + 10,
                    color=colors[categoria],
                    line=dict(width=2, color='white')
                ),
                text=df_cat['Produto'].str[:15],
                textposition='top center',
                textfont=dict(size=9),
                hovertemplate='<b>%{text}</b><br>' +
                             'Participação: %{x:.1f}%<br>' +
                             'Crescimento: %{y:.1f}%<br>' +
                             '<extra></extra>'
            ))
        
        # Adicionar linhas de referência
        mediana_participacao = bcg_results['Participacao_%'].median()
        mediana_crescimento = bcg_results['Crescimento_%'].median()
        
        fig.add_hline(y=mediana_crescimento, line_dash="dash", line_color="gray", opacity=0.5)
        fig.add_vline(x=mediana_participacao, line_dash="dash", line_color="gray", opacity=0.5)
        
        fig.update_layout(
            title='Matriz BCG - Classificação de Produtos',
            xaxis_title='Participação de Mercado (%)',
            yaxis_title='Taxa de Crescimento (%)',
            hovermode='closest',
            height=600,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            plot_bgcolor='rgba(240,240,240,0.5)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
