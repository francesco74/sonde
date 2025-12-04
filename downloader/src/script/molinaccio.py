import mysql.connector
from mysql.connector import Error
import argparse
import os
from datetime import datetime
import logging
import shutil
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

LOCAL_MOUNT_PATH = os.environ.get("LOCAL_MOUNT_PATH") # The primary mounted volume path
ARCHIVE_PATH = os.path.join(LOCAL_MOUNT_PATH, "archive")

# --- Database Configuration ---
# Use environment variables for configuration
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
        logging.info("Successfully connected to the database.")
        return conn
    except Error as e:
        logging.error(f"Error connecting to MySQL database: {e}")
        return None

def parse_file(filepath):
    """
    Parses the datalogger text file.
    Ignores [INIZIO VBATT] and only processes the [INIZIO DATI] section.
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return None

    # --- Parse DATA section ---
    try:
        # Find the data block
        if '[INIZIO DATI]' in content and '[FINE DATI]' in content:
            data_section = content.split('[INIZIO DATI]')[1].split('[FINE DATI]')[0].strip()
        else:
            logging.error("Could not find [INIZIO DATI] or [FINE DATI] section. Cannot parse readings.")
            return None

        lines = data_section.splitlines()
        if not lines:
             logging.warning("Data section is empty.")
             return []
        
        # Parse Header: Splitting by comma and removing empty strings/whitespace
        # Example Header: DATE,F1,F2,Y_1,X_1,Y_2,X_2,TEMP,V Batt.,
        header = [h.strip() for h in lines[0].split(',') if h.strip()]
        
        readings = []
        for line in lines[1:]:
            if not line.strip():
                continue
            
            # Split values. Note: lines often end with a comma, creating an empty last element
            values = [v.strip() for v in line.split(',')]
            
            # Zip strictly pairs up to the length of the shortest list.
            # Since 'header' doesn't include the trailing empty element, this correctly handles the trailing comma in data.
            row_data = dict(zip(header, values))
            readings.append(row_data)
            
        logging.info(f"Successfully parsed {len(readings)} data rows from {filepath}.")
        logging.debug(f"Ingested data: \n {readings}.")
        return readings
    except IndexError:
        logging.error("Error parsing data section structure.")
        return None


def get_or_create_sensor(cursor, probe_id, sensor_name):
    """
    Retrieves the ID of a sensor if it exists, otherwise creates it.
    """
    cursor.execute("SELECT id FROM probe_headers WHERE probe_id = %s AND id = %s", (probe_id, sensor_name))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        cursor.execute("INSERT INTO probe_headers (probe_id, id) VALUES (%s, %s)", (probe_id, sensor_name))
        logging.info(f"Created new sensor '{sensor_name}' for probe ID {probe_id}.")
        # Since ID in probe_headers is not auto-increment (it's the sensor_name string),
        # we return the sensor_name directly.
        return sensor_name

def insert_data_into_db(readings, probe_id):
    """
    Inserts the parsed readings into the database.
    Returns True if successful, False otherwise.
    """
    conn = get_db_connection()
    if not conn:
        return False
        
    if not readings:
        logging.warning("No readings to insert. Aborting.")
        return False

    try:
        cursor = conn.cursor()
        
        # 1. Find Practice ID
        cursor.execute("SELECT description FROM probes WHERE id = %s", (probe_id,))
        practice_result = cursor.fetchone()
        if not practice_result:
            logging.error(f"Probe ID '{probe_id}' not found in database. Please create it first.")
            return False
        probe_description = practice_result[0]
        logging.info(f"Processing data for Probe: '{probe_description}' (ID: {probe_id})")

        # 2. Insert Row Data
        count = 0
        for row in readings:
            try:
                # Parse Timestamp
                timestamp_str = row['DATE']
                timestamp_dt = datetime.strptime(timestamp_str, '%d/%m/%Y %H.%M')
            except (ValueError, KeyError) as e:
                logging.warning(f"Skipping row with invalid/missing DATE. Error: {e}")
                continue

            # Loop through all other columns (sensors)
            # This naturally handles 'V Batt.' as just another sensor
            for sensor_name, value_str in row.items():
                if sensor_name == 'DATE' or not value_str:
                    continue 
                
                try:
                    # Dynamic sensor creation (F1, F2, Y_1, V Batt., etc.)
                    sensor_id = get_or_create_sensor(cursor, probe_id, sensor_name)
                    value_float = float(value_str)

                    # Fixed missing placeholder in SQL
                    cursor.execute("""
                        INSERT INTO probe_data (probe_id, value_id, timestamp, value)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE value = VALUES(value)
                    """, (probe_id, sensor_id, timestamp_dt, value_float))
                    
                except ValueError:
                    logging.warning(f"Invalid numeric value '{value_str}' for sensor '{sensor_name}' at {timestamp_dt}")
                except Error as e:
                    logging.error(f"Database error inserting {sensor_name}: {e}")
            count += 1
        
        conn.commit()
        logging.info(f"Import complete. Processed {count} timestamps.")
        return True

    except Error as e:
        logging.error(f"Database transaction error: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def move_to_archive(filepath):
    """Moves the processed file to the archive directory."""
    try:
        # Create archive directory if it doesn't exist
        if not os.path.exists(ARCHIVE_PATH):
            os.makedirs(ARCHIVE_PATH)
            logging.info(f"Created archive directory: {ARCHIVE_PATH}")

        filename = os.path.basename(filepath)
        destination = os.path.join(ARCHIVE_PATH, filename)
        
        # Handle potential filename conflicts in archive
        if os.path.exists(destination):
            base, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_filename = f"{base}_{timestamp}{ext}"
            destination = os.path.join(ARCHIVE_PATH, new_filename)
            logging.info(f"File with same name exists in archive. Renaming to: {new_filename}")

        shutil.move(filepath, destination)
        logging.info(f"Successfully moved file to: {destination}")
    except OSError as e:
        logging.error(f"Error moving file to archive: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Import datalogger files.")
    parser.add_argument("filepath", type=str, help="Path to the file")
    parser.add_argument("probe_id", type=int, help="ID of probe in the DB")
    
    args = parser.parse_args()
    
    readings = parse_file(args.filepath)
    if readings:
        success = insert_data_into_db(readings, args.probe_id)
        if success:
            move_to_archive(args.filepath)
        else:
            logging.error("Database insertion failed. File will not be moved.")
    else:
        logging.error("Parsing failed or returned no data. File will not be moved.")