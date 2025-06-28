from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
from openai import OpenAI
import psycopg2
import os
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
CORS(app)

# Session setup
app.secret_key = os.getenv("FLASK_SECRET", "super_secret_key")
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# OpenAI setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Database connection
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def fetch_table(sql):
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print("❌ DB Error:", e)
        return {"error": str(e)}
    finally:
        if conn:
            conn.close()


def build_system_context():
    menu = fetch_table("SELECT * FROM menu_items")
    orders = fetch_table("SELECT * FROM orders ORDER BY created_at DESC LIMIT 20")
    users = fetch_table("SELECT * FROM users")

    if any(isinstance(t, dict) and "error" in t for t in [menu, orders, users]):
        return None, {"error": "Database fetch error."}

    menu_text = "\n".join([
        f"- {item['name']} (${item['price']}) - {item['category']}" +
        (f" | {item.get('description', '')}" if item.get('description') else "")
        for item in menu
    ])

    orders_text = "\n".join([
        f"- Order {o['id']}: {o['status'].capitalize()}, Customer: {o.get('customer_name', 'N/A')}, "
        f"Table: {o.get('table_number', 'N/A')}, Total: ${o['total']}"
        for o in orders
    ])

    users_text = "\n".join([
        f"- {u.get('name', u.get('id'))} ({u.get('role', 'N/A')})"
        for u in users
    ])

    context = f"""
You are an AI assistant for a restaurant.

📋 MENU ITEMS:
{menu_text}

📦 RECENT ORDERS:
{orders_text}

👥 USERS:
{users_text}

→ Use this data to answer questions, summarize orders, or help with tasks.

→ Remember all previous questions and answers within this chat session. 
If the user uses 'it', 'them', 'those', assume they refer to the most recent relevant item or entity unless clarified.
"""
    print("🔧 Built system context ✅")
    return context, None


@app.route('/ai/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "Message is missing."}), 400

    # Initialize chat history
    if 'chat_history' not in session:
        context, error = build_system_context()
        if error:
            return jsonify(error), 500

        session['chat_history'] = [{"role": "system", "content": context}]
        print("🚀 Initialized new chat history with system context.")

    chat_history = session['chat_history']

    print("\n🟦 Previous chat history:")
    for m in chat_history:
        print(f" - {m['role']}: {m['content'][:100]}...")

    # Add user message
    chat_history.append({"role": "user", "content": user_message})
    print(f"\n🟩 Added user message: {user_message}")

    try:
        # Call GPT
        print("\n🚀 Sending to OpenAI...")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=chat_history,
            max_tokens=700,
            temperature=0.5
        )

        answer = response.choices[0].message.content.strip()

        print(f"\n💬 GPT Answer: {answer}")

        # Save reply to history
        chat_history.append({"role": "assistant", "content": answer})
        session['chat_history'] = chat_history

        return jsonify({
            "answer": answer
        })

    except Exception as e:
        print("❌ OpenAI API error:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/ai/clear', methods=['POST'])
def clear_memory():
    session.pop('chat_history', None)
    print("\n🗑️ Chat memory cleared.")
    return jsonify({"status": "Chat memory cleared."})


@app.route('/')
def home():
    return "✅ Restaurant AI backend with session-based chat memory and debug mode ON."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
