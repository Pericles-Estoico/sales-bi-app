import pandas as pd
import plotly.graph_objects as go


class ParetoAnalysis:
    """
    Faz análise de Pareto (80/20) em cima de um DataFrame de vendas.

    Espera colunas:
      - Produto
      - Quantidade
    """

    def __init__(
        self,
        df: pd.DataFrame,
        col_produto: str = "Produto",
        col_qtd: str = "Quantidade",
    ):
        self.df = df
        self.col_produto = col_produto
        self.col_qtd = col_qtd

    # ------------------------------------------------------------------
    # GERA DATAFRAME DE PARETO
    # ------------------------------------------------------------------
    def analyze(self) -> pd.DataFrame:
        """
        Retorna um DataFrame com:
        Produto | Quantidade | Percentual | Percentual_Acumulado
        """

        # Sem dados ou sem colunas necessárias → retorna DF vazio estruturado
        if (
            self.df is None
            or self.df.empty
            or self.col_produto not in self.df.columns
            or self.col_qtd not in self.df.columns
        ):
            return pd.DataFrame(
                columns=[
                    self.col_produto,
                    self.col_qtd,
                    "Percentual",
                    "Percentual_Acumulado",
                ]
            )

        df_group = (
            self.df.groupby(self.col_produto)[self.col_qtd]
            .sum()
            .reset_index()
            .sort_values(self.col_qtd, ascending=False)
        )

        total = df_group[self.col_qtd].sum()
        if total <= 0:
            # Nada vendido → evita divisão por zero
            df_group["Percentual"] = 0.0
            df_group["Percentual_Acumulado"] = 0.0
            return df_group

        df_group["Percentual"] = df_group[self.col_qtd] / total * 100
        df_group["Percentual_Acumulado"] = df_group["Percentual"].cumsum()

        return df_group

    # ------------------------------------------------------------------
    # INSIGHTS PRINCIPAIS DO PARETO
    # ------------------------------------------------------------------
    def get_insights(self, pareto_results: pd.DataFrame) -> dict:
        """
        Retorna:
          - produtos_top_80
          - percentual_produtos_top
          - participacao_top_80
        """

        # Sem dados → tudo zero (e sem divisão por zero)
        if pareto_results is None or pareto_results.empty:
            return {
                "produtos_top_80": 0,
                "percentual_produtos_top": 0.0,
                "participacao_top_80": 0.0,
            }

        # Produtos que compõem até 80% das vendas
        top_80 = pareto_results[pareto_results["Percentual_Acumulado"] <= 80]

        total_produtos = len(pareto_results)
        if total_produtos == 0:
            percentual_top = 0.0
        else:
            percentual_top = len(top_80) / total_produtos * 100

        total_vendas = pareto_results[self.col_qtd].sum()
        if total_vendas > 0:
            participacao_top = top_80[self.col_qtd].sum() / total_vendas * 100
        else:
            participac
