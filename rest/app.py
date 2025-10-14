from flask import Flask, jsonify, request, session, g
from flask_cors import CORS
from flask_session import Session
import mysql.connector
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import re
import os
import argparse

# --- Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'sensor_user',
    'password': 'sensor_password',
    'database':  'sensordb'
}

app = Flask(__name__)


# --- Database Connection Management using Flask Context ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        try:
            g.db = mysql.connector.connect(**DB_CONFIG)
            app.logger.debug("Database connection established for this request.")
        except mysql.connector.Error as err:
            app.logger.error(f"Critical DB connection error: {err}")
            g.db = None
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        app.logger.debug("Database connection closed.")


# --- API ENDPOINTS ---

@app.route('/login', methods=['POST'])
def login():
    """Authenticates the user, retrieves permissions, and creates a session."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    app.logger.debug(f"Login attempt for user: '{username}'")

    if not username or not password:
        app.logger.warning("Login attempt with missing username or password.")
        return jsonify({"status": "error", "result": "Username and password are required."}), 400

    conn = get_db()
    if not conn:
        return jsonify({"status": "error", "result": "Server error."}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    if user and check_password_hash(user['password_hash'], password):
        user_id = user['id']
        
        cursor.execute("SELECT macrogroup_id FROM user_macrogroup_permissions WHERE user_id = %s", (user_id,))
        macro_permissions = cursor.fetchall()
        accessible_macrogroups = [p['macrogroup_id'] for p in macro_permissions]
        
        cursor.execute("SELECT practice_id FROM user_practice_permissions WHERE user_id = %s", (user_id,))
        practice_permissions = cursor.fetchall()
        accessible_practices = [p['practice_id'] for p in practice_permissions]

        session.clear()
        session['user_id'] = user_id
        session['username'] = user['username']
        session['accessible_macrogroups'] = accessible_macrogroups
        session['accessible_practices'] = accessible_practices
        
        app.logger.info(f"Authentication successful for '{username}'.")
        return jsonify({"status": "ok", "result": "Authentication successful."})
    else:
        app.logger.warning(f"Invalid credentials for login attempt by user: {username}")
        return jsonify({"status": "error", "result": "Invalid credentials."}), 401

@app.route('/logout', methods=['POST'])
def logout():
    """Logs out the user by clearing the session."""
    username = session.get('username', 'unknown')
    session.clear()
    app.logger.info(f"Logout successful for user: {username}")
    return jsonify({"status": "ok", "result": "Logout successful."})

@app.route('/get_tree', methods=['GET'])
def get_tree():
    """Returns the practice tree by combining permissions."""
    if 'user_id' not in session:
        app.logger.warning(f"Unauthorized access to /get_tree from IP: {request.remote_addr}")
        return jsonify({"status": "error", "result": "Authorization required."}), 401

    username = session['username']
    accessible_macrogroups = session.get('accessible_macrogroups', [])
    accessible_practices = session.get('accessible_practices', [])
    app.logger.info(f"Fetching practice tree for user: {username}")

    if not accessible_macrogroups and not accessible_practices:
        app.logger.debug(f"User {username} has no permissions, returning empty tree.")
        return jsonify({"status": "ok", "result": []})

    conn = get_db()
    if not conn:
        return jsonify({"status": "error", "result": "Server error."}), 500

    cursor = conn.cursor(dictionary=True)
    
    query_parts = []
    params = []
    
    if accessible_macrogroups:
        macro_placeholders = ', '.join(['%s'] * len(accessible_macrogroups))
        query_parts.append(f"p.macrogroup_id IN ({macro_placeholders})")
        params.extend(accessible_macrogroups)
        
    if accessible_practices:
        practice_placeholders = ', '.join(['%s'] * len(accessible_practices))
        query_parts.append(f"p.id IN ({practice_placeholders})")
        params.extend(accessible_practices)
        
    where_clause = " OR ".join(query_parts)
    
    query = f"""
        SELECT 
            m.name as macrogroup_name,
            p.id as practice_id,
            p.name, 
            p.description, 
            p.latitude, 
            p.longitude 
        FROM practices p
        JOIN macrogroups m ON p.macrogroup_id = m.id
        WHERE {where_clause}
        ORDER BY m.name, p.name
    """
    
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    
    tree_data = {}
    processed_practices = set()
    for row in results:
        if row['practice_id'] in processed_practices:
            continue

        macrogroup_name = row['macrogroup_name']
        if macrogroup_name not in tree_data:
            tree_data[macrogroup_name] = []
        
        tree_data[macrogroup_name].append({
            "name": row['name'],
            "description": row['description'],
            "latitude": float(row['latitude']),
            "longitude": float(row['longitude'])
        })
        processed_practices.add(row['practice_id'])
    
    formatted_tree = [
        {"macrogroup_name": name, "probes": probes}
        for name, probes in tree_data.items()
    ]
    
    app.logger.debug(f"Built tree with {len(formatted_tree)} macrogroups for user {username}.")
    return jsonify({"status": "ok", "result": formatted_tree})


@app.route('/get_latest_data', methods=['GET'])
def get_latest_data():
    """
    Returns the latest 15 days of sensor data for a specific practice.
    This new endpoint handles the initial data load upon probe selection.
    """
    if 'user_id' not in session:
        return jsonify({"status": "error", "result": "Authorization required."}), 401
        
    practice_name = request.args.get('practice_id')
    if not practice_name:
        return jsonify({"status": "error", "result": "Missing 'practice_id' parameter."}), 400

    # Calculate date range: today and the 14 days prior
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)
    
    # Reuse the logic from get_data but with a fixed date range
    data_response = _fetch_sensor_data(practice_name, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    
    # Check if _fetch_sensor_data returned an error response
    if isinstance(data_response, tuple):
        return data_response # Forward the error response tuple (jsonify_object, status_code)

    # If successful, wrap it in the format expected by InitialSensorData model
    return jsonify({
        "status": "ok",
        "data": {
            "startDate": start_date.strftime('%Y-%m-%d'),
            "endDate": end_date.strftime('%Y-%m-%d'),
            "series": data_response # This is the list of sensor series
        }
    })


@app.route('/get_data', methods=['GET'])
def get_data_endpoint():
    """Endpoint for manual data fetching with a custom date range."""
    if 'user_id' not in session:
        return jsonify({"status": "error", "result": "Authorization required."}), 401
        
    practice_name = request.args.get('practice_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not all([practice_name, start_date_str, end_date_str]):
        return jsonify({"status": "error", "result": "Missing parameters."}), 400

    # The actual data fetching is now in a helper function
    data_response = _fetch_sensor_data(practice_name, start_date_str, end_date_str)
    
    if isinstance(data_response, tuple):
        return data_response

    return jsonify({"status": "ok", "data": data_response})


def _fetch_sensor_data(practice_name, start_date_str, end_date_str):
    """
    A helper function to fetch sensor data. Can be used by multiple endpoints.
    Returns a list of sensor data or a tuple (error_json, status_code) on failure.
    """
    username = session['username']
    
    conn = get_db()
    if not conn:
        return jsonify({"status": "error", "result": "Server error."}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, macrogroup_id FROM practices WHERE name = %s", (practice_name,))
    practice = cursor.fetchone()

    if not practice:
        return jsonify({"status": "error", "result": "Practice not found."}), 404

    practice_id = practice['id']
    practice_macrogroup_id = practice['macrogroup_id']
    accessible_macrogroups = session.get('accessible_macrogroups', [])
    accessible_practices = session.get('accessible_practices', [])

    has_permission = (practice_macrogroup_id in accessible_macrogroups) or \
                     (practice_id in accessible_practices)

    if not has_permission:
        app.logger.warning(f"Permission denied for '{username}' on practice '{practice_name}' (ID: {practice_id})")
        return jsonify({"status": "error", "result": "Permission denied for this practice."}), 403
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"status": "error", "result": "Invalid date format. Use YYYY-MM-DD."}), 400

    query_data = """
        SELECT s.name AS sensor_name, sr.timestamp, sr.value
        FROM sensor_readings sr
        JOIN sensors s ON sr.sensor_id = s.id
        WHERE s.practice_id = %s AND sr.timestamp BETWEEN %s AND %s
        ORDER BY sr.timestamp;
    """
    cursor.execute(query_data, (practice_id, start_date, end_date))
    readings = cursor.fetchall()
    
    sensor_data_map = {}
    for reading in readings:
        sensor_name = reading['sensor_name']
        if sensor_name not in sensor_data_map:
            sensor_data_map[sensor_name] = []
        
        sensor_data_map[sensor_name].append({
            "timestamp": int(reading['timestamp'].timestamp()),
            "value": float(reading['value'])
        })
    
    formatted_data = [
        {"name": name, "values": values} 
        for name, values in sensor_data_map.items()
    ]
    
    return formatted_data


@app.route('/create_user', methods=['POST'])
def create_user():
    """Utility endpoint to create a new user with a hashed password."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400

    hashed_password = generate_password_hash(password)

    conn = get_db()
    if not conn:
        return jsonify({"status": "error", "result": "Server error."}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
        conn.commit()
        app.logger.info(f"New user '{username}' created successfully.")
        return jsonify({"status": "ok", "message": f"User {username} created"}), 201
    except mysql.connector.Error as err:
        app.logger.error(f"Error creating user '{username}': {err}")
        return jsonify({"status": "error", "message": "This username already exists."}), 409

# --- Application Startup ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sensor Data REST Server')
    parser.add_argument(
        '--loglevel',
        type=str.upper,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set the logging level.'
    )
    args = parser.parse_args()
    log_level = getattr(logging, args.loglevel, logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    app.logger.handlers.clear()
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)
    
    app.logger.info('--- Starting Sensor Server ---')
    app.logger.info(f'Log level set to: {args.loglevel}')

    debug_mode = (args.loglevel == 'DEBUG')

    if debug_mode:
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        app.config['SESSION_COOKIE_SECURE'] = False
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.logger.info('DEVELOPMENT MODE: Cookie Security disabled for HTTP')
    else:
        app.config['SESSION_COOKIE_SAMESITE'] = 'None'
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.logger.info('PRODUCTION MODE: Cookie Security enabled for HTTPS')
    
    if debug_mode:
        origin_regex = re.compile(r"http://(localhost|127\.0\.0\.1):\d+")
        CORS(
            app,
            resources={r"/*": {"origins": origin_regex}},
            supports_credentials=True,
            allow_headers=["Content-Type"]
        )
        app.logger.info('CORS enabled for localhost (any port)')
    else:
        allowed_origins = os.environ.get('ALLOWED_ORIGINS', '').split(',')
        CORS(
            app,
            resources={r"/*": {"origins": allowed_origins}},
            supports_credentials=True,
            allow_headers=["Content-Type"]
        )
        app.logger.info(f'CORS enabled for: {allowed_origins}')
    
    app.config["SECRET_KEY"] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
    app.config["SESSION_TYPE"] = "filesystem"
    
    Session(app)
    
    app.run(debug=debug_mode, port=5000)

