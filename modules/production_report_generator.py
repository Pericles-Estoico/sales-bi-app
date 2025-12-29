"""
Gerador de relatórios de produção em formato Excel.
Formato igual ao "exemplo de entrega.xlsx".
"""

import pandas as pd
from typing import Dict
from io import BytesIO
from modules.production_analyzer import ProductNeed

class ProductionReportGenerator:
    """Gera relatórios de produção em Excel"""
    
    def __init__(self):
        pass
    
    def generate_marketplace_report(
        self, 
        marketplace: str, 
        date: str,
        needs: Dict[str, ProductNeed]
    ) -> BytesIO:
        """
        Gera relatório por marketplace em Excel.
        
        Args:
            marketplace: Nome do marketplace
            date: Data das vendas
            needs: Necessidades de produção
        
        Returns:
            BytesIO: Arquivo Excel em memória
        """
        # Filtrar apenas produtos deste marketplace
        marketplace_needs = {
            codigo: need 
            for codigo, need in needs.items() 
            if marketplace in need.origem_marketplaces
        }
        
        # Preparar dados
        rows = []
        for codigo, need in sorted(
            marketplace_needs.items(), 
            key=lambda x: x[1].quantidade_faltante, 
            reverse=True
        ):
            if need.quantidade_faltante > 0:
                rows.append({
                    'Item': codigo,
                    'Quantidade': need.quantidade_faltante,
                    'Check': ''  # Coluna vazia para marcar quando produzir
                })
        
        # Criar DataFrame
        df = pd.DataFrame(rows)
        
        # Criar arquivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Adicionar título
            df_title = pd.DataFrame([
                [f'RELATÓRIO DE PRODUÇÃO - {marketplace.upper()}'],
                [f'Data: {date}'],
                [''],
                ['PRODUTOS FALTANTES']
            ])
            df_title.to_excel(writer, sheet_name='Produção', index=False, header=False)
            
            # Adicionar dados a partir da linha 5
            df.to_excel(writer, sheet_name='Produção', index=False, startrow=5)
        
        output.seek(0)
        return output
    
    def generate_daily_consolidated_report(
        self, 
        date: str,
        needs: Dict[str, ProductNeed],
        marketplace_names: list
    ) -> BytesIO:
        """
        Gera relatório CONSOLIDADO do dia (todos os marketplaces).
        
        Args:
            date: Data das vendas
            needs: Necessidades totais acumuladas
            marketplace_names: Lista de marketplaces processados
        
        Returns:
            BytesIO: Arquivo Excel em memória
        """
        # Preparar dados
        rows = []
        for codigo, need in sorted(
            needs.items(), 
            key=lambda x: x[1].quantidade_faltante, 
            reverse=True
        ):
            if need.quantidade_faltante > 0:
                rows.append({
                    'Item': codigo,
                    'Quantidade': need.quantidade_faltante,
                    'Marketplaces': ', '.join(need.origem_marketplaces),
                    'Check': ''  # Coluna vazia para marcar quando produzir
                })
        
        # Criar DataFrame
        df = pd.DataFrame(rows)
        
        # Criar arquivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Adicionar título
            df_title = pd.DataFrame([
                ['RELATÓRIO CONSOLIDADO DE PRODUÇÃO DO DIA'],
                [f'Data: {date}'],
                [f'Marketplaces: {", ".join(marketplace_names)}'],
                [''],
                ['PRODUTOS FALTANTES - ORDEM DE PRODUÇÃO']
            ])
            df_title.to_excel(writer, sheet_name='Consolidado', index=False, header=False)
            
            # Adicionar dados a partir da linha 6
            df.to_excel(writer, sheet_name='Consolidado', index=False, startrow=6)
            
            # Adicionar resumo por marketplace
            startrow = 6 + len(df) + 3
            df_summary = pd.DataFrame([
                [''],
                ['RESUMO POR MARKETPLACE']
            ])
            df_summary.to_excel(writer, sheet_name='Consolidado', index=False, header=False, startrow=startrow)
            
            # Para cada marketplace, mostrar resumo
            current_row = startrow + 3
            for mktp in marketplace_names:
                mktp_needs = {
                    codigo: need 
                    for codigo, need in needs.items() 
                    if mktp in need.origem_marketplaces and need.quantidade_faltante > 0
                }
                
                total_items = len(mktp_needs)
                total_units = sum(need.quantidade_faltante for need in mktp_needs.values())
                
                df_mktp = pd.DataFrame([
                    [f'📦 {mktp}'],
                    [f'Total de itens faltantes: {total_items}'],
                    [f'Total de unidades a produzir: {total_units}']
                ])
                df_mktp.to_excel(writer, sheet_name='Consolidado', index=False, header=False, startrow=current_row)
                current_row += 4
        
        output.seek(0)
        return output
    
    def generate_summary_dataframe(
        self, 
        needs: Dict[str, ProductNeed]
    ) -> pd.DataFrame:
        """
        Gera DataFrame de resumo para exibição no Streamlit.
        
        Args:
            needs: Necessidades de produção
        
        Returns:
            DataFrame formatado
        """
        rows = []
        for codigo, need in sorted(
            needs.items(), 
            key=lambda x: x[1].quantidade_faltante, 
            reverse=True
        ):
            rows.append({
                'Código': codigo,
                'Qtd Necessária': need.quantidade_necessaria,
                'Estoque Atual': need.estoque_atual,
                '🚨 Faltante': need.quantidade_faltante,
                'Marketplaces': ', '.join(need.origem_marketplaces)
            })
        
        return pd.DataFrame(rows)
