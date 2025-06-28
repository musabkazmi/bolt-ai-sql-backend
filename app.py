from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Flask setup
app = Flask(__name__)
CORS(app)

# Database connection setup
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def execute_sql(sql_query):
    conn = None

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        with conn.cursor() as cur:
            cur.execute(sql_query)

            if cur.description:
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                return result
            else:
                conn.commit()
                return {"status": "Query executed successfully"}

    except Exception as e:
        return {"error": str(e)}

    finally:
        if conn is not None:
            conn.close()


@app.route('/ai/query', methods=['POST'])
def ai_to_sql():
    data = request.json
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    try:
        prompt = f"""
You are an AI assistant that converts natural language into SQL SELECT queries.
Database has tables: menu_items, orders, users.
Only write SELECT queries. Never write DELETE, UPDATE, DROP, or INSERT.

User message: {user_message}

SQL query:
"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates SQL queries."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0
        )

        sql_query = response.choices[0].message.content.strip()

        print(f"Generated SQL: {sql_query}")

        result = execute_sql(sql_query)

        return jsonify({
            "sql_query": sql_query,
            "result": result
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Optional for local testing; Render uses gunicorn so doesn't need this
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
