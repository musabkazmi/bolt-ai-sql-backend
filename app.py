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


def generate_natural_response(user_message, sql_query, query_result):
    try:
        prompt = f"""
You are an AI assistant for a restaurant management system.

Given:
- The user question.
- The SQL query used.
- The database query result.

Your job is to write a clear, helpful natural language response to the user.

Example:
User Question: "How many pending orders?"
SQL Query: SELECT COUNT(*) FROM orders WHERE status = 'pending';
Result: {{ "count": 1 }}
→ Response: "There is 1 pending order."

Example:
User Question: "Get all menu items in the dessert category."
SQL Query: SELECT * FROM menu_items WHERE category = 'dessert';
Result: [{{name: "Ice Cream", price: 4.99}}, ...]
→ Response: "There are 2 items in the dessert category: Ice Cream ($4.99), Cake ($5.99)."

Now process this:
User Question: "{user_message}"
SQL Query: {sql_query}
Result: {query_result}

Response:
"""
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that explains database query results."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print("Error generating natural language response:", e)
        return None


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

        if "error" in result:
            return jsonify({
                "sql_query": sql_query,
                "result": result,
                "answer": "There was an error executing the SQL query."
            })

        natural_response = generate_natural_response(user_message, sql_query, result)

        return jsonify({
            "sql_query": sql_query,
            "result": result,
            "answer": natural_response
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Optional for local testing
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
