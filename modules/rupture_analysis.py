"""
Módulo de Análise de Ruptura de Estoque
Cruza dados de vendas históricas com estoque atual para prever rupturas
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st


class RuptureAnalysis:
    """
    Analisa risco de ruptura de estoque baseado em vendas históricas
    
    Metodologia:
    1. Calcula média de vendas por produto/dia
    2. Compara com estoque atual
    3. Calcula dias de cobertura
    4. Gera alertas por criticidade
    """
    
    def __init__(self, df_vendas=None, df_estoque=None):
        """
        Inicializa análise de ruptura
        
        Args:
            df_vendas: DataFrame com histórico de vendas
            df_estoque: DataFrame com estoque atual
        """
        self.df_vendas = df_vendas if df_vendas is not None else pd.DataFrame()
        self.df_estoque = df_estoque if df_estoque is not None else pd.DataFrame()
    
    def calcular_media_vendas_diaria(self, codigo_produto=None):
        """
        Calcula média de vendas diárias por produto
        
        Args:
            codigo_produto: Código específico (None para todos)
            
        Returns:
            pd.Series ou float: Média de vendas por dia
        """
        if self.df_vendas.empty:
            return pd.Series() if codigo_produto is None else 0.0
        
        # Verificar se tem coluna de data
        if 'Data' not in self.df_vendas.columns:
            # Se não tem data, assumir período de 30 dias
            dias_periodo = 30
        else:
            # Calcular dias únicos no período
            try:
                df_temp = self.df_vendas.copy()
                df_temp['Data'] = pd.to_datetime(df_temp['Data'], errors='coerce')
                dias_periodo = (df_temp['Data'].max() - df_temp['Data'].min()).days + 1
                dias_periodo = max(dias_periodo, 1)  # Mínimo 1 dia
            except:
                dias_periodo = 30
        
        # Agrupar por produto
        if 'Produto' in self.df_vendas.columns:
            col_produto = 'Produto'
        elif 'Código' in self.df_vendas.columns:
            col_produto = 'Código'
        else:
            return pd.Series() if codigo_produto is None else 0.0
        
        # Calcular total vendido por produto
        vendas_por_produto = self.df_vendas.groupby(col_produto)['Quantidade'].sum()
        
        # Calcular média diária
        media_diaria = vendas_por_produto / dias_periodo
        
        if codigo_produto:
            return media_diaria.get(codigo_produto, 0.0)
        
        return media_diaria
    
    def calcular_cobertura(self):
        """
        Calcula dias de cobertura de estoque para cada produto
        
        Fórmula: Dias_Cobertura = Estoque_Atual / Média_Vendas_Diária
        
        Returns:
            pd.DataFrame: Produtos com dias de cobertura calculados
        """
        if self.df_vendas.empty or self.df_estoque.empty:
            return pd.DataFrame()
        
        # Calcular média de vendas
        media_vendas = self.calcular_media_vendas_diaria()
        
        if media_vendas.empty:
            return pd.DataFrame()
        
        # Preparar DataFrame de resultado
        df_resultado = self.df_estoque.copy()
        
        # Normalizar códigos para matching
        from modules.inventory_integration import InventoryIntegration
        inv_int = InventoryIntegration()
        
        # Criar dicionário de média de vendas normalizado
        media_vendas_dict = {}
        for codigo, media in media_vendas.items():
            codigo_norm = inv_int.normalizar_texto(str(codigo))
            media_vendas_dict[codigo_norm] = media
        
        # Adicionar média de vendas ao DataFrame
        df_resultado['codigo_normalizado'] = df_resultado['codigo'].apply(
            lambda x: inv_int.normalizar_texto(str(x))
        )
        
        df_resultado['media_vendas_dia'] = df_resultado['codigo_normalizado'].map(media_vendas_dict).fillna(0)
        
        # Calcular dias de cobertura
        df_resultado['dias_cobertura'] = df_resultado.apply(
            lambda row: row['estoque_atual'] / row['media_vendas_dia'] 
            if row['media_vendas_dia'] > 0 else 999,  # 999 = sem vendas históricas
            axis=1
        )
        
        # Arredondar
        df_resultado['dias_cobertura'] = df_resultado['dias_cobertura'].round(1)
        
        # Classificar criticidade
        df_resultado['alerta'] = df_resultado['dias_cobertura'].apply(self._classificar_alerta)
        
        # Ordenar por criticidade
        ordem_alerta = {'🔴 Crítico': 0, '🟡 Atenção': 1, '🟢 OK': 2, '⚪ Sem Vendas': 3}
        df_resultado['ordem_alerta'] = df_resultado['alerta'].map(ordem_alerta)
        df_resultado = df_resultado.sort_values('ordem_alerta')
        
        return df_resultado
    
    @staticmethod
    def _classificar_alerta(dias_cobertura):
        """
        Classifica nível de alerta baseado em dias de cobertura
        
        Args:
            dias_cobertura: Número de dias de cobertura
            
        Returns:
            str: Classificação do alerta
        """
        if dias_cobertura >= 999:
            return '⚪ Sem Vendas'
        elif dias_cobertura < 3:
            return '🔴 Crítico'
        elif dias_cobertura < 7:
            return '🟡 Atenção'
        else:
            return '🟢 OK'
    
    def alertas_criticos(self, limite_dias=7):
        """
        Retorna produtos com estoque crítico
        
        Args:
            limite_dias: Limite de dias para considerar crítico
            
        Returns:
            pd.DataFrame: Produtos em situação crítica
        """
        df_cobertura = self.calcular_cobertura()
        
        if df_cobertura.empty:
            return pd.DataFrame()
        
        # Filtrar críticos
        df_criticos = df_cobertura[
            (df_cobertura['dias_cobertura'] < limite_dias) & 
            (df_cobertura['dias_cobertura'] < 999)  # Excluir sem vendas
        ].copy()
        
        return df_criticos
    
    def projetar_ruptura(self, dias_futuros=30):
        """
        Projeta quando cada produto terá ruptura de estoque
        
        Args:
            dias_futuros: Número de dias para projetar
            
        Returns:
            pd.DataFrame: Produtos com data prevista de ruptura
        """
        df_cobertura = self.calcular_cobertura()
        
        if df_cobertura.empty:
            return pd.DataFrame()
        
        # Filtrar produtos que vão romper no período
        df_ruptura = df_cobertura[
            (df_cobertura['dias_cobertura'] < dias_futuros) & 
            (df_cobertura['dias_cobertura'] < 999)
        ].copy()
        
        # Calcular data prevista de ruptura
        hoje = datetime.now()
        df_ruptura['data_ruptura_prevista'] = df_ruptura['dias_cobertura'].apply(
            lambda dias: (hoje + timedelta(days=int(dias))).strftime('%d/%m/%Y')
        )
        
        # Calcular quantidade necessária para reposição (30 dias)
        df_ruptura['qtd_reposicao_sugerida'] = (
            df_ruptura['media_vendas_dia'] * 30
        ).round(0).astype(int)
        
        # Calcular valor de reposição
        if 'custo_unitario' in df_ruptura.columns:
            df_ruptura['valor_reposicao'] = (
                df_ruptura['qtd_reposicao_sugerida'] * df_ruptura['custo_unitario']
            ).round(2)
        
        return df_ruptura.sort_values('dias_cobertura')
    
    def analise_comparativa_periodos(self, dias_periodo1=7, dias_periodo2=7):
        """
        Compara vendas entre dois períodos para detectar tendências
        
        Args:
            dias_periodo1: Dias do período mais recente
            dias_periodo2: Dias do período anterior
            
        Returns:
            pd.DataFrame: Análise comparativa por produto
        """
        if self.df_vendas.empty or 'Data' not in self.df_vendas.columns:
            return pd.DataFrame()
        
        try:
            # Preparar dados
            df = self.df_vendas.copy()
            df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
            df = df.dropna(subset=['Data'])
            
            if df.empty:
                return pd.DataFrame()
            
            # Definir períodos
            data_mais_recente = df['Data'].max()
            inicio_periodo1 = data_mais_recente - timedelta(days=dias_periodo1)
            inicio_periodo2 = inicio_periodo1 - timedelta(days=dias_periodo2)
            
            # Filtrar períodos
            df_periodo1 = df[df['Data'] > inicio_periodo1]
            df_periodo2 = df[(df['Data'] > inicio_periodo2) & (df['Data'] <= inicio_periodo1)]
            
            # Agrupar por produto
            col_produto = 'Produto' if 'Produto' in df.columns else 'Código'
            
            vendas_p1 = df_periodo1.groupby(col_produto)['Quantidade'].sum()
            vendas_p2 = df_periodo2.groupby(col_produto)['Quantidade'].sum()
            
            # Criar DataFrame comparativo
            df_comp = pd.DataFrame({
                'vendas_periodo_recente': vendas_p1,
                'vendas_periodo_anterior': vendas_p2
            }).fillna(0)
            
            # Calcular variação
            df_comp['variacao_%'] = (
                ((df_comp['vendas_periodo_recente'] - df_comp['vendas_periodo_anterior']) / 
                 df_comp['vendas_periodo_anterior'].replace(0, 1)) * 100
            ).round(1)
            
            # Classificar tendência
            df_comp['tendencia'] = df_comp['variacao_%'].apply(self._classificar_tendencia)
            
            return df_comp.sort_values('variacao_%', ascending=False)
            
        except Exception as e:
            st.warning(f"Erro na análise comparativa: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def _classificar_tendencia(variacao):
        """
        Classifica tendência de vendas
        
        Args:
            variacao: Variação percentual
            
        Returns:
            str: Classificação da tendência
        """
        if variacao > 50:
            return '📈 Crescimento Forte'
        elif variacao > 20:
            return '↗️ Crescimento'
        elif variacao > -20:
            return '➡️ Estável'
        elif variacao > -50:
            return '↘️ Queda'
        else:
            return '📉 Queda Forte'
    
    def gerar_resumo_executivo(self):
        """
        Gera resumo executivo da situação de estoque
        
        Returns:
            dict: Métricas principais
        """
        resumo = {}
        
        # Calcular cobertura
        df_cobertura = self.calcular_cobertura()
        
        if not df_cobertura.empty:
            # Produtos críticos
            resumo['criticos'] = len(df_cobertura[df_cobertura['alerta'] == '🔴 Crítico'])
            resumo['atencao'] = len(df_cobertura[df_cobertura['alerta'] == '🟡 Atenção'])
            resumo['ok'] = len(df_cobertura[df_cobertura['alerta'] == '🟢 OK'])
            
            # Cobertura média
            df_com_vendas = df_cobertura[df_cobertura['dias_cobertura'] < 999]
            if not df_com_vendas.empty:
                resumo['cobertura_media_dias'] = df_com_vendas['dias_cobertura'].mean().round(1)
            
            # Produtos sem movimento
            resumo['sem_vendas'] = len(df_cobertura[df_cobertura['alerta'] == '⚪ Sem Vendas'])
        
        # Projeção de ruptura
        df_ruptura = self.projetar_ruptura(dias_futuros=30)
        if not df_ruptura.empty:
            resumo['rupturas_30_dias'] = len(df_ruptura)
            if 'valor_reposicao' in df_ruptura.columns:
                resumo['investimento_reposicao'] = df_ruptura['valor_reposicao'].sum().round(2)
        
        return resumo
