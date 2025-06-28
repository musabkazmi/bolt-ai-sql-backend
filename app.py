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


def fetch_table(query):
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
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            result = [dict(zip(columns, row)) for row in rows]
            return result

    except Exception as e:
        return {"error": str(e)}

    finally:
        if conn is not None:
            conn.close()


def build_context_string(menu_items, orders, users):
    menu_text = "\n".join([
        f"- {item['name']} (${item['price']}) - {item['category']}" +
        (f" | {item['description']}" if item.get('description') else "")
        for item in menu_items
    ])

    orders_text = "\n".join([
        f"- Order {o['id']}: {o['status'].capitalize()}, Customer: {o.get('customer_name', 'Unknown')}, "
        f"Table: {o.get('table_number', 'N/A')}, Total: ${o['total']}"
        for o in orders
    ])

    users_text = "\n".join([
        f"- {u.get('name', u.get('id'))} ({u.get('role', 'Unknown')})"
        for u in users
    ])

    context = f"""
You are an AI assistant for a restaurant. Here is the current data:

📜 Menu:
{menu_text}

📦 Orders:
{orders_text}

👥 Users:
{users_text}

Use this information to answer questions accurately about the restaurant. 
If the question cannot be answered from this data, say: 'This information is not available.'
"""
    return context


@app.route('/ai/chat', methods=['POST'])
def chat_with_context():
    data = request.json
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Fetch all relevant tables
    menu_items = fetch_table("SELECT * FROM menu_items")
    orders = fetch_table("SELECT * FROM orders ORDER BY created_at DESC LIMIT 20;")  # Recent 20 orders
    users = fetch_table("SELECT * FROM users")

    if any(isinstance(table, dict) and "error" in table for table in [menu_items, orders, users]):
        return jsonify({"error": "Database fetch error", "details": [menu_items, orders, users]}), 500

    # Build context string
    context = build_context_string(menu_items, orders, users)

    try:
        # Send to OpenAI
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_message}
            ],
            max_tokens=500,
            temperature=0.5
        )

        answer = response.choices[0].message.content.strip()

        return jsonify({
            "answer": answer,
            "context_used": context  # Optional, for debug
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Optional health check
@app.route('/')
def index():
    return "Restaurant AI Backend is running."


# For local run
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
