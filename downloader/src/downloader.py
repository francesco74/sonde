import os
import ftplib
import logging
import fnmatch
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector
import subprocess 
import shlex 

# --- Determine Script Location ---
# This line gets the absolute directory path of the currently running Python script (ftp_downloader.py).
DOWNLOADER_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the absolute path to the directory containing the post-download scripts.
SCRIPT_ROOT_PATH = os.path.join(DOWNLOADER_SCRIPT_DIR, "script") 
# ---------------------------------

# --- Configuration & Logging Setup ---
# 1. Load environment variables from .env file (for local development/testing)
load_dotenv() 

# 2. Configure logging dynamically
LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"Logging level set to: {LOG_LEVEL_STR}")

# Get FTP connection details
FTP_HOST = os.environ.get("FTP_HOST")
FTP_USER = os.environ.get("FTP_USER")
FTP_PASS = os.environ.get("FTP_PASS")

LOCAL_MOUNT_PATH = os.environ.get("LOCAL_MOUNT_PATH") # The primary mounted volume path
ARCHIVE_PATH = os.path.join(LOCAL_MOUNT_PATH, "archive")

# Get Database connection details from environment variables
DB_HOST = os.environ.get("DB_HOST")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

def execute_post_download_script(script_command: str, probe_id: str, local_file_path: str):
    """
    Executes the external Python script after a successful download.
    
    The final command executed is: python3 /script/<script> <probe_id> <filename>
    """
    if not script_command:
        logging.debug("No script command provided. Skipping post-download script execution.")
        return

    # Unconditionally set the interpreter to python3
    interpreter = "python3" 
    logging.debug(f"Script execution set to use interpreter: {interpreter}")

    # 1. Construct the full executable path
    full_script_path = os.path.join(SCRIPT_ROOT_PATH, script_command)
    
    # 2. Construct the full command string
    quoted_probe_id = shlex.quote(str(probe_id))
    quoted_script_path = shlex.quote(full_script_path)
    quoted_file_path = shlex.quote(local_file_path)
    
    # Example: python3 '/app/script/processor.py' '101' '/data/file.txt'
    full_command = f"{interpreter} {quoted_script_path} {quoted_file_path} {quoted_probe_id}"
    
    # 3. Use shlex for safe splitting
    try:
        command_args = shlex.split(full_command)
    except ValueError as e:
        logging.error(f"Failed to parse script command '{full_command}'. Error: {e}")
        return

    logging.info(f"Executing post-download script: {' '.join(command_args)}")

    try:
        # Run the script using subprocess.run, capturing output and checking for success
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            check=True # Raise an exception for non-zero return codes
        )
        
        logging.info(f"Script executed successfully (Return Code: {result.returncode}).")
        if result.stdout:
            logging.debug(f"Script STDOUT: \n{result.stdout.strip()}")
        if result.stderr:
            logging.warning(f"Script STDERR: \n{result.stderr.strip()}")
            
    except subprocess.CalledProcessError as e:
        logging.error(f"Post-download script failed (Return Code: {e.returncode}).")
        logging.error(f"Script execution STDOUT: \n{e.stdout.strip()}")
        logging.error(f"Script execution STDERR: \n{e.stderr.strip()}")
    except FileNotFoundError:
        # Note: command_args[1] holds the script path (after the python interpreter)
        logging.error(f"Post-download script executable not found: {full_script_path}. Ensure it exists in the container.")
    except Exception as e:
        logging.error(f"Error executing post-download script: {e}")


def get_file_paths_from_db() -> list[tuple[str, str, str]]:
    """
    Connects to MySQL and fetches the probe ID, file path/pattern, and associated script 
    from the 'probes' table. Returns a list of (probe_id, files_path_pattern, script_command) tuples.
    """
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        logging.error("Missing required DB environment variables.")
        return []

    logging.info(f"Connecting to database '{DB_NAME}' on {DB_HOST} to fetch ALL file path and script patterns...")
    db_connection = None
    cursor = None
    path_script_pairs = []

    try:
        db_connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connection_timeout=15
        )
        cursor = db_connection.cursor()
        
        # UPDATED QUERY: Select 'id', 'files', and 'script'
        query = "SELECT id, files, script FROM probes WHERE files IS NOT NULL AND files != ''"
        logging.debug(f"Executing query: {query}")
        cursor.execute(query)
        
        results = cursor.fetchall()
        
        if results:
            for row in results:
                probe_id = str(row[0]) 
                files_path = row[1].strip() if row[1] else ""
                script_cmd = row[2].strip() if row[2] else ""
                if files_path:
                    path_script_pairs.append((probe_id, files_path, script_cmd)) 
            
            logging.info(f"Successfully retrieved {len(path_script_pairs)} file path and script pairs.")
        else:
            logging.warning("No file path patterns found in the 'probes' table.")

    except mysql.connector.Error as err:
        logging.error(f"MySQL Database Error: {err}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during database operation: {e}")
    finally:
        if cursor:
            cursor.close()
        if db_connection and db_connection.is_connected():
            db_connection.close()
            logging.debug("Database connection closed.")
            
    return path_script_pairs

