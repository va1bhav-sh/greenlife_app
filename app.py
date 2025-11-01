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
login_manager.login_message_category = 'info'

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    points = db.Column(db.Integer, default=0)
    address = db.Column(db.String(300), nullable=True)
    tree_level = db.Column(db.Integer, default=0)

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

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300))
    points_reward = db.Column(db.Integer, default=10)

class UserChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=False)
    completed_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (db.UniqueConstraint('user_id', 'challenge_id', name='_user_challenge_uc'),)


# --- Helpers ---
def create_dummy_challenges():
    if Challenge.query.count() == 0:
        print("Creating dummy challenges...")
        c1 = Challenge(title="Waste-Free Wednesday", description="Go a full day without using any single-use plastic.", points_reward=20)
        c2 = Challenge(title="DIY Recycler", description="Find an item in your home and repurpose it instead of throwing it away.", points_reward=15)
        c3 = Challenge(title="Community Cleanup", description="Pick up 5 pieces of trash on your street or in a local park.", points_reward=10)
        c4 = Challenge(title="First Pickup", description="Schedule your very first recycling pickup.", points_reward=5)
        db.session.add_all([c1, c2, c3, c4])
        db.session.commit()
    else:
        print("Challenges already exist.")

def init_db():
    with app.app_context():
        db.create_all()
        create_dummy_challenges()

def calculate_points(item, qty):
    points_map = {
        "Plastic Bottles": 2, "Cardboard": 5, "Electronics": 10,
        "Metal": 8, "Glass": 6, "E-Waste": 12
    }
    try: qty_int = int(qty)
    except (ValueError, TypeError): qty_int = 0
    return points_map.get(item, 1) * qty_int

def is_safe_url(target):
    if not target: return False
    host_url = request.host_url
    test_url = urljoin(host_url, target)
    return urlparse(test_url).scheme in ("http", "https") and urlparse(host_url).netloc == urlparse(test_url).netloc

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}

# --- Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    u = db.session.get(User, int(user_id))
    if u:
        return u
    return db.session.get(Rider, int(user_id))

# --- Main Routes ---
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if not isinstance(current_user, User):
        return redirect(url_for('rider_dashboard'))
    
    if request.method == "POST":
        item = request.form['item']
        qty = int(request.form['quantity'])
        addr = request.form.get('address') or current_user.address or ''
        date = request.form.get('date')
        time_ = request.form.get('time')
        
        if addr and (not current_user.address or current_user.address != addr):
            current_user.address = addr

        p = Pickup(user_id=current_user.id, item_type=item, quantity=qty,
                   address=addr, preferred_date=date, preferred_time=time_)
        db.session.add(p)
        
        # --- FIX: Increase tree_level on submission, not completion ---
        current_user.tree_level = (current_user.tree_level or 0) + 1
        
        db.session.commit()
        
        # This message is still correct and tells the user what to expect!
        flash('Your pickup is scheduled! Points will be credited after pickup.')
        return redirect(url_for('index'))

    return render_template("index.html")

@app.route("/leaderboard")
@login_required
def leaderboard():
    users = User.query.order_by(User.points.desc()).limit(20).all()
    return render_template("leaderboard.html", users=[(u.name, u.points or 0) for u in users])

@app.route("/rewards")
@login_required
def rewards():
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

@app.route("/dashboard")
@login_required
def dashboard():
    if not isinstance(current_user, User):
        return redirect(url_for('rider_dashboard'))

    # --- FIX: Count all pickups (any status) to show immediate impact ---
    total_pickups = Pickup.query.filter_by(user_id=current_user.id).count()
    
    # --- FIX: Calculate stats based on all pickups (any status) ---
    items_saved_query = db.session.query(
        Pickup.item_type, 
        db.func.sum(Pickup.quantity)
    ).filter_by(user_id=current_user.id).group_by(Pickup.item_type).all()
    
    carbon_map = {
        "Plastic Bottles": 2.5, "Cardboard": 1.2, "Electronics": 5.0,
        "Metal": 3.0, "Glass": 0.8, "E-Waste": 5.0
    }
    
    stats = {}
    total_carbon_saved = 0
    for item, quantity in items_saved_query:
        stats[item] = quantity
        total_carbon_saved += carbon_map.get(item, 0.5) * quantity

    return render_template("dashboard.html", 
                           stats=stats, 
                           total_pickups=total_pickups, 
                           total_carbon=round(total_carbon_saved, 2))

@app.route("/challenges")
@login_required
def challenges():
    if not isinstance(current_user, User):
        return redirect(url_for('rider_dashboard'))
    
    all_challenges = Challenge.query.all()
    completed_query = db.session.query(UserChallenge.challenge_id).filter_by(user_id=current_user.id).all()
    completed_ids = {c[0] for c in completed_query}

    return render_template("challenges.html", 
                           challenges=all_challenges, 
                           completed_ids=completed_ids)

@app.route("/challenges/complete/<int:challenge_id>", methods=["POST"])
@login_required
def complete_challenge(challenge_id):
    if not isinstance(current_user, User):
        return redirect(url_for('rider_dashboard'))
        
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge:
        flash("Challenge not found!")
        return redirect(url_for('challenges'))

    existing = UserChallenge.query.filter_by(user_id=current_user.id, challenge_id=challenge_id).first()
    if existing:
        flash("You already completed this challenge!")
        return redirect(url_for('challenges'))
    
    new_completion = UserChallenge(user_id=current_user.id, challenge_id=challenge_id)
    db.session.add(new_completion)
    
    current_user.points = (current_user.points or 0) + challenge.points_reward
    db.session.commit()
    
    flash(f"Challenge completed! You earned {challenge.points_reward} points! 🎉")
    return redirect(url_for('challenges'))

@app.route("/forest")
@login_required
def forest():
    if not isinstance(current_user, User):
        return redirect(url_for('rider_dashboard'))
    
    level = current_user.tree_level or 0
    
    tree_stages = [
        ("🌱", "Seedling", 0),
        ("🌿", "Sprout", 5),
        ("🌳", "Small Tree", 10),
        ("🌲", "Growing Forest", 20),
        ("🏞️", "Lush Ecosystem", 50)
    ]
    
    current_stage = tree_stages[0]
    next_stage = tree_stages[1]
    
    for i in range(len(tree_stages)):
        if level >= tree_stages[i][2]:
            current_stage = tree_stages[i]
            if i + 1 < len(tree_stages):
                next_stage = tree_stages[i+1]
            else:
                next_stage = None # Max level
        else:
            break
            
    progress_percent = 0
    if next_stage:
        level_range = next_stage[2] - current_stage[2]
        progress_in_range = level - current_stage[2]
        if level_range > 0:
            progress_percent = (progress_in_range / level_range) * 100

    return render_template("forest.html", 
                           level=level, 
                           stage=current_stage, 
                           next_stage=next_stage, 
                           progress=progress_percent)


# --- Auth Routes ---
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form['name'].strip()
        email = request.form.get('email')
        pw = request.form.get('password')

        # --- FIX: Convert empty string '' to None (NULL) ---
        # This allows multiple users to sign up without an email
        # without violating the UNIQUE constraint.
        if email == '':
            email = None
        # --- END FIX ---

        if User.query.filter_by(name=name).first():
            flash('Name already used', 'warning') # Added category
            return redirect(url_for('signup'))
        
        # This check will now be skipped if email is None, which is correct.
        if email and User.query.filter_by(email=email).first():
            flash('Email already used', 'warning') # Added category
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
            return redirect(posted_next if is_safe_url(posted_next) else url_for('rider_dashboard'))
        flash("Invalid credentials")
    return render_template("login.html", next_page=next_page)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Rider Routes ---
@app.route("/rider")
@login_required
def rider_dashboard():
    if not isinstance(current_user, Rider):
        flash("Rider access only")
        return redirect(url_for('index'))
    requested_pickups = Pickup.query.filter_by(status='requested').order_by(Pickup.created_at.desc()).all()
    my_pickups = Pickup.query.filter_by(status='assigned', rider_id=current_user.id).order_by(Pickup.created_at.desc()).all()
    return render_template('rider_dashboard.html', requested=requested_pickups, assigned=my_pickups)

@app.route("/rider/accept/<int:pickup_id>", methods=["POST"])
@login_required
def rider_accept(pickup_id):
    if not isinstance(current_user, Rider):
        flash("Rider access only")
        return redirect(url_for('index'))
    p = db.session.get(Pickup, pickup_id)
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
    if not isinstance(current_user, Rider):
        flash("Rider access only")
        return redirect(url_for('index'))

    p = db.session.get(Pickup, pickup_id)
    if not p:
        flash("Pickup not found")
        return redirect(url_for('rider_dashboard'))
    if p.rider_id != current_user.id:
        flash("This pickup is not assigned to you")
        return redirect(url_for('rider_dashboard'))

    p.status = 'completed'
    u = db.session.get(User, p.user_id)
    if u:
        points_to_add = calculate_points(p.item_type, p.quantity)
        u.points = (u.points or 0) + points_to_add
        
        # --- FIX: Removed tree_level increase from here ---
        
        flash(f"Pickup completed! {points_to_add} points awarded to {u.name}.")
    
    db.session.commit()
    return redirect(url_for('rider_dashboard'))

# --- Main Run ---
if __name__ == "__main__":
    init_db()
    app.run(debug=True)