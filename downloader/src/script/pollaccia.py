import mysql.connector
from mysql.connector import Error
import argparse
import os
from datetime import datetime
import logging
import shutil
from dotenv import load_dotenv
import re # Added for regular expressions

# Load environment variables from .env file if present
load_dotenv()

LOCAL_MOUNT_PATH = os.environ.get("LOCAL_MOUNT_PATH") # The primary mounted volume path
ARCHIVE_PATH = os.path.join(LOCAL_MOUNT_PATH, "archive")
VBATT_SENSOR_NAME = 'V Batt.' # Consistent name for the battery sensor

# --- Database Configuration ---
# Use environment variables for configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'sensor_user'),
    'password': os.environ.get('DB_PASSWORD', 'sensor_password'),
    'database': os.environ.get('DB_NAME', 'sensordb')
}

LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"Logging level set to: {LOG_LEVEL_STR}")


def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        logging.info("Successfully connected to the database.")
        return conn
    except Error as e:
        logging.error(f"Error connecting to MySQL database: {e}")
        return None

def extract_vbatt_value(content):
    """
    Extracts the V Batt. value from the [INIZIO VBATT] section.
    Returns the value as a string, or None if not found/invalid.
    """
    try:
        vbatt_match = re.search(r'\[INIZIO VBATT\]\s*([\d\.-]+)\s*,?\s*\[FINE VBATT\]', content, re.DOTALL)
        if vbatt_match:
            vbatt_str = vbatt_match.group(1).strip()
            logging.info(f"Extracted V Batt. value: {vbatt_str}")
            return vbatt_str
        else:
            logging.warning("Could not find V Batt. section or value.")
            return None
    except Exception as e:
        logging.error(f"Error extracting V Batt. value: {e}")
        return None

def parse_file(filepath):
    """
    Parses the datalogger text file.
    Extracts V Batt. value and inserts it into every data row.
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return None

    # 1. Extract the V Batt. value from the header section
    vbatt_value = extract_vbatt_value(content)
    if vbatt_value is None:
        logging.error("V Batt. value is required but could not be parsed.")
        return None

    # 2. Parse DATA section
    try:
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
        # Example Header: DATE,Y_30.00,X_30.00,Y_5.50,X_5.50,
        header = [h.strip() for h in lines[0].split(',') if h.strip()]
        
        # Add the V Batt. sensor name to the header list
        header.append(VBATT_SENSOR_NAME) 
        logging.debug(f"Header: {header}")
        
        readings = []
        for line in lines[1:]:
            if not line.strip():
                continue
            
            # Split values. Note: lines often end with a comma, creating an empty last element
            values = []
            for v in line.split(','):
                # 1. Strip whitespace from the value
                stripped_v = v.strip()
                
                # 2. Check the conditions
                # This logic keeps the value if:
                #   a) it is NOT an empty string (e.g., '-.509', 'DATE')
                #   OR
                #   b) it is the string '0' (which would otherwise be considered False by v.strip())
                if stripped_v:  # True if string is NOT empty (e.g., '0' or '6.416')
                    values.append(stripped_v)
                elif stripped_v == '0': # Handles the explicit string "0" if the first check was bypassed
                    values.append(stripped_v)
            
            # Add the extracted V Batt. value to the list of data values
            values.append(vbatt_value) 
            logging.debug(f"Values: {values}")
            
            # Create the dictionary using the augmented header and values
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
    (Function remains identical to original)
    """
    cursor.execute("SELECT id FROM probe_headers WHERE probe_id = %s AND id = %s", (probe_id, sensor_name))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        cursor.execute("INSERT INTO probe_headers (probe_id, id) VALUES (%s, %s)", (probe_id, sensor_name))
        logging.info(f"Created new sensor '{sensor_name}' for probe ID {probe_id}.")
        return sensor_name

def insert_data_into_db(readings, probe_id):
    """
    Inserts the parsed readings into the database.
    (Function remains identical to original, as the data structure passed to it is the same)
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
                # Parse Timestamp (Updated format: '%d/%m/%Y %H.%M' -> '%d/%m/%Y %H.%M' or '%d/%m/%Y %H.%M')
                # Trying to parse with minutes/decimal format first, then simple hour if needed
                timestamp_str = row['DATE']
                try:
                    timestamp_dt = datetime.strptime(timestamp_str, '%d/%m/%Y %H.%M')
                except ValueError:
                    # Fallback for simpler hour format like "19/11/2025 21.0"
                    timestamp_dt = datetime.strptime(timestamp_str, '%d/%m/%Y %H.%f')
                    
            except (ValueError, KeyError) as e:
                logging.warning(f"Skipping row with invalid/missing DATE '{timestamp_str}'. Error: {e}")
                continue

            # Loop through all other columns (sensors)
            for sensor_name, value_str in row.items():
                if sensor_name == 'DATE' or not value_str:
                    continue 
                
                try:
                    sensor_id = get_or_create_sensor(cursor, probe_id, sensor_name)
                    value_float = float(value_str)

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
    
    # Check if the required path variable is set
    if not LOCAL_MOUNT_PATH:
        logging.error("LOCAL_MOUNT_PATH environment variable is not set. Cannot proceed with archiving.")
    else:
        readings = parse_file(args.filepath)
        if readings:
            success = insert_data_into_db(readings, args.probe_id)
            if success:
                move_to_archive(args.filepath)
            else:
                logging.error("Database insertion failed. File will not be moved.")
        else:
            logging.error("Parsing failed or returned no data. File will not be moved.")