from __future__ import annotations


def build_queries(symbol: str, max_queries: int = 5) -> list[str]:
    stock_id = symbol.split(".")[0]
    base = [
        f"{stock_id} 長榮 SCFI 最新",
        "SCFI 最新指數 美西 美東 歐洲線 運價",
        "Evergreen Marine SCFI latest freight rate Red Sea",
        f"{stock_id} 長榮 運價 紅海 法說 配息",
        f"{stock_id} 長榮 外資 投信 ETF 買賣超",
    ]
    return base[:max_queries]


def freight_queries(symbol: str) -> list[str]:
    stock_id = symbol.split(".")[0]
    return [
        "SCFI 最新指數 美西 美東 歐洲線 運價",
        "SCFI 2726.48 美西 美東 歐洲 運價",
        "6月5日 SCFI 美西 美東 歐洲 運價",
        f"{stock_id} 長榮 SCFI 運價 最新",
        "Evergreen Marine SCFI latest US West US East Europe freight rate",
        "Red Sea shipping latest container freight rate",
    ]
