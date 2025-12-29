"""
Módulo para análise de produção e decomposição de kits.
Gerencia o fluxo: Vendas → Decomposição → Verificação de Estoque → Relatório
"""

import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import streamlit as st

@dataclass
class ProductNeed:
    """Representa a necessidade de um produto"""
    codigo: str
    quantidade_necessaria: int
    estoque_atual: int = 0
    quantidade_faltante: int = 0
    origem_marketplaces: List[str] = field(default_factory=list)
    
    def add_marketplace(self, marketplace: str, qtd: int):
        """Adiciona necessidade de um marketplace"""
        self.quantidade_necessaria += qtd
        if marketplace not in self.origem_marketplaces:
            self.origem_marketplaces.append(marketplace)
    
    def calcular_faltante(self):
        """Calcula quantidade faltante após verificar estoque"""
        self.quantidade_faltante = max(0, self.quantidade_necessaria - self.estoque_atual)


class ProductionAnalyzer:
    """Analisa vendas e gera necessidades de produção"""
    
    def __init__(self):
        self.produtos_cache = None
        self.kits_cache = None
        self.estoque_cache = None
        
        # Acumulador de necessidades por DIA
        if 'production_needs' not in st.session_state:
            st.session_state.production_needs = {}
        
        if 'current_date' not in st.session_state:
            st.session_state.current_date = datetime.now().strftime('%Y-%m-%d')
        
        if 'marketplace_reports' not in st.session_state:
            st.session_state.marketplace_reports = {}
    
    def reset_daily_analysis(self, date: str = None):
        """Reseta análise para um novo dia"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        st.session_state.current_date = date
        st.session_state.production_needs = {}
        st.session_state.marketplace_reports = {}
    
    def load_produtos(self, df_produtos: pd.DataFrame):
        """Carrega DataFrame de produtos"""
        self.produtos_cache = df_produtos
    
    def load_kits(self, df_kits: pd.DataFrame):
        """Carrega DataFrame de kits"""
        self.kits_cache = df_kits
    
    def load_estoque(self, df_estoque: pd.DataFrame):
        """Carrega DataFrame de estoque"""
        self.estoque_cache = df_estoque
    
    def is_kit(self, codigo: str) -> bool:
        """Verifica se um código é um KIT"""
        if self.kits_cache is None:
            return False
        
        # Normalizar nomes de colunas
        col_codigo = None
        for col in self.kits_cache.columns:
            if 'codigo' in col.lower() and 'kit' in col.lower():
                col_codigo = col
                break
        
        if col_codigo is None:
            return False
        
        return codigo in self.kits_cache[col_codigo].values
    
    def decompose_kit(self, codigo_kit: str) -> List[Tuple[str, int]]:
        """
        Decompõe um KIT em seus componentes.
        
        Returns:
            List[Tuple[str, int]]: Lista de (codigo_produto, quantidade)
        """
        if self.kits_cache is None:
            return []
        
        # Encontrar colunas
        col_codigo, col_skus, col_qtds = None, None, None
        for col in self.kits_cache.columns:
            if 'codigo' in col.lower() and 'kit' in col.lower():
                col_codigo = col
            elif 'sku' in col.lower() and 'componente' in col.lower():
                col_skus = col
            elif 'qtd' in col.lower() and 'componente' in col.lower():
                col_qtds = col
        
        if not all([col_codigo, col_skus, col_qtds]):
            return []
        
        # Buscar o kit
        kit_row = self.kits_cache[self.kits_cache[col_codigo] == codigo_kit]
        if kit_row.empty:
            return []
        
        # Pegar SKUs e quantidades
        skus_str = str(kit_row.iloc[0][col_skus])
        qtds_str = str(kit_row.iloc[0][col_qtds])
        
        # Separar por ;
        skus = [s.strip() for s in skus_str.split(';')]
        qtds = [q.strip() for q in qtds_str.split(';')]
        
        # Garantir mesmo tamanho
        if len(skus) != len(qtds):
            return []
        
        # Converter quantidades para int
        componentes = []
        for sku, qtd in zip(skus, qtds):
            try:
                qtd_int = int(float(qtd.replace(',', '.')))
                componentes.append((sku, qtd_int))
            except:
                componentes.append((sku, 1))  # Default 1 se não conseguir converter
        
        return componentes
    
    def analyze_sales(self, df_vendas: pd.DataFrame, marketplace: str) -> Dict[str, ProductNeed]:
        """
        Analisa um arquivo de vendas e retorna necessidades de produção.
        ACUMULA com vendas anteriores do mesmo dia.
        
        Args:
            df_vendas: DataFrame com colunas ['código', 'quantidade']
            marketplace: Nome do marketplace (ex: 'Mercado Livre')
        
        Returns:
            Dict[str, ProductNeed]: Necessidades acumuladas
        """
        needs = st.session_state.production_needs.copy()
        
        # Processar cada venda
        for _, row in df_vendas.iterrows():
            codigo = str(row['código']).strip() if 'código' in row else str(row['codigo']).strip()
            quantidade = int(row['quantidade'])
            
            # Verificar se é KIT
            if self.is_kit(codigo):
                # Decompor kit
                componentes = self.decompose_kit(codigo)
                for comp_codigo, comp_qtd in componentes:
                    total_qtd = quantidade * comp_qtd
                    
                    if comp_codigo not in needs:
                        needs[comp_codigo] = ProductNeed(
                            codigo=comp_codigo,
                            quantidade_necessaria=0
                        )
                    
                    needs[comp_codigo].add_marketplace(marketplace, total_qtd)
            else:
                # Produto individual
                if codigo not in needs:
                    needs[codigo] = ProductNeed(
                        codigo=codigo,
                        quantidade_necessaria=0
                    )
                
                needs[codigo].add_marketplace(marketplace, quantidade)
        
        # Atualizar session_state
        st.session_state.production_needs = needs
        
        return needs
    
    def check_inventory(self, needs: Dict[str, ProductNeed]) -> Dict[str, ProductNeed]:
        """
        Verifica estoque disponível e calcula faltantes.
        
        Args:
            needs: Dicionário de necessidades
        
        Returns:
            Dict[str, ProductNeed]: Necessidades com estoque verificado
        """
        if self.estoque_cache is None:
            # Sem estoque, tudo é faltante
            for need in needs.values():
                need.estoque_atual = 0
                need.calcular_faltante()
            return needs
        
        # Encontrar coluna de código
        col_codigo = None
        for col in self.estoque_cache.columns:
            if 'codigo' in col.lower():
                col_codigo = col
                break
        
        # Encontrar coluna de estoque atual
        col_estoque = None
        for col in self.estoque_cache.columns:
            if 'estoque' in col.lower() and 'atual' in col.lower():
                col_estoque = col
                break
        
        if col_codigo is None or col_estoque is None:
            # Colunas não encontradas, tudo faltante
            for need in needs.values():
                need.estoque_atual = 0
                need.calcular_faltante()
            return needs
        
        # Verificar estoque de cada produto
        for codigo, need in needs.items():
            estoque_row = self.estoque_cache[self.estoque_cache[col_codigo] == codigo]
            
            if not estoque_row.empty:
                estoque_atual = estoque_row.iloc[0][col_estoque]
                try:
                    need.estoque_atual = int(estoque_atual)
                except:
                    need.estoque_atual = 0
            else:
                need.estoque_atual = 0
            
            need.calcular_faltante()
        
        return needs
    
    def get_marketplace_summary(self, marketplace: str, needs: Dict[str, ProductNeed]) -> pd.DataFrame:
        """
        Gera resumo de necessidades para um marketplace específico.
        
        Args:
            marketplace: Nome do marketplace
            needs: Necessidades totais
        
        Returns:
            DataFrame com produtos deste marketplace
        """
        # Filtrar apenas produtos deste marketplace
        marketplace_needs = {
            codigo: need 
            for codigo, need in needs.items() 
            if marketplace in need.origem_marketplaces
        }
        
        # Criar DataFrame
        rows = []
        for codigo, need in marketplace_needs.items():
            rows.append({
                'Código': codigo,
                'Qtd Necessária': need.quantidade_necessaria,
                'Estoque Atual': need.estoque_atual,
                'Qtd Faltante': need.quantidade_faltante
            })
        
        df = pd.DataFrame(rows)
        return df.sort_values('Qtd Faltante', ascending=False) if not df.empty else df
    
    def get_daily_summary(self, needs: Dict[str, ProductNeed]) -> pd.DataFrame:
        """
        Gera resumo CONSOLIDADO do dia (todos os marketplaces).
        
        Args:
            needs: Necessidades totais acumuladas
        
        Returns:
            DataFrame consolidado
        """
        rows = []
        for codigo, need in needs.items():
            rows.append({
                'Código': codigo,
                'Qtd Necessária': need.quantidade_necessaria,
                'Estoque Atual': need.estoque_atual,
                'Qtd Faltante': need.quantidade_faltante,
                'Marketplaces': ', '.join(need.origem_marketplaces)
            })
        
        df = pd.DataFrame(rows)
        return df.sort_values('Qtd Faltante', ascending=False) if not df.empty else df
