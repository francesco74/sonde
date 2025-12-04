from flask import Flask, jsonify, request, g
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling, Error
from datetime import datetime, timedelta, timezone
from werkzeug.security import check_password_hash
import logging
import re
import os
import argparse
import jwt
from functools import wraps
from dotenv import load_dotenv

load_dotenv() 

LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"Logging level set to: {LOG_LEVEL_STR}")

# --- Database Configuration ---
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'sensor_user'),
    'password': os.environ.get('DB_PASSWORD', 'sensor_password'),
    'database': os.environ.get('DB_NAME', 'sensordb')
}

app = Flask(__name__)
# Secret key for JWT encoding/decoding
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
if app.config['SECRET_KEY'] is None:
    # Use logger/print before exiting for visibility
    logging.error("FLASK_SECRET_KEY environment variable not set. Exiting.")
    exit(1)

# Ensure the database pool connection attempt is wrapped in a try/except
try:
    db_pool = pooling.MySQLConnectionPool(
        pool_name="sensor_pool",
        pool_size=5,  # Adjust based on traffic
        pool_reset_session=True,
        **DB_CONFIG # Use the existing config dictionary
    )
    app.logger.info("Database connection pool initialized successfully.")
except mysql.connector.Error as err:
    app.logger.critical(f"Failed to initialize database pool: {err}")
    # Consider what to do here: exit, or allow startup and fail on first db access
    # For now, we allow startup, as connection attempts are wrapped in get_db()
    db_pool = None 

LATEST_DATA_DAYS = int(os.environ.get('LATEST_DATA_DAYS', 7))


# --- Database Helper ---
def get_db():
    if 'db' not in g:
        try:
            # Check if pool is available before getting a connection
            if db_pool is None:
                app.logger.error("Database pool is not initialized.")
                g.db = None
                return g.db
                
            # Get a connection from the pool
            g.db = db_pool.get_connection()
        except mysql.connector.Error as err:
            app.logger.error(f"DB Connection Error (get_db): {err}")
            g.db = None
        except Exception as e:
            app.logger.error(f"Unexpected error in get_db: {e}")
            g.db = None
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception as close_err:
            app.logger.error(f"Error closing DB connection: {close_err}")


# --- Helper: Fetch User Role IDs ---
def get_user_role_ids(user_id):
    """Fetches the list of role IDs assigned to a user, handling DB errors."""
    conn = get_db()
    if conn is None:
        app.logger.error("Database unavailable during role check")
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        query = "SELECT role_id FROM user_roles WHERE user_id = %s"
        
        app.logger.debug(f"Fetching role IDs for user_id: {user_id}")
        cursor.execute(query, (user_id,))
        
        role_ids = [row[0] for row in cursor.fetchall()]
        app.logger.debug(f"Role IDs found for user_id {user_id}: {role_ids}")
        return role_ids
    except mysql.connector.Error as db_err:
        app.logger.error(f"Database error in get_user_role_ids for user {user_id}: {db_err}")
        return []
    except Exception as e:
        app.logger.error(f"Unexpected error in get_user_role_ids for user {user_id}: {e}")
        return []
    finally:
        if cursor:
            cursor.close()

# --- JWT Decorator ---
# NOTE: token_required already has good exception handling for JWT errors

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Check Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({'status': 'error', 'result': 'Token is missing!'}), 401
        
        try:
            # Decode token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            g.user_id = data['user_id']
            g.username = data['username']
            # Fetch role IDs fresh from DB for security
            g.user_role_ids = get_user_role_ids(g.user_id)
        except jwt.ExpiredSignatureError:
            return jsonify({'status': 'error', 'result': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'status': 'error', 'result': 'Token is invalid!'}), 401
        except Exception as e:
            app.logger.error(f"Error during token processing: {e}")
            return jsonify({'status': 'error', 'result': 'An error occurred during authentication.'}), 500
        
        return f(*args, **kwargs)
    return decorated

# --- API ENDPOINTS ---

