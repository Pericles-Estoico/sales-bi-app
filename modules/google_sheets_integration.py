"""
Módulo de Integração com Google Sheets
Envia dados de vendas automaticamente para o Google Sheets
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import streamlit as st


class GoogleSheetsIntegration:
    """Classe para gerenciar integração com Google Sheets"""
    
    def __init__(self):
        """Inicializa a conexão com Google Sheets usando secrets do Streamlit"""
        try:
            # Carregar credenciais dos secrets do Streamlit
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Converter secrets para formato de credenciais
            creds_dict = {
                "type": st.secrets["google_sheets"]["type"],
                "project_id": st.secrets["google_sheets"]["project_id"],
                "private_key_id": st.secrets["google_sheets"]["private_key_id"],
                "private_key": st.secrets["google_sheets"]["private_key"],
                "client_email": st.secrets["google_sheets"]["client_email"],
                "client_id": st.secrets["google_sheets"]["client_id"],
                "auth_uri": st.secrets["google_sheets"]["auth_uri"],
                "token_uri": st.secrets["google_sheets"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["google_sheets"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["google_sheets"]["client_x509_cert_url"],
                "universe_domain": st.secrets["google_sheets"]["universe_domain"]
            }
            
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(credentials)
            self.spreadsheet_id = st.secrets["spreadsheet_id"]
            self.connected = True
            
        except Exception as e:
            self.connected = False
            self.error_message = str(e)
    
    def is_connected(self):
        """Verifica se a conexão foi estabelecida"""
        return self.connected
    
    def get_error(self):
        """Retorna mensagem de erro se houver"""
        return getattr(self, 'error_message', 'Erro desconhecido')
    
    def upload_daily_data(self, df, channel_name="Geral"):
        """
        Envia dados diários para o Google Sheets
        
        Args:
            df: DataFrame com os dados de vendas
            channel_name: Nome do canal de vendas
        
        Returns:
            tuple: (sucesso: bool, mensagem: str)
        """
        try:
            if not self.connected:
                return False, f"Erro de conexão: {self.get_error()}"
            
            # Abrir planilha
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Nome da aba: YYYY-MM-DD_NomeCanal
            today = datetime.now().strftime("%Y-%m-%d")
            sheet_name = f"{today}_{channel_name.replace(' ', '_')}"
            
            # Verificar se aba já existe
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                # Se existe, limpar dados antigos
                worksheet.clear()
            except:
                # Se não existe, criar nova aba
                worksheet = spreadsheet.add_worksheet(
                    title=sheet_name,
                    rows=str(len(df) + 10),
                    cols=str(len(df.columns) + 2)
                )
            
            # Preparar dados
            df_to_upload = df.copy()
            
            # Adicionar metadados
            df_to_upload['Data_Envio'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df_to_upload['Canal'] = channel_name
            
            # Converter para lista de listas
            data_to_upload = [df_to_upload.columns.tolist()] + df_to_upload.values.tolist()
            
            # Enviar para Google Sheets
            worksheet.update('A1', data_to_upload)
            
            # Formatar cabeçalho
            worksheet.format('A1:Z1', {
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            
            return True, f"✅ {len(df)} registros enviados para '{sheet_name}'"
            
        except Exception as e:
            return False, f"❌ Erro ao enviar dados: {str(e)}"
    
    def create_monthly_consolidation(self, year, month):
        """
        Cria aba consolidada do mês
        
        Args:
            year: Ano (ex: 2025)
            month: Mês (ex: 11)
        
        Returns:
            tuple: (sucesso: bool, mensagem: str)
        """
        try:
            if not self.connected:
                return False, f"Erro de conexão: {self.get_error()}"
            
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Nome da aba consolidada
            consolidation_name = f"Consolidado_{year}_{month:02d}"
            
            # Buscar todas as abas do mês
            all_sheets = spreadsheet.worksheets()
            month_prefix = f"{year}-{month:02d}"
            month_sheets = [s for s in all_sheets if s.title.startswith(month_prefix)]
            
            if not month_sheets:
                return False, f"❌ Nenhuma aba encontrada para {month:02d}/{year}"
            
            # Consolidar dados
            all_data = []
            for sheet in month_sheets:
                data = sheet.get_all_values()
                if len(data) > 1:  # Se tem dados além do cabeçalho
                    if not all_data:
                        all_data.append(data[0])  # Adicionar cabeçalho
                    all_data.extend(data[1:])  # Adicionar dados
            
            # Criar ou atualizar aba consolidada
            try:
                worksheet = spreadsheet.worksheet(consolidation_name)
                worksheet.clear()
            except:
                worksheet = spreadsheet.add_worksheet(
                    title=consolidation_name,
                    rows=str(len(all_data) + 10),
                    cols="20"
                )
            
            # Enviar dados consolidados
            worksheet.update('A1', all_data)
            
            # Formatar
            worksheet.format('A1:Z1', {
                "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.2},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            
            return True, f"✅ Consolidação criada: {len(all_data)-1} registros em '{consolidation_name}'"
            
        except Exception as e:
            return False, f"❌ Erro ao consolidar: {str(e)}"
    
    def get_spreadsheet_url(self):
        """Retorna URL da planilha"""
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
    
    def generate_insights(self, df):
        """
        Gera insights automáticos dos dados
        
        Args:
            df: DataFrame com dados de vendas
        
        Returns:
            dict: Dicionário com insights
        """
        insights = {}
        
        try:
            # Top 5 produtos mais vendidos
            top_products = df.groupby('Produto')['Quantidade'].sum().nlargest(5)
            insights['top_produtos'] = top_products.to_dict()
            
            # Total de vendas
            insights['total_vendas'] = int(df['Quantidade'].sum())
            
            # Produtos únicos
            insights['produtos_unicos'] = int(df['Produto'].nunique())
            
            # Média de vendas por produto
            insights['media_por_produto'] = round(df.groupby('Produto')['Quantidade'].sum().mean(), 2)
            
            # Data do período
            if 'Data' in df.columns:
                df['Data'] = pd.to_datetime(df['Data'])
                insights['data_inicio'] = df['Data'].min().strftime("%Y-%m-%d")
                insights['data_fim'] = df['Data'].max().strftime("%Y-%m-%d")
            
        except Exception as e:
            insights['erro'] = str(e)
        
        return insights
