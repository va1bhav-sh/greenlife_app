from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

# Initialize database
def init_db():
    conn = sqlite3.connect("greenlife.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        name TEXT PRIMARY KEY,
        points INTEGER
    )
    """)
    conn.commit()
    conn.close()

# Points logic
def calculate_points(item, qty):
    points_map = {
        "Plastic Bottles": 2,
        "Cardboard": 5,
        "Electronics": 10,
        "Metal": 8,
        "Glass": 6,
        "E-Waste": 12
    }
    return points_map.get(item, 1) * qty # default 1 if item not found

# Home page → Form
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        item = request.form["item"]
        qty = int(request.form["quantity"])

        # Calculate points
        points = calculate_points(item, qty)

        # Save to DB
        conn = sqlite3.connect("greenlife.db")
        c = conn.cursor()

        # Check if user exists
        c.execute("SELECT points FROM users WHERE name=?", (name,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE users SET points=? WHERE name=?", (row[0] + points, name))
        else:
            c.execute("INSERT INTO users (name, points) VALUES (?, ?)", (name, points))

        conn.commit()
        conn.close()

        return redirect("/leaderboard")
    
    return render_template("index.html")

# Leaderboard page
@app.route("/leaderboard")
def leaderboard():
    conn = sqlite3.connect("greenlife.db")
    c = conn.cursor()
    c.execute("SELECT name, points FROM users ORDER BY points DESC")
    users = c.fetchall()
    conn.close()
    return render_template("leaderboard.html", users=users)

# Rewards page
@app.route("/rewards")
def rewards():
    rewards_data = [
        {"tier": "Bronze", "points": 50, "reward": "Reusable Bag"},
        {"tier": "Silver", "points": 100, "reward": "Eco Bottle"},
        {"tier": "Gold", "points": 200, "reward": "Tree Plantation"},
        {"tier": "Platinum", "points": 500, "reward": "Community Recognition"}
    ]
    return render_template("rewards.html", rewards=rewards_data)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)