@app.route('/login', methods=['POST'])
def login():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({"status": "error", "result": "Username and password required"}), 400

        conn = get_db()
        if not conn:
            return jsonify({"status": "error", "result": "Server error: Database unavailable"}), 500
        
        cursor = conn.cursor(dictionary=True)
        
        # Schema: users(id, username, password)
        app.logger.debug(f"Querying user: {username}")
        cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        # Verify password
        if user and (check_password_hash(user['password'], password) or user['password'] == password):
            # Generate JWT
            token = jwt.encode({
                'user_id': user['id'],
                'username': user['username'],
                'exp': datetime.now(timezone.utc) + timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm="HS256")
            
            app.logger.info(f"Login successful: {username}")
            return jsonify({
                "status": "ok", 
                "result": "Login successful",
                "token": token 
            })
        else:
            app.logger.warning(f"Invalid login: {username}")
            return jsonify({"status": "error", "result": "Invalid credentials"})
            
    except mysql.connector.Error as db_err:
        app.logger.error(f"Database error during login for user {username}: {db_err}")
        # No rollback needed for SELECT/query, but good practice to handle general DB failure
        return jsonify({"status": "error", "result": "Server error: Database failure"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected exception during login: {e}")
        # Catch all other exceptions (e.g., KeyError on data.get)
        return jsonify({"status": "error", "result": "An internal error occurred"}), 500
    finally:
        # Cursor is implicitly closed by 'with conn.cursor()' in the original, but here we manage it explicitly
        if cursor:
            cursor.close()
        # NOTE: conn.close() is handled by @app.teardown_appcontext

@app.route('/logout', methods=['POST'])
def logout():
    # JWT is stateless
    return jsonify({"status": "ok", "result": "Logout successful"})

@app.route('/get_tree', methods=['GET'])
@token_required
def get_tree():
    user_role_ids = g.user_role_ids
    username = g.username
    
    app.logger.debug(f"get_tree called for user: {username}, role IDs: {user_role_ids}")

    if not user_role_ids:
        app.logger.debug("User has no roles, returning empty tree.")
        return jsonify({"status": "ok", "result": []})

    conn = get_db()
    if conn is None:
        app.logger.error("Database unavailable for get_tree")
        return jsonify({"status": "error", "result": "Server error: Database unavailable"}), 500
    
    cursor = None
    results = []
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Create placeholders for IN clause
        format_strings = ','.join(['%s'] * len(user_role_ids))
        
        query = f"""
            SELECT id, parent, description, lat, lng, leaf
            FROM probes
            WHERE requested_role IN ({format_strings})
            ORDER BY parent, id
        """
        
        app.logger.debug(f"Executing get_tree query with role IDs: {user_role_ids}")
        cursor.execute(query, tuple(user_role_ids))
        results = cursor.fetchall()
        app.logger.debug(f"Query returned {len(results)} rows.")
        
    except mysql.connector.Error as db_err:
        app.logger.error(f"Database error in get_tree for user {username}: {db_err}")
        return jsonify({"status": "error", "result": "Server error: Database failure"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in get_tree for user {username}: {e}")
        return jsonify({"status": "error", "result": "An internal error occurred"}), 500
    finally:
        if cursor:
            cursor.close()

    # --- Tree Structuring Logic (outside try block as it's not DB-dependent) ---
    tree_structure = {} # Key: ID (string) -> List of Probes
    macrogroup_descriptions = {} # Key: ID (string) -> Description
    
    # 1. First pass: Identify Macrogroups (branches where leaf=0)
    for row in results:
        if row['leaf'] == 0:
            mg_id = str(row['id'])
            mg_desc = row['description']
            
            # Store description keyed by ID
            macrogroup_descriptions[mg_id] = mg_desc
            
            if mg_id not in tree_structure:
                tree_structure[mg_id] = []

    # 2. Second pass: Add Probes (leaves where leaf=1) to their parents
    for row in results:
        if row['leaf'] == 1:
            parent_id_raw = row['parent']
            if parent_id_raw is None:
                continue

            parent_id_str = str(parent_id_raw)
            
            # Ensure the parent entry exists in the tree structure
            if parent_id_str not in tree_structure:
                # This handles cases where a leaf's parent wasn't fetched as a macrogroup 
                # (e.g., the parent itself doesn't require the user's role ID but the leaf does)
                # For this application's logic, we should probably ignore it or create a placeholder.
                # Assuming the query logic guarantees parent is fetched if needed by a leaf, we proceed.
                continue 
            
            try:
                # Safely convert lat/lng before appending
                lat_val = float(row['lat'])
                lng_val = float(row['lng'])
            except (TypeError, ValueError):
                app.logger.warning(f"Skipping probe {row['id']} due to invalid lat/lng: {row['lat']}, {row['lng']}")
                continue # Skip this row if coordinates are invalid

            tree_structure[parent_id_str].append({
                "id": str(row['id']), 
                "description": row['description'],
                "latitude": lat_val,
                "longitude": lng_val
            })

    # Format for Flutter
    formatted_tree = []
    for mg_id, probes in tree_structure.items():
        # Get description using ID, or fallback to "Group <ID>" if description missing
        mg_desc = macrogroup_descriptions.get(mg_id, f"Group {mg_id}")
        
        formatted_tree.append({
            "macrogroup_id": mg_id,           # NEW: ID
            "macrogroup_description": mg_desc, # NEW: Description
            "probes": probes
        })
    
    return jsonify({"status": "ok", "result": formatted_tree})

def _fetch_sensor_data(probe_id_str, start_date, end_date):
    """Helper to fetch data from probe_data table, handling DB and conversion errors."""
    user_role_ids = g.user_role_ids
    
    if not user_role_ids:
        return None, 403, "No roles assigned"

    conn = get_db()
    if conn is None:
        app.logger.error("Database unavailable in _fetch_sensor_data")
        return None, 500, "Database unavailable"
    
    cursor = None
    try:
        probe_id = int(probe_id_str)
    except ValueError:
        return None, 400, "Invalid probe ID format"

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Check permission using Probe ID directly
        format_strings = ','.join(['%s'] * len(user_role_ids))
        query_probe = f"""
            SELECT id FROM probes 
            WHERE id = %s AND leaf = 1 AND requested_role IN ({format_strings})
        """
        
        params = (probe_id,) + tuple(user_role_ids)
        
        app.logger.debug(f"Searching probes using {query_probe} with parameters {params}")
        cursor.execute(query_probe, params)
        probe = cursor.fetchone()

        if not probe:
            app.logger.warning(f"Probe ID '{probe_id}' not found or access denied.")
            return None, 403, "Probe not found or access denied"

        # 2. Fetch Data
        query_data = """
            SELECT value_id, timestamp, value
            FROM probe_data
            WHERE probe_id = %s AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp ASC
        """

        app.logger.debug(f"Searching data using {query_data} with parameters {probe_id}, {start_date}, {end_date}")
        cursor.execute(query_data, (probe_id, start_date, end_date))
        rows = cursor.fetchall()

    except mysql.connector.Error as db_err:
        app.logger.error(f"Database error in _fetch_sensor_data for probe {probe_id}: {db_err}")
        return None, 500, "Server error: Database failure"
    except Exception as e:
        app.logger.error(f"Unexpected error during database operations in _fetch_sensor_data: {e}")
        return None, 500, "An internal server error occurred"
    finally:
        if cursor:
            cursor.close()

    # 3. Group by Sensor Type (value_id) - Data processing logic
    data_map = {}
    for row in rows:
        sensor_type = row['value_id']
        if sensor_type not in data_map:
            data_map[sensor_type] = []
        
        try:
            val = float(row['value'])

            dt = row['timestamp']
            # If the DB returns a naive datetime (no timezone info), force it to UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp()) * 1000
            
            data_map[sensor_type].append({
                "timestamp": ts,
                "value": val
            })
        except ValueError:
            # Log the bad data point and continue
            app.logger.warning(f"Skipping non-numeric value for probe {probe_id}, value_id {sensor_type}: {row['value']}")
            continue 
        except Exception as conversion_e:
             app.logger.error(f"Unexpected conversion error for probe {probe_id}: {conversion_e}")
             continue


    result = [{"name": k, "values": v} for k, v in data_map.items()]
    return result, 200, None

@app.route('/get_latest_data', methods=['GET'])
@token_required
def get_latest_data():
    try:
        probe_id_str = request.args.get('practice_id') # Flutter sends ID in this param
        
        if not probe_id_str:
            return jsonify({"status": "error", "result": "Probe ID required"}), 400

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=LATEST_DATA_DAYS)
        
        data, status, err = _fetch_sensor_data(probe_id_str, start_date, end_date)
        
        if status != 200:
            return jsonify({"status": "error", "result": err}), status

        return jsonify({
            "status": "ok",
            "data": {
                "startDate": start_date.strftime('%Y-%m-%d'),
                "endDate": end_date.strftime('%Y-%m-%d'),
                "series": data
            }
        })
    except Exception as e:
        app.logger.error(f"Unexpected exception in get_latest_data: {e}")
        return jsonify({"status": "error", "result": "An internal error occurred"}), 500


@app.route('/get_data', methods=['GET'])
@token_required
def get_data():
    try:
        probe_id_str = request.args.get('practice_id')
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')

        if not all([probe_id_str, start_str, end_str]):
            return jsonify({"status": "error", "result": "Probe ID, start_date, and end_date required"}), 400

        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
            # Set time to end of day for the end date
            end_date = end_date.replace(hour=23, minute=59, second=59)
            # Make dates timezone-aware (assuming they represent local dates that should be treated as UTC dates for DB query)
            start_date = start_date.replace(tzinfo=timezone.utc)
            end_date = end_date.replace(tzinfo=timezone.utc)
            
        except (ValueError, TypeError) as e:
            app.logger.warning(f"Invalid date format received: {e}")
            return jsonify({"status": "error", "result": "Invalid date format. Use YYYY-MM-DD"}), 400

        data, status, err = _fetch_sensor_data(probe_id_str, start_date, end_date)

        if status != 200:
            return jsonify({"status": "error", "result": err}), status

        return jsonify({"status": "ok", "data": data})
        
    except Exception as e:
        app.logger.error(f"Unexpected exception in get_data: {e}")
        return jsonify({"status": "error", "result": "An internal error occurred"}), 500


# --- Startup ---
if __name__ == '__main__':
    # Configure mysql.connector logger to avoid excessive output, if needed
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)

    origin_regex = re.compile(r"http://(localhost|127\.0\.0\.1):\d+")
    CORS(app, resources={r"/*": {"origins": origin_regex}}, supports_credentials=True, allow_headers=["Content-Type", "Authorization"])

    app.run(debug=(LOG_LEVEL_STR == 'DEBUG'), port=5000, host='0.0.0.0')