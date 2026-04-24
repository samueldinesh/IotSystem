import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'alarms.db')

def get_connection():
    # Enable WAL mode for better concurrent read/write
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('pragma journal_mode=wal')
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()
    
    # Rules Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL, -- SIMPLE or CONDITIONAL
            primary_sensor TEXT NOT NULL,
            operator TEXT NOT NULL,
            threshold REAL NOT NULL,
            duration INTEGER NOT NULL, -- in seconds
            shunt_sensor TEXT,
            shunt_operator TEXT,
            shunt_threshold REAL
        )
    ''')
    
    # Sensor State Table (Stores latest value of all sensors)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_state (
            sensor_id TEXT PRIMARY KEY,
            value REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Alarm Tracking Table (Stateful application)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alarm_tracking (
            rule_id INTEGER,
            sensor_id TEXT,
            breach_start_time TIMESTAMP NOT NULL,
            status TEXT NOT NULL, -- EVALUATING, TRIGGERED
            PRIMARY KEY (rule_id, sensor_id),
            FOREIGN KEY(rule_id) REFERENCES rules(id)
        )
    ''')
    
    # Alarm History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alarm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            sensor_id TEXT,
            triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(rule_id) REFERENCES rules(id)
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
