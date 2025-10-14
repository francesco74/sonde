Datalogger Import Script Instructions

This document provides instructions on how to use the import_datalogger.py script to load sensor data from a text file into the MySQL database.
1. Prerequisites

    You must have Python 3 installed on your system.

    You need the mysql-connector-python library. If you haven't installed it yet, run:

    pip install mysql-connector-python

2. Database Configuration

The script connects to the database using credentials. For security, it's best to configure these using environment variables.

Open your terminal and set the following variables before running the script:

# For Linux / macOS
export DB_HOST=localhost
export DB_USER=sensor_user
export DB_PASSWORD=sensor_password
export DB_NAME=sensordb

# For Windows (Command Prompt)
set DB_HOST=localhost
set DB_USER=sensor_user
set DB_PASSWORD=sensor_password
set DB_NAME=sensordb

Important:

    Replace the values (localhost, sensor_user, etc.) with your actual database credentials.

    The practice you associate the data with must already exist in the practices table in your database.

3. How to Run the Script

The script is designed to be run from your command line. It requires two arguments:

    The full path to the datalogger .TXT file.

    The exact name of the practice (as it appears in your database) that this data belongs to.

Example Usage

Let's say your text file is located at /home/user/data/stazione1_17_07_2018_10_25_55.TXT and you want to associate this data with the practice named Sonda-LU-01.

You would run the following command in your terminal:

python import_datalogger.py "/home/user/data/stazione1_17_07_201fl_chart8_10_25_55.TXT" "Sonda-LU-01"

Note: It's a good practice to wrap the file path in quotes, especially if it contains spaces.
4. Script Logic Explained

    Parsing: The script opens the text file and specifically looks for the [INIZIO DATI] and [FINE DATI] markers to isolate the data section. It reads the first line as the header (to get the sensor names like FESS1, TEMP, etc.) and then processes each subsequent line as a set of readings.

    Database Connection: It connects to the database using the credentials you provided in the environment variables.

    Practice Lookup: It first finds the ID of the practice you specified. If the practice doesn't exist, the script will stop to prevent data from being miscategorized.

    Sensor Handling: For each sensor name found in the file's header (e.g., FESS1, TEMP), the script checks if a sensor with that name already exists for the given practice.

        If it exists, it retrieves its ID.

        If it's a new sensor for this practice, it automatically creates a new entry in the sensors table and gets the new ID.

    Data Insertion: Finally, it inserts each reading into the sensor_readings table, linking it to the correct sensor_id and converting the date and value into the correct format for the database.

    Error Handling: The script includes error handling. If there's a problem with the database connection or during the data insertion, it will print an error message and safely roll back any partial changes to ensure data integrity.