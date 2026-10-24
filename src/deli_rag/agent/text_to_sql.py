from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from groq import Groq

from deli_rag.config.settings import get_env, get_config
from deli_rag.agent.sql_route import SqlEvidence

DB_SCHEMA = """
CREATE TABLE sales_daily (
    id INTEGER, source_file TEXT, source_report_date DATE,
    kind VARCHAR(16), -- 'sku' or 'category'
    upc VARCHAR(32), name TEXT, total_qty INTEGER, total_amount NUMERIC(12, 2)
);
CREATE TABLE ria_transactions (
    id INTEGER, source_file TEXT, txn_date DATE,
    activity VARCHAR(32), ref_no VARCHAR(32), description TEXT, amount NUMERIC(12, 2),
    fee NUMERIC(12, 2), tax NUMERIC(12, 2), comm NUMERIC(12, 2)
);
CREATE TABLE inventory_snapshot (
    id INTEGER, upc VARCHAR(32), name TEXT, department TEXT, in_stock INTEGER, needs_reorder BOOLEAN
);
"""


class TextToSql:
    def __init__(self, session: Session):
        self.session = session
        self.client = Groq(api_key=get_env().groq_api_key)
        cfg = get_config().llm
        self.model = "openai/gpt-oss-120b"
        for key in ["primary", "fallback_1", "fallback_2"]:
            model_conf = getattr(cfg, key, None)
            if model_conf and "sql" in getattr(model_conf, "roles", []):
                self.model = model_conf.id
                break

    def run(self, question: str, history: list[tuple[str, str]] | None = None) -> SqlEvidence | None:
        today = datetime.now().strftime("%Y-%m-%d")

        history_text = ""
        if history:
            history_text = "RECENT CONVERSATION:\n"
            for user_msg, assistant_msg in history[-2:]:
                history_text += f"User: {user_msg}\nAssistant: {assistant_msg}\n"

        prompt = f"""
        You are an expert PostgreSQL data analyst for a Deli & Grocery store.
        Today's date is {today}.

        {history_text}

        Here is the database schema:
        {DB_SCHEMA}

        Here are examples of how to answer questions:

        USER: what is total sales for last month
        SQL: SELECT SUM(total_amount) FROM sales_daily WHERE source_report_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' AND source_report_date < date_trunc('month', CURRENT_DATE);

        USER: what is total sales for this week
        SQL: SELECT SUM(total_amount) FROM sales_daily WHERE source_report_date >= CURRENT_DATE - INTERVAL '7 days';

        USER: what is total sales for 10/20/2026
        SQL: SELECT SUM(total_amount) FROM sales_daily WHERE source_report_date = '2026-10-20';

        USER: what is the price of [ANY ITEM NAME]
        SQL: SELECT ROUND(SUM(total_amount) / NULLIF(SUM(total_qty), 0), 2) AS unit_price FROM sales_daily WHERE name ILIKE '%ITEM_NAME%' AND kind = 'sku';

        USER: how many [ANY ITEM] did we sell this week
        SQL: SELECT SUM(total_qty) FROM sales_daily WHERE name ILIKE '%ITEM_NAME%' AND source_report_date >= CURRENT_DATE - INTERVAL '7 days';

        USER: what is the top selling product
        SQL: SELECT name, SUM(total_qty) AS total_sold FROM sales_daily WHERE kind = 'sku' GROUP BY name ORDER BY total_sold DESC LIMIT 1;

        USER: what items are running low on stock
        SQL: SELECT name, in_stock FROM inventory_snapshot WHERE needs_reorder = TRUE ORDER BY in_stock ASC LIMIT 10;

        USER: what is total RIA commission
        SQL: SELECT SUM(comm) FROM ria_transactions WHERE activity NOT ILIKE '%Total%';

        CRITICAL RULES:
        - ALWAYS use ILIKE '%keyword%' for any item name.
        - NEVER use `name = 'item'`. The database has many variants (e.g., "Salem Gold Box", "Salem Silver Box").
        - If the user asks for something general like "cigarettes", use `name ILIKE '%cigarette%'`.

        Write a single PostgreSQL SELECT query to answer this user's latest question.
        Output ONLY the SQL query. No markdown, no explanations.
        Only use SELECT. Never UPDATE, DELETE, or DROP.

        USER: {question}
        SQL:
        """

        try:
            time.sleep(1)
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.0,
                max_tokens=300,
            )
            sql_query = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"LLM API Error: {e}")
            return None

        sql_query = re.sub(r"^```sql\s*", "", sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(r"\s*```$", "", sql_query)

        if not sql_query.upper().startswith("SELECT"):
            return None

        try:
            result = self.session.execute(text(sql_query)).all()
            if not result or result[0][0] is None:
                # Fallback: try to find similar items for user suggestions
                cleaned = re.sub(
                    r'(what is the|what are the|price of|price for|selling price|how much is|how much are|cost of|cost for|the|price|cost|selling)',
                    '',
                    question.lower()
                ).strip()

                # Use first 10 chars of cleaned item name as a fuzzy search
                search_term = cleaned[:10]
                suggestion_sql = f"""
                    SELECT DISTINCT name FROM sales_daily
                    WHERE name ILIKE '%{search_term}%'
                    LIMIT 5
                """
                suggestions = self.session.execute(text(suggestion_sql)).all()

                if suggestions:
                    items = [row[0] for row in suggestions]
                    suggestion_text = "Did you mean one of these? " + ", ".join(items)
                    return SqlEvidence(
                        kind="text_to_sql",
                        columns=["result"],
                        rows=[[suggestion_text]],
                        sql=sql_query,
                        summary=suggestion_text
                    )
                else:
                    return SqlEvidence(
                        kind="text_to_sql", columns=["result"], rows=[["No matching records found."]],
                        sql=sql_query, summary="No matching records found."
                    )

            columns = list(result[0]._fields) if hasattr(result[0], "_fields") else list(result[0]._mapping.keys())
            data = [list(row) for row in result]

            # If it's a price query, add the price to the summary
            # Extract the actual value from the data
            first_row = data[0] if data else []
            if len(first_row) == 1:
                summary_text = f"The result is: {first_row[0]}"
            else:
                summary_text = "Results: " + " | ".join(str(v) for v in first_row)
            if "price" in question.lower() and data and len(data[0]) == 1:
                summary_text = f"The price is {data[0][0]}."

            return SqlEvidence(
                kind="text_to_sql", columns=columns, rows=data,
                sql=sql_query, summary=summary_text
            )
        except Exception as e:
            print(f"SQL Execution Error: {e}\nQuery: {sql_query}")
            return None