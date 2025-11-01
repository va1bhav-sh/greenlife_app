from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from urllib.parse import urlparse, urljoin
from datetime import datetime
import os

# --- Flask Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///greenlife.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    points = db.Column(db.Integer, default=0)
    address = db.Column(db.String(300), nullable=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return self.password_hash and check_password_hash(self.password_hash, pw)


class Rider(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Pickup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_type = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    address = db.Column(db.String(300))
    preferred_date = db.Column(db.String(50))
    preferred_time = db.Column(db.String(50))
    status = db.Column(db.String(50), default='requested')
    rider_id = db.Column(db.Integer, db.ForeignKey('rider.id'), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


# --- Helpers ---
def init_db():
    with app.app_context():
        db.create_all()


def calculate_points(item, qty):
    points_map = {
        "Plastic Bottles": 2,
        "Cardboard": 5,
        "Electronics": 10,
        "Metal": 8,
        "Glass": 6,
        "E-Waste": 12
    }
    # Ensure quantity is an integer
    try:
        qty_int = int(qty)
    except (ValueError, TypeError):
        qty_int = 0
    return points_map.get(item, 1) * qty_int


def is_safe_url(target):
    if not target:
        return False
    host_url = request.host_url
    test_url = urljoin(host_url, target)
    return urlparse(test_url).scheme in ("http", "https") and urlparse(host_url).netloc == urlparse(test_url).netloc


@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}


# --- Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    # --- FIX: Check User table first, then Rider table ---
    u = User.query.get(int(user_id))
    if u:
        return u
    return Rider.query.get(int(user_id))


# --- Routes ---
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    # --- FIX: This page is for Users only. Redirect Riders. ---
    if not isinstance(current_user, User):
        return redirect(url_for('rider_dashboard'))
    
    if request.method == "POST":
        name = current_user.name
        item = request.form["item"]
        qty = int(request.form["quantity"])
        points = calculate_points(item, qty)

        current_user.points = (current_user.points or 0) + points
        db.session.commit()
        flash(f'{points} points added for {item}!')
        return redirect("/leaderboard")

    return render_template("index.html")


@app.route("/leaderboard")
@login_required
def leaderboard():
    users = User.query.order_by(User.points.desc()).all()
    return render_template("leaderboard.html", users=[(u.name, u.points or 0) for u in users])


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form['name'].strip()
        email = request.form.get('email')
        pw = request.form.get('password')

        if User.query.filter_by(name=name).first():
            flash('Name already used')
            return redirect(url_for('signup'))
        
        # --- FIX: Check for email uniqueness too ---
        if email and User.query.filter_by(email=email).first():
            flash('Email already used')
            return redirect(url_for('signup'))

        u = User(name=name, email=email)
        if pw:
            u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        login_user(u)
        return redirect(url_for('index'))

    return render_template('signup.html')


@app.route("/login", methods=["GET", "POST"])
def login():
    next_page = request.args.get('next')
    if request.method == 'POST':
        name_or_email = request.form.get('email')
        pw = request.form.get('password')
        posted_next = request.form.get('next') or next_page

        u = User.query.filter((User.email == name_or_email) | (User.name == name_or_email)).first()
        if u and u.check_password(pw):
            login_user(u)
            return redirect(posted_next if is_safe_url(posted_next) else url_for('index'))

        r = Rider.query.filter_by(email=name_or_email).first()
        if r and r.check_password(pw):
            login_user(r)
            # --- FIX: Riders go to rider_dashboard, not index ---
            return redirect(posted_next if is_safe_url(posted_next) else url_for('rider_dashboard'))

        flash("Invalid credentials")

    return render_template("login.html", next_page=next_page)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route("/request_pickup", methods=["GET", "POST"])
@login_required
def request_pickup():
    # --- FIX: This page is for Users only. ---
    if not isinstance(current_user, User):
        flash("Only users can request pickups.")
        return redirect(url_for('index'))

    if request.method == "POST":
        item = request.form['item']
        qty = int(request.form['quantity'])
        addr = request.form.get('address') or current_user.address or ''
        date = request.form.get('date')
        time_ = request.form.get('time')
        
        # --- FIX: Update user's address if they provided a new one ---
        if addr and not current_user.address:
            current_user.address = addr

        p = Pickup(user_id=current_user.id, item_type=item, quantity=qty,
                   address=addr, preferred_date=date, preferred_time=time_)
        db.session.add(p)
        db.session.commit()
        flash('Pickup requested — you will get confirmation soon')
        return redirect(url_for('index'))

    return render_template('request_pickup.html', user=current_user)


@app.route("/rider")
@login_required
def rider_dashboard():
    # --- FIX: Robust check to ensure only Riders access this page ---
    if not isinstance(current_user, Rider):
        flash("Rider access only")
        return redirect(url_for('index'))
    
    # --- FIX: Show both new requests and requests assigned to this rider ---
    requested_pickups = Pickup.query.filter_by(status='requested').order_by(Pickup.created_at.desc()).all()
    my_pickups = Pickup.query.filter_by(status='assigned', rider_id=current_user.id).order_by(Pickup.created_at.desc()).all()
    
    return render_template('rider_dashboard.html', requested=requested_pickups, assigned=my_pickups)


@app.route("/rider/accept/<int:pickup_id>", methods=["POST"])
@login_required
def rider_accept(pickup_id):
    # --- FIX: Robust check for Rider access ---
    if not isinstance(current_user, Rider):
        flash("Rider access only")
        return redirect(url_for('index'))
        
    p = Pickup.query.get(pickup_id)
    if not p:
        flash("Pickup not found")
        return redirect(url_for('rider_dashboard'))
    
    if p.status != 'requested':
        flash("Pickup already assigned")
        return redirect(url_for('rider_dashboard'))

    p.rider_id = current_user.id
    p.status = 'assigned'
    db.session.commit()
    flash("Pickup accepted")
    return redirect(url_for('rider_dashboard'))


@app.route("/rider/complete/<int:pickup_id>", methods=["POST"])
@login_required
def rider_complete(pickup_id):
    # --- FIX: Robust check for Rider access ---
    if not isinstance(current_user, Rider):
        flash("Rider access only")
        return redirect(url_for('index'))

    p = Pickup.query.get(pickup_id)
    if not p:
        flash("Pickup not found")
        return redirect(url_for('rider_dashboard'))

    # --- FIX: Ensure only the assigned rider can complete it ---
    if p.rider_id != current_user.id:
        flash("This pickup is not assigned to you")
        return redirect(url_for('rider_dashboard'))

    p.status = 'completed'
    u = User.query.get(p.user_id)
    if u:
        # --- FIX: Use the calculate_points function instead of a flat 10 ---
        points_to_add = calculate_points(p.item_type, p.quantity)
        u.points = (u.points or 0) + points_to_add
        flash(f"Pickup completed! {points_to_add} points awarded to {u.name}.")
    
    db.session.commit()
    return redirect(url_for('rider_dashboard'))


@app.route("/rewards")
@login_required
def rewards():
    # --- FIX: This page is for Users only. ---
    if not isinstance(current_user, User):
        flash("Rewards are for users only.")
        return redirect(url_for('index'))

    rewards_data = [
        {"tier": "Bronze", "points": 50, "reward": "Reusable Bag"},
        {"tier": "Silver", "points": 100, "reward": "Eco Bottle"},
        {"tier": "Gold", "points": 200, "reward": "Tree Plantation"},
        {"tier": "Platinum", "points": 500, "reward": "Community Recognition"}
    ]
    return render_template("rewards.html", rewards=rewards_data)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)