import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
from datetime import datetime, timedelta

class StockProjection:
    def __init__(self, data):
        self.data = data
        self.data['Data'] = pd.to_datetime(self.data['Data'])
    
    def project(self, days=30, confidence=0.95):
        """
        Projeta vendas futuras usando média móvel e tendência linear
        """
        # Agrupar por data
        df_daily = self.data.groupby('Data')['Quantidade'].sum().reset_index()
        df_daily = df_daily.sort_values('Data')
        
        # Calcular média móvel (7 dias)
        df_daily['MA7'] = df_daily['Quantidade'].rolling(window=7, min_periods=1).mean()
        
        # Calcular tendência linear
        x = np.arange(len(df_daily))
        y = df_daily['Quantidade'].values
        
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        # Projetar para os próximos dias
        last_date = df_daily['Data'].max()
        future_dates = [last_date + timedelta(days=i) for i in range(1, days + 1)]
        future_x = np.arange(len(df_daily), len(df_daily) + days)
        
        # Projeção com tendência
        future_y = slope * future_x + intercept
        
        # Calcular intervalo de confiança
        std_dev = df_daily['Quantidade'].std()
        z_score = stats.norm.ppf((1 + confidence) / 2)
        margin = z_score * std_dev
        
        # Criar DataFrame de projeção
        df_projection = pd.DataFrame({
            'Data': future_dates,
            'Projecao': future_y,
            'Limite_Superior': future_y + margin,
            'Limite_Inferior': np.maximum(future_y - margin, 0)  # Não pode ser negativo
        })
        
        # Adicionar dados históricos
        df_historical = df_daily[['Data', 'Quantidade']].copy()
        df_historical['Tipo'] = 'Histórico'
        
        df_projection['Tipo'] = 'Projeção'
        df_projection['Quantidade'] = df_projection['Projecao']
        
        return df_historical, df_projection
    
    def plot_projection(self, projection_data):
        """
        Cria gráfico de projeção de vendas
        """
        df_historical, df_projection = projection_data
        
        fig = go.Figure()
        
        # Dados históricos
        fig.add_trace(go.Scatter(
            x=df_historical['Data'],
            y=df_historical['Quantidade'],
            mode='lines+markers',
            name='Vendas Reais',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=6)
        ))
        
        # Projeção
        fig.add_trace(go.Scatter(
            x=df_projection['Data'],
            y=df_projection['Projecao'],
            mode='lines+markers',
            name='Projeção',
            line=dict(color='#ff7f0e', width=2, dash='dash'),
            marker=dict(size=6)
        ))
        
        # Intervalo de confiança
        fig.add_trace(go.Scatter(
            x=df_projection['Data'].tolist() + df_projection['Data'].tolist()[::-1],
            y=df_projection['Limite_Superior'].tolist() + df_projection['Limite_Inferior'].tolist()[::-1],
            fill='toself',
            fillcolor='rgba(255,127,14,0.2)',
            line=dict(color='rgba(255,255,255,0)'),
            name='Intervalo de Confiança',
            showlegend=True
        ))
        
        fig.update_layout(
            title='Projeção de Vendas',
            xaxis_title='Data',
            yaxis_title='Quantidade',
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
    
    def get_alerts(self, projection_data):
        """
        Gera alertas baseados nas projeções
        """
        df_historical, df_projection = projection_data
        
        alerts = []
        
        # Calcular média histórica
        media_historica = df_historical['Quantidade'].mean()
        
        # Verificar projeções
        for idx, row in df_projection.iterrows():
            if row['Projecao'] < media_historica * 0.5:
                alerts.append({
                    'Data': row['Data'],
                    'Produto': 'Geral',
                    'Tipo': 'Crítico',
                    'Mensagem': f"Projeção de vendas muito abaixo da média ({row['Projecao']:.0f} vs {media_historica:.0f})"
                })
            elif row['Projecao'] < media_historica * 0.7:
                alerts.append({
                    'Data': row['Data'],
                    'Produto': 'Geral',
                    'Tipo': 'Atenção',
                    'Mensagem': f"Projeção de vendas abaixo da média ({row['Projecao']:.0f} vs {media_historica:.0f})"
                })
        
        return pd.DataFrame(alerts)
    
    def project_by_product(self, product, days=30):
        """
        Projeta vendas para um produto específico
        """
        df_product = self.data[self.data['Produto'] == product].copy()
        
        if df_product.empty:
            return None
        
        # Agrupar por data
        df_daily = df_product.groupby('Data')['Quantidade'].sum().reset_index()
        df_daily = df_daily.sort_values('Data')
        
        # Calcular média diária
        media_diaria = df_daily['Quantidade'].mean()
        
        # Projetar estoque necessário
        estoque_projetado = media_diaria * days
        
        return {
            'produto': product,
            'media_diaria': round(media_diaria, 2),
            'estoque_7_dias': round(media_diaria * 7, 0),
            'estoque_15_dias': round(media_diaria * 15, 0),
            'estoque_30_dias': round(media_diaria * 30, 0),
            'estoque_60_dias': round(media_diaria * 60, 0)
        }
