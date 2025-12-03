import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

class ProfitabilityAnalysis:
    def __init__(self, sales_data, product_costs, channel_fees):
        """
        Inicializa análise de rentabilidade
        
        Args:
            sales_data: DataFrame com vendas
            product_costs: Dict com custos por produto
            channel_fees: Dict com taxas por canal
        """
        self.sales_data = sales_data
        self.product_costs = product_costs
        self.channel_fees = channel_fees
    
    def calculate_profitability(self):
        """
        Calcula rentabilidade por produto e canal
        """
        df = self.sales_data.copy()
        
        # Adicionar custo do produto
        df['Custo_Unitario'] = df['Produto'].map(self.product_costs.get('custos', {}))
        df['Preco_Venda'] = df['Produto'].map(self.product_costs.get('precos', {}))
        
        # Adicionar taxas do canal
        df['Taxa_Variavel_%'] = df['Canal'].map(
            lambda x: self.channel_fees.get(x, {}).get('taxa_variavel', 0)
        )
        df['Taxa_Fixa'] = df['Canal'].map(
            lambda x: self.channel_fees.get(x, {}).get('taxa_fixa', 0)
        )
        
        # Calcular valores
        df['Receita_Bruta'] = df['Quantidade'] * df['Preco_Venda']
        df['Custo_Total'] = df['Quantidade'] * df['Custo_Unitario']
        df['Taxa_Variavel_Valor'] = df['Receita_Bruta'] * (df['Taxa_Variavel_%'] / 100)
        df['Taxa_Total'] = df['Taxa_Variavel_Valor'] + (df['Quantidade'] * df['Taxa_Fixa'])
        
        # Lucro
        df['Lucro_Bruto'] = df['Receita_Bruta'] - df['Custo_Total']
        df['Lucro_Liquido'] = df['Lucro_Bruto'] - df['Taxa_Total']
        df['Margem_Liquida_%'] = (df['Lucro_Liquido'] / df['Receita_Bruta'] * 100).round(2)
        
        return df
    
    def get_top_products_by_channel(self, profitability_df):
        """
        Retorna produtos destaque por canal
        """
        results = {}
        
        for canal in profitability_df['Canal'].unique():
            df_canal = profitability_df[profitability_df['Canal'] == canal]
            
            # Agrupar por produto
            df_produtos = df_canal.groupby('Produto').agg({
                'Quantidade': 'sum',
                'Receita_Bruta': 'sum',
                'Lucro_Liquido': 'sum',
                'Margem_Liquida_%': 'mean'
            }).reset_index()
            
            # Ordenar por lucro líquido
            df_produtos = df_produtos.sort_values('Lucro_Liquido', ascending=False)
            
            results[canal] = df_produtos.head(10)
        
        return results
    
    def get_channel_summary(self, profitability_df):
        """
        Resumo de rentabilidade por canal
        """
        summary = profitability_df.groupby('Canal').agg({
            'Quantidade': 'sum',
            'Receita_Bruta': 'sum',
            'Custo_Total': 'sum',
            'Taxa_Total': 'sum',
            'Lucro_Liquido': 'sum',
            'Margem_Liquida_%': 'mean'
        }).reset_index()
        
        summary = summary.sort_values('Lucro_Liquido', ascending=False)
        
        return summary
    
    def plot_profitability_by_channel(self, summary_df):
        """
        Gráfico de rentabilidade por canal
        """
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            name='Receita Bruta',
            x=summary_df['Canal'],
            y=summary_df['Receita_Bruta'],
            marker_color='#1f77b4'
        ))
        
        fig.add_trace(go.Bar(
            name='Custo Total',
            x=summary_df['Canal'],
            y=summary_df['Custo_Total'],
            marker_color='#ff7f0e'
        ))
        
        fig.add_trace(go.Bar(
            name='Taxas',
            x=summary_df['Canal'],
            y=summary_df['Taxa_Total'],
            marker_color='#d62728'
        ))
        
        fig.add_trace(go.Bar(
            name='Lucro Líquido',
            x=summary_df['Canal'],
            y=summary_df['Lucro_Liquido'],
            marker_color='#2ca02c'
        ))
        
        fig.update_layout(
            title='Análise de Rentabilidade por Canal',
            xaxis_title='Canal',
            yaxis_title='Valor (R$)',
            barmode='group',
            height=500,
            hovermode='x unified'
        )
        
        return fig
    
    def plot_margin_comparison(self, summary_df):
        """
        Comparação de margem entre canais
        """
        fig = px.bar(
            summary_df,
            x='Canal',
            y='Margem_Liquida_%',
            title='Margem Líquida por Canal',
            color='Margem_Liquida_%',
            color_continuous_scale='RdYlGn',
            text='Margem_Liquida_%'
        )
        
        fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig.update_layout(height=400)
        
        return fig
