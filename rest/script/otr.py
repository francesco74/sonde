import mysql.connector
from mysql.connector import Error
import argparse
import os
from datetime import datetime
import logging

# --- Database Configuration ---
# It's recommended to use environment variables for security.
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

def parse_datalogger_file(filepath):
    """
    Parses the specific datalogger text file format to extract sensor data and VBATT.
    Returns a dictionary containing the readings and the vbatt value.
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return None

    # --- Parse VBATT section ---
    vbatt_value = None
    try:
        vbatt_str = content.split('[INIZIO VBATT]')[1].split('[FINE VBATT]')[0].strip()
        # Remove comma and convert to float
        vbatt_value = float(vbatt_str.replace(',', ''))
        logging.info(f"Parsed VBATT value: {vbatt_value}")
    except (IndexError, ValueError) as e:
        logging.warning(f"Could not parse VBATT section. It might be missing or malformed. Error: {e}")

    # --- Parse DATA section ---
    try:
        data_section = content.split('[INIZIO DATI]')[1].split('[FINE DATI]')[0].strip()
        lines = data_section.splitlines()
        
        header = [h.strip() for h in lines[0].split(',') if h.strip()]
        
        readings = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = [v.strip() for v in line.split(',')]
            row_data = dict(zip(header, values))
            readings.append(row_data)
            
        logging.info(f"Successfully parsed {len(readings)} data rows from {filepath}.")
        return {"vbatt": vbatt_value, "readings": readings}
    except IndexError:
        logging.error("Could not find [INIZIO DATI] or [FINE DATI] section. Cannot parse readings.")
        return None


def get_or_create_sensor(cursor, practice_id, sensor_name):
    """
    Retrieves the ID of a sensor if it exists, otherwise creates it.
    Returns the sensor ID.
    """
    # Check if the sensor already exists for this practice
    cursor.execute("SELECT id FROM sensors WHERE practice_id = %s AND name = %s", (practice_id, sensor_name))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        # If not, create it
        cursor.execute("INSERT INTO sensors (practice_id, name) VALUES (%s, %s)", (practice_id, sensor_name))
        logging.info(f"Created new sensor '{sensor_name}' for practice ID {practice_id}.")
        return cursor.lastrowid

def insert_data_into_db(data, practice_name):
    """
    Inserts the parsed data, including VBATT, into the database.
    """
    conn = get_db_connection()
    if not conn:
        return
        
    readings = data.get('readings', [])
    vbatt = data.get('vbatt')

    if not readings:
        logging.warning("No readings to insert. Aborting database operation.")
        return

    try:
        cursor = conn.cursor()
        
        # 1. Get the ID of the practice from its name
        cursor.execute("SELECT id FROM practices WHERE name = %s", (practice_name,))
        practice_result = cursor.fetchone()
        if not practice_result:
            logging.error(f"Practice '{practice_name}' not found in the database. Aborting.")
            return
        practice_id = practice_result[0]
        logging.info(f"Found practice '{practice_name}' with ID: {practice_id}.")

        # 2. Handle VBATT insertion
        # We use the timestamp of the first reading for the VBATT value.
        first_timestamp_dt = None
        try:
            first_timestamp_str = readings[0]['DATE']
            first_timestamp_dt = datetime.strptime(first_timestamp_str, '%d/%m/%Y %H.%M')
        except (ValueError, KeyError, IndexError) as e:
            logging.error(f"Could not determine a valid timestamp for VBATT from the first data row. Error: {e}")

        if vbatt is not None and first_timestamp_dt is not None:
            try:
                vbatt_sensor_id = get_or_create_sensor(cursor, practice_id, "VBATT")
                cursor.execute(
                    "INSERT INTO sensor_readings (sensor_id, timestamp, value) VALUES (%s, %s, %s)",
                    (vbatt_sensor_id, first_timestamp_dt, vbatt)
                )
                logging.info(f"Inserted VBATT reading with timestamp {first_timestamp_dt}.")
            except Error as e:
                logging.error(f"Database error inserting VBATT data: {e}")


        # 3. Iterate over each row of data from the file
        for row in readings:
            try:
                timestamp_str = row['DATE']
                timestamp_dt = datetime.strptime(timestamp_str, '%d/%m/%Y %H.%M')
            except (ValueError, KeyError) as e:
                logging.warning(f"Skipping row due to invalid date format or missing DATE field: {row}. Error: {e}")
                continue

            # 4. For each sensor in the row, get/create its ID and insert the reading
            for sensor_name, value_str in row.items():
                if sensor_name == 'DATE' or not value_str:
                    continue # Skip the date field itself and any empty values
                
                try:
                    sensor_id = get_or_create_sensor(cursor, practice_id, sensor_name)
                    value_float = float(value_str)

                    insert_query = """
                        INSERT INTO sensor_readings (sensor_id, timestamp, value)
                        VALUES (%s, %s, %s)
                    """
                    cursor.execute(insert_query, (sensor_id, timestamp_dt, value_float))
                    logging.debug(f"Inserted reading for {sensor_name} at {timestamp_dt} with value {value_float}")

                except ValueError:
                    logging.warning(f"Could not convert value '{value_str}' to float for sensor '{sensor_name}'. Skipping.")
                except Error as e:
                    logging.error(f"Database error inserting data for {sensor_name}: {e}")
        
        # Commit all changes to the database
        conn.commit()
        logging.info("Data import completed successfully.")

    except Error as e:
        logging.error(f"A database error occurred: {e}")
        conn.rollback() # Roll back changes in case of error
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            logging.info("Database connection closed.")


if __name__ == '__main__':
    # --- Command-Line Argument Parser ---
    parser = argparse.ArgumentParser(description="Import datalogger files into the sensor database.")
    parser.add_argument("filepath", type=str, help="The full path to the datalogger TXT file.")
    parser.add_argument("practice_name", type=str, help="The name of the practice (e.g., 'Sonda-LU-01') to associate this data with.")
    
    args = parser.parse_args()
    
    # 1. Parse the file
    parsed_data = parse_datalogger_file(args.filepath)
    
    # 2. If parsing was successful, insert the data
    if parsed_data:
        insert_data_into_db(parsed_data, args.practice_name)

