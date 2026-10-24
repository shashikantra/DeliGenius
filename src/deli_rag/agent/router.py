from __future__ import annotations

from deli_rag.schemas.query import TransformedQuery, UnderstoodQuery
from deli_rag.schemas.routing import RoutedQuery, RoutingDecision


def route(understood: UnderstoodQuery, transformed: TransformedQuery) -> RoutedQuery:
    subs = transformed.sub_questions or [transformed.expanded]
    decisions: list[RoutingDecision] = []

    for sq in subs:
        decisions.append(_route_one(sq, understood))

    return RoutedQuery(
        original=understood.original,
        sub_questions=subs,
        decisions=decisions,
    )


def _route_one(sub_question: str, understood: UnderstoodQuery) -> RoutingDecision:
    intent = understood.intent
    q_lower = sub_question.lower()

    # Comprehensive SQL keywords for a Deli & Grocery store
    sql_keywords = [
        # --- SALES & REVENUE ---
        "sale", "sales", "revenue", "income", "earnings", "profit", "margin",
        "sold", "sell", "selling", "purchased", "bought", "transaction",
        "total", "sum", "average", "daily", "weekly", "monthly", "yearly",
        "yesterday", "today", "week", "month", "year", "quarter", "period",

        # --- PRICES & COSTS ---
        "price", "pricing", "cost", "how much", "rate", "value", "worth",
        "discount", "markup", "retail", "wholesale", "unit price",

        # --- INVENTORY & STOCK ---
        "inventory", "stock", "in stock", "out of stock", "on hand",
        "reorder", "re-order", "low stock", "restock", "quantity", "count",
        "available", "availability", "depleted", "shortage",

        # --- PRODUCTS & ITEMS ---
        "item", "product", "sku", "upc", "barcode", "brand", "category",
        "department", "aisle", "shelf", "variant", "size", "weight", "unit",

        # --- RIA & MONEY TRANSFER ---
        "commission", "comm", "ria", "rimi", "remittance", "transfer",
        "wire", "ach", "deposit", "balance", "fee", "tax", "settlement",

        # --- RANKINGS & COMPARISONS ---
        "top", "best", "worst", "highest", "lowest", "most", "least",
        "popular", "selling", "rank", "compare", "difference", "trend",

        # --- COUNTS & AGGREGATES ---
        "how many", "count", "number of", "sum", "average", "total",

        # --- TIMEFRAMES ---
        "last", "this", "previous", "recent", "past", "current",
    ]

    if any(w in q_lower for w in sql_keywords):
        return RoutingDecision(
            sub_question=sub_question, route="sql",
            sql_kind="text_to_sql", reason="keyword matched SQL route", confidence=0.95,
        )

    if understood.is_ambiguous and understood.entities.is_empty():
        return RoutingDecision(
            sub_question=sub_question, route="abstain",
            reason="ambiguous query with no usable entities", confidence=0.9,
        )

    if intent in ("fact", "comparison", "summary"):
        return RoutingDecision(
            sub_question=sub_question, route="sql",
            sql_kind="text_to_sql", reason="data intent", confidence=0.95,
        )

    return RoutingDecision(
        sub_question=sub_question, route="doc_retrieval",
        reason=f"intent {intent!r} prefers documents", confidence=0.8,
    )