def download_files_from_ftp():
    """
    Fetches all remote paths and scripts from the database, connects to the FTP server once, 
    iterates through paths, finds matching files, downloads them, and executes the 
    post-download script for new files.
    """
    logging.debug("Starting download_files_from_ftp function.")
    
    # 1. Fetch file paths and scripts from DB
    remote_path_script_pairs = get_file_paths_from_db()
    
    if not remote_path_script_pairs:
        logging.warning("No valid file path patterns retrieved from the database. Aborting FTP process.")
        return []

    if not all([FTP_HOST, FTP_USER, FTP_PASS]):
        logging.error("Missing one or more required FTP environment variables. Aborting.")
        return []

    # Ensure the local download directory exists (LOCAL_MOUNT_PATH) AND the archive directory (ARCHIVE_PATH) exists.
    # Since ARCHIVE_PATH includes LOCAL_MOUNT_PATH, creating the archive directory 
    # handles both directories in one call.
    os.makedirs(ARCHIVE_PATH, exist_ok=True)
    
    logging.info(f"Attempting to connect to FTP host: {FTP_HOST}")
    ftp = None
    files_downloaded = []
    
    try:
        # 2. Connect and Log In ONCE
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        logging.debug(f"Connected to {FTP_HOST}. Attempting login for user: {FTP_USER}")
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True) 
        logging.info("Successfully connected and logged in.")
        
        # --- 3. Loop through ALL Retrieved Paths and Scripts ---
        for probe_id, remote_path_with_pattern, script_command in remote_path_script_pairs:
            logging.info("-" * 40)
            logging.info(f"Processing Probe ID {probe_id} with pattern: {remote_path_with_pattern}")

            # 3a. Parsing Logic: Split the combined path (e.g., /otr/INC_*.TXT)
            REMOTE_DIR, FILE_PATTERN = os.path.split(remote_path_with_pattern)
            
            if not FILE_PATTERN:
                 logging.warning(f"Skipping: Pattern '{remote_path_with_pattern}' does not contain a file pattern.")
                 continue

            if not REMOTE_DIR:
                REMOTE_DIR = '/'

            logging.debug(f"Parsed FTP target. Directory: '{REMOTE_DIR}', Pattern: '{FILE_PATTERN}'")

            # 3b. Change Directory
            logging.debug(f"Changing directory to: {REMOTE_DIR}")
            try:
                ftp.cwd('/') 
                ftp.cwd(REMOTE_DIR)
                logging.debug(f"Current remote directory is: {ftp.pwd()}")
            except ftplib.error_perm as e:
                 logging.error(f"Skipping path '{remote_path_with_pattern}': Failed to change directory. Error: {e}")
                 continue 

            # 3c. List and Filter Files
            logging.info(f"Listing files in '{ftp.pwd()}' with pattern '{FILE_PATTERN}'...")
            remote_file_names = ftp.nlst() 
            matched_files = [name for name in remote_file_names if fnmatch.fnmatch(name, FILE_PATTERN)]
            logging.info(f"Found {len(matched_files)} files matching the pattern.")

            # 3d. Download Matched Files
            if not matched_files:
                logging.info("No files matched the specified pattern.")
            
            for remote_file_name in matched_files:
                local_file_path = os.path.join(LOCAL_MOUNT_PATH, remote_file_name)
                archive_file_path = os.path.join(ARCHIVE_PATH, remote_file_name)
                
                # --- NEW CHECK: Check both local (temp) and archive directories ---
                if os.path.exists(local_file_path):
                    logging.info(f"File '{remote_file_name}' found in primary download path ({LOCAL_MOUNT_PATH}). Skipping download.")
                    continue
                if os.path.exists(archive_file_path):
                    logging.info(f"File '{remote_file_name}' found in archive path ({ARCHIVE_PATH}). Skipping download.")
                    continue
                # --- END NEW CHECK ---
                
                # Perform Download
                try:
                    with open(local_file_path, 'wb') as local_file:
                        logging.info(f"Starting download: '{remote_file_name}' to '{local_file_path}'...")
                        
                        ftp.retrbinary(f'RETR {remote_file_name}', local_file.write)
                        
                    file_size_bytes = os.path.getsize(local_file_path)
                    logging.info(f"Download complete for '{remote_file_name}' (Size: {file_size_bytes} bytes).")
                    files_downloaded.append(remote_file_name)
                    
                    # Execute script only for newly downloaded files that have content
                    # The external script is responsible for moving the file to the archive.
                    if file_size_bytes > 0: 
                        execute_post_download_script(script_command, probe_id, local_file_path)
                        
                except ftplib.all_errors as e:
                    logging.error(f"FTP transfer error for file '{remote_file_name}': {e}. Skipping this file.")
                except Exception as e:
                    logging.error(f"Local file system error or script execution error for file '{remote_file_name}': {e}. Skipping this file.")
        
        # --- End Loop ---

    except ftplib.all_errors as e:
        logging.error(f"FTP Communication Error (ftplib): {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during execution: {e}")
    finally:
        if ftp:
            try:
                ftp.quit()
                logging.info("FTP connection closed gracefully.")
            except Exception as e:
                logging.warning(f"Error during FTP quit/closing: {e}")
    
    return files_downloaded

if __name__ == "__main__":
    logging.debug("Main execution block started.")
    start_time = datetime.now()
    
    downloaded_list = download_files_from_ftp()
    
    if downloaded_list:
        logging.info(f"Script finished successfully. Total files downloaded: {len(downloaded_list)}")
        logging.debug(f"Downloaded file list: {downloaded_list}")
    else:
        logging.warning("Script finished. Zero files were downloaded.")
    
    end_time = datetime.now()
    duration = end_time - start_time
    logging.info(f"Total execution time: {duration.total_seconds():.2f} seconds.")
    logging.debug("Main execution block finished.")