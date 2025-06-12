# wlsa_canteen_code_system
This is a website designed for optimizing the canteen congestion problem by rewarding students who go to canteen during the idle time. The canteen should setup the host in the canteen. When students enter the canteen during the idle time, a dynamic code is shown on the host. The students then collect points by redeeming the code shown in the canteen.
# WLSA Cafeteria Queue Management System

A system to manage cafeteria queues and encourage students to visit during off-peak hours through a points-based reward system.

## Features

- User registration and authentication
- Dynamic QR code generation for check-ins
- Points system based on queue length
- Points redemption for rewards
- Queue length monitoring
- One check-in per day limit
- Secure QR code verification

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize the database:
```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
```

3. Add some initial rewards:
```bash
python
>>> from app import app, db, Reward
>>> with app.app_context():
...     rewards = [
...         Reward(name="School Store Voucher", description="$5 voucher for the school store", points_cost=100, stock=50),
...         Reward(name="Cafeteria Pass", description="Skip the line once", points_cost=200, stock=20),
...         Reward(name="Study Room Pass", description="Access to the quiet study room for one day", points_cost=150, stock=30)
...     ]
...     db.session.add_all(rewards)
...     db.session.commit()
```

4. Run the application:
```bash
python app.py
```

## Usage

### For Students

1. Register an account at `/register`
2. Log in at `/login`
3. Visit the dashboard to see your points and check-in status
4. Scan the QR code displayed in the cafeteria to check in
5. Visit the rewards page to redeem your points

### For Cafeteria Staff

1. Access the host interface at `/host`
2. Click on the queue length number to update it
3. The QR code will automatically refresh every 30 seconds
4. Points are automatically calculated based on queue length:
   - Queue < 5: 10 points
   - Queue < 10: 5 points
   - Queue < 15: 2 points
   - Queue >= 15: 0 points

## Security Features

- Time-based QR codes that expire after 30 seconds
- One check-in per day limit
- Secure password hashing
- Session-based authentication
- Protection against QR code screenshot reuse

## Technical Details

- Built with Flask
- SQLite database
- Bootstrap 5 for the frontend
- HTML5 QR code scanner
- TOTP for QR code generation 