import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from groq import Groq

# Load environment variables (for DB URL and GROQ_API_KEY)
load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://deli:sheetal123@localhost:5434/deli_rag")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

DB_SCHEMA = """
CREATE TABLE sales_daily (
    id INTEGER,
    source_file TEXT,
    source_report_date DATE,
    kind VARCHAR(16), -- 'sku' or 'category'
    upc VARCHAR(32),
    name TEXT,
    total_qty INTEGER,
    total_amount NUMERIC(12, 2)
);

CREATE TABLE ria_transactions (
    id INTEGER,
    source_file TEXT,
    txn_date DATE,
    activity VARCHAR(32), -- e.g. 'MT Send', 'ACH', 'MT Send Total'
    ref_no VARCHAR(32),
    description TEXT,
    amount NUMERIC(12, 2),
    fee NUMERIC(12, 2),
    tax NUMERIC(12, 2),
    comm NUMERIC(12, 2), -- Commission earned
    running_balance NUMERIC(12, 2)
);

CREATE TABLE inventory_snapshot (
    id INTEGER,
    upc VARCHAR(32),
    name TEXT,
    department TEXT,
    in_stock INTEGER,
    needs_reorder BOOLEAN
);
"""


def test_question(question: str):
    print(f"\n========================================\nQUESTION: {question}")

    prompt = f"""
    You are an expert PostgreSQL data analyst for a Deli & Grocery store.
    Given the user's question, write a single PostgreSQL SELECT query to answer it.

    RULES:
    - Output ONLY the SQL query. No markdown, no explanations.
    - Only use SELECT. Never UPDATE, DELETE, or DROP.
    - If the user asks for "commission", sum the `comm` column in `ria_transactions`.
      IMPORTANT: Filter out summary rows to avoid double counting: `WHERE activity NOT ILIKE '%Total%'`
    - If the user asks for "top selling", order by `total_amount` DESC.

    SCHEMA:
    {DB_SCHEMA}

    USER QUESTION: {question}
    SQL QUERY:
    """

    # 1. Generate SQL
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",  # Using the 120b model for better reasoning
        temperature=0.0,
        max_tokens=300,
    )

    sql_query = response.choices[0].message.content.strip()

    # Clean up markdown formatting if the LLM ignores instructions
    if sql_query.startswith("```sql"):
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    elif sql_query.startswith("```"):
        sql_query = sql_query.replace("```", "").strip()

    print(f"--- GENERATED SQL ---\n{sql_query}\n---------------------")

    # 2. Execute SQL
    if not sql_query.upper().startswith("SELECT"):
        print("❌ BLOCKED: Generated query is not a SELECT statement.")
        return

    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.fetchall()

            if not rows:
                print("⚠️ 0 ROWS RETURNED.")
                return

            # Print columns
            cols = result.keys()
            print(f"✅ {len(rows)} ROWS RETURNED:")
            print(" | ".join(cols))
            print("-" * 40)

            # Print up to 5 rows
            for row in rows[:5]:
                print(" | ".join(str(val) for val in row))

    except Exception as e:
        print(f"❌ SQL EXECUTION FAILED:\n{e}")


if __name__ == "__main__":
    questions = [
        "what is total sales",
        "what are top 5 selling products",
        "what is total RIA's commission",
        "how many items are currently out of stock?",
        "which department has the most inventory?"
    ]

    for q in questions:
        test_question(q)