from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import qrcode
import io
import base64
import pyotp
import json
import os
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cafeteria.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    points = db.Column(db.Integer, default=0)
    last_checkin = db.Column(db.DateTime)

class CheckIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    points_earned = db.Column(db.Integer)

class PointsTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    points = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    transaction_type = db.Column(db.String(20))
    description = db.Column(db.String(200))

class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(200))
    points_cost = db.Column(db.Integer)
    stock = db.Column(db.Integer)

# Queue management
current_queue_length = 0
queue_history = []

# 在文件开头添加全局变量
debug_mode = False
debug_time = None
debug_time_increment = 0  # 用于模拟时间流逝
current_code = None
code_expiry = None

def get_current_time():
    global debug_mode, debug_time, debug_time_increment
    if debug_mode and debug_time:
        current = debug_time + timedelta(seconds=debug_time_increment)
        print(f"Debug time: {current}")  # Debug info
        return current
    current = datetime.now()
    print(f"Real time: {current}")  # Debug info
    return current

@app.route('/get_current_time')
def get_current_time_api():
    global debug_mode, debug_time, debug_time_increment
    if debug_mode and debug_time:
        # 每次请求增加30秒
        debug_time_increment += 30
        current = debug_time + timedelta(seconds=debug_time_increment)
        print(f"Debug API time: {current}")  # Debug info
        return jsonify({
            'time': current.strftime('%H:%M:%S'),
            'is_debug': True
        })
    current = datetime.now()
    print(f"Real API time: {current}")  # Debug info
    return jsonify({
        'time': current.strftime('%H:%M:%S'),
        'is_debug': False
    })

@app.route('/set_debug_time', methods=['POST'])
def set_debug_time():
    global debug_mode, debug_time, debug_time_increment
    debug_mode = True
    debug_time = datetime.now().replace(hour=11, minute=45, second=0, microsecond=0)
    debug_time_increment = 0
    return jsonify({
        'success': True,
        'time': debug_time.strftime('%H:%M:%S')
    })

@app.route('/reset_debug_time', methods=['POST'])
def reset_debug_time():
    global debug_mode, debug_time, debug_time_increment
    debug_mode = False
    debug_time = None
    debug_time_increment = 0
    return jsonify({
        'success': True,
        'message': 'Debug mode reset'
    })

def is_cafeteria_open():
    current_time = get_current_time()
    # 转换为北京时间 (UTC+8)
    beijing_time = current_time + timedelta(hours=8)
    print(f"Checking cafeteria status at: {beijing_time}")  # Debug info
    
    # 检查是否在营业时间内 (11:45-12:50)
    is_open = False
    if beijing_time.hour == 11 and beijing_time.minute >= 45:
        is_open = True
    elif beijing_time.hour == 12 and beijing_time.minute <= 50:
        is_open = True
    
    print(f"Cafeteria status: {'OPEN' if is_open else 'CLOSED'}")  # Debug info
    return is_open

def calculate_queue_length():
    try:
        # Read CSV file
        df = pd.read_csv("queue_data.csv")
        print(f"Total records in CSV: {len(df)}")  # Debug info
        
        # Convert Time column to datetime
        df['Time'] = pd.to_datetime(df['Time'])
        print(f"First record time: {df['Time'].iloc[0]}")  # Debug info
        
        # Calculate queue length
        df['Delta'] = df['Action'].map({'enter': 1, 'exit': -1})
        df['Queue Length'] = df['Delta'].cumsum()
        
        # Get current queue length and convert to Python int
        current_length = int(df['Queue Length'].iloc[-1])
        print(f"Current queue length: {current_length}")  # Debug info
        
        # Calculate average processing time based on recent data
        recent_exits = df[df['Action'] == 'exit'].tail(10)
        if len(recent_exits) > 0:
            avg_processing_time = 2.0  # Default to 2 minutes if not enough data
        else:
            avg_processing_time = 2.0
        
        # Calculate estimated wait time
        estimated_wait_time = current_length * avg_processing_time
        
        # Get cafeteria status
        is_open = is_cafeteria_open()
        print(f"Returning queue data - Length: {current_length}, Wait Time: {estimated_wait_time}, Is Open: {is_open}")  # Debug info
        
        return {
            'queue_length': max(0, current_length),
            'estimated_wait_time': round(estimated_wait_time, 1),
            'is_open': is_open
        }
    except Exception as e:
        print(f"Error reading queue data: {e}")
        return {
            'queue_length': 0,
            'estimated_wait_time': 0,
            'is_open': is_cafeteria_open()
        }

def calculate_points(queue_length):
    if queue_length < 5:
        return 10
    elif queue_length < 10:
        return 5
    elif queue_length < 15:
        return 2
    else:
        return 0

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    rewards = Reward.query.all()
    return render_template('dashboard.html', user=current_user, rewards=rewards)

@app.route('/generate_qr')
def generate_qr():
    # Generate a time-based OTP
    totp = pyotp.TOTP('base32secret3232')
    current_code = totp.now()
    
    # Create QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(current_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({'qr_code': img_str, 'code': current_code})

def generate_code():
    global current_code, code_expiry
    # 生成6位随机数字
    current_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    code_expiry = datetime.now() + timedelta(seconds=10)
    return current_code

@app.route('/generate_code')
def generate_code_api():
    code = generate_code()
    return jsonify({
        'code': code,
        'expires_in': 10
    })

@app.route('/get_code')
def get_code():
    global current_code, code_expiry
    if not current_code or datetime.now() >= code_expiry:
        current_code = generate_code()
    return jsonify({
        'code': current_code,
        'expires_in': int((code_expiry - datetime.now()).total_seconds())
    })

@app.route('/checkin', methods=['POST'])
@login_required
def checkin():
    data = request.get_json()
    code = data.get('code')
    
    # 验证码
    if not current_code or code != current_code:
        return jsonify({'success': False, 'message': 'Invalid code'})
    
    if datetime.now() >= code_expiry:
        return jsonify({'success': False, 'message': 'Code expired'})
    
    # Check if user has already checked in today
    today = datetime.utcnow().date()
    if current_user.last_checkin and current_user.last_checkin.date() == today:
        return jsonify({'success': False, 'message': 'Already checked in today'})
    
    # Calculate points based on queue length
    queue_length = calculate_queue_length()
    points = calculate_points(queue_length['queue_length'])
    
    # Record check-in
    checkin = CheckIn(user_id=current_user.id, points_earned=points)
    transaction = PointsTransaction(
        user_id=current_user.id,
        points=points,
        transaction_type='earn',
        description='Cafeteria check-in'
    )
    
    current_user.points += points
    current_user.last_checkin = datetime.utcnow()
    
    db.session.add(checkin)
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'points': points,
        'total_points': current_user.points
    })

@app.route('/rewards')
@login_required
def rewards():
    rewards = Reward.query.all()
    return render_template('rewards.html', rewards=rewards, user=current_user)

@app.route('/redeem/<int:reward_id>')
@login_required
def redeem_reward(reward_id):
    reward = Reward.query.get_or_404(reward_id)
    
    if current_user.points < reward.points_cost:
        flash('Not enough points')
        return redirect(url_for('rewards'))
    
    if reward.stock <= 0:
        flash('Out of stock')
        return redirect(url_for('rewards'))
    
    # Record transaction
    transaction = PointsTransaction(
        user_id=current_user.id,
        points=-reward.points_cost,
        transaction_type='spend',
        description=f'Redeemed {reward.name}'
    )
    
    current_user.points -= reward.points_cost
    reward.stock -= 1
    
    db.session.add(transaction)
    db.session.commit()
    
    flash('Reward redeemed successfully!')
    return redirect(url_for('rewards'))

@app.route('/get_queue_length')
def get_queue_length():
    queue_data = calculate_queue_length()
    return jsonify({
        'queue_length': queue_data['queue_length'],
        'estimated_wait_time': queue_data['estimated_wait_time'],
        'is_open': queue_data['is_open']
    })

@app.route('/host')
def host():
    return render_template('host.html')

def init_rewards():
    rewards = [
        # Study Support
        Reward(
            name="Study Room Priority Booking",
            description="Get priority booking rights for the study room for one week",
            points_cost=300,
            stock=15
        ),
        
        # Cafeteria Rewards
        Reward(
            name="Cafeteria Skip-the-Line Pass",
            description="Skip the line once during lunch time",
            points_cost=250,
            stock=20
        ),
        Reward(
            name="Snack Pack",
            description="A pack of healthy snacks from the school store",
            points_cost=100,
            stock=30
        ),
        
        # Special Privileges
        Reward(
            name="School Store Discount",
            description="20% off at the school store for one month",
            points_cost=400,
            stock=10
        )
    ]
    
    # Add rewards to database
    for reward in rewards:
        if not Reward.query.filter_by(name=reward.name).first():
            db.session.add(reward)
    
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_rewards()
    app.run(host='0.0.0.0', port=29999, debug=True) 
    