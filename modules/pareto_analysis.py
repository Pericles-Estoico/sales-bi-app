import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

class ParetoAnalysis:
    def __init__(self, data):
        self.data = data
    
    def analyze(self):
        """
        Realiza análise de Pareto (80/20)
        Retorna DataFrame ordenado com percentuais acumulados
        """
        # Agrupar por produto e somar quantidades
        df_pareto = self.data.groupby('Produto')['Quantidade'].sum().reset_index()
        
        # Ordenar por quantidade decrescente
        df_pareto = df_pareto.sort_values('Quantidade', ascending=False).reset_index(drop=True)
        
        # Calcular percentuais
        total = df_pareto['Quantidade'].sum()
        df_pareto['Percentual'] = (df_pareto['Quantidade'] / total * 100).round(2)
        df_pareto['Percentual_Acumulado'] = df_pareto['Percentual'].cumsum().round(2)
        
        # Identificar produtos que compõem 80% das vendas
        df_pareto['Classificacao'] = df_pareto['Percentual_Acumulado'].apply(
            lambda x: 'Top 80%' if x <= 80 else 'Outros 20%'
        )
        
        return df_pareto
    
    def plot_pareto(self, pareto_results):
        """
        Cria gráfico de Pareto
        """
        # Criar subplots com eixos secundários
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Barras de quantidade
        fig.add_trace(
            go.Bar(
                x=pareto_results.index + 1,
                y=pareto_results['Quantidade'],
                name='Quantidade',
                marker_color='#1f77b4',
                hovertemplate='<b>%{text}</b><br>' +
                             'Quantidade: %{y:,.0f}<br>' +
                             '<extra></extra>',
                text=pareto_results['Produto']
            ),
            secondary_y=False
        )
        
        # Linha de percentual acumulado
        fig.add_trace(
            go.Scatter(
                x=pareto_results.index + 1,
                y=pareto_results['Percentual_Acumulado'],
                name='% Acumulado',
                mode='lines+markers',
                line=dict(color='#ff7f0e', width=3),
                marker=dict(size=6),
                hovertemplate='% Acumulado: %{y:.1f}%<br>' +
                             '<extra></extra>'
            ),
            secondary_y=True
        )
        
        # Linha de referência 80%
        fig.add_hline(
            y=80,
            line_dash="dash",
            line_color="red",
            opacity=0.7,
            secondary_y=True,
            annotation_text="80%",
            annotation_position="right"
        )
        
        # Layout
        fig.update_xaxes(title_text="Ranking de Produtos")
        fig.update_yaxes(title_text="Quantidade Vendida", secondary_y=False)
        fig.update_yaxes(title_text="Percentual Acumulado (%)", secondary_y=True, range=[0, 105])
        
        fig.update_layout(
            title='Análise de Pareto - Princípio 80/20',
            hovermode='x unified',
            height=500,
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
    
    def get_insights(self, pareto_results):
        """
        Retorna insights da análise de Pareto
        """
        top_80 = pareto_results[pareto_results['Percentual_Acumulado'] <= 80]
        
        insights = {
            'total_produtos': len(pareto_results),
            'produtos_top_80': len(top_80),
            'percentual_produtos_top': round(len(top_80) / len(pareto_results) * 100, 1),
            'vendas_top_80': top_80['Quantidade'].sum(),
            'percentual_vendas_top': round(top_80['Quantidade'].sum() / pareto_results['Quantidade'].sum() * 100, 1)
        }
        
        return insights
