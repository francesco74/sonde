import mysql.connector
from mysql.connector import Error
import argparse
import os
from werkzeug.security import generate_password_hash
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Database Configuration ---
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'sensor_user'),
    'password': os.environ.get('DB_PASSWORD', 'sensor_password'),
    'database': os.environ.get('DB_NAME', 'sensordb')
}

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        logging.error(f"Error connecting to database: {e}")
        return None

def create_user(username, password, roles):
    """Creates a new user and assigns roles."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # 1. Check if user exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            logging.error(f"User '{username}' already exists.")
            return

        # 2. Hash password
        hashed_password = generate_password_hash(password)

        # 3. Insert User
        # Using 'password_hash' column to match server.py convention
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed_password)
        )
        user_id = cursor.lastrowid
        logging.info(f"User '{username}' created with ID: {user_id}")

        # 4. Assign Roles
        if roles:
            for role_name in roles:
                # Find role ID
                cursor.execute("SELECT id FROM roles WHERE role = %s", (role_name,))
                role_result = cursor.fetchone()
                
                if role_result:
                    role_id = role_result[0]
                    cursor.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                        (user_id, role_id)
                    )
                    logging.info(f"Assigned role '{role_name}' to user '{username}'.")
                else:
                    logging.warning(f"Role '{role_name}' not found in database. Skipping assignment.")

        conn.commit()
        logging.info("User creation process completed successfully.")

    except Error as e:
        logging.error(f"Database error: {e}")
        conn.rollback()
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create a new user in the sensor database.")
    parser.add_argument("username", type=str, help="The username for the new user.")
    parser.add_argument("password", type=str, help="The raw password for the new user.")
    parser.add_argument(
        "--roles", 
        nargs="+", 
        default=[], 
        help="List of roles to assign (e.g., --roles Admin User)"
    )
    
    args = parser.parse_args()
    
    create_user(args.username, args.password, args.roles)