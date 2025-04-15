import mysql.connector

print("=== Testing InfinityFree MySQL Connection ===")

config = {
    "host": "sql305.infinityfree.com",
    "user": "if0_38757634",
    "password": "miDebQzfNS46c",
    "database": "if0_38757634_youtube_summaries",
    "port": 3306,
    "ssl_disabled": True,
    "connect_timeout": 5
}

try:
    print("🔄 Attempting to connect...")
    conn = mysql.connector.connect(**config)
    
    if conn.is_connected():
        print("✅ Success! Connected to database.")
        print(f"Server Info: {conn.get_server_info()}")
        
        # Test a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print(f"Query Test: {result[0]}")
        
        cursor.close()
        conn.close()
    else:
        print("❌ Connection failed silently")

except Exception as e:
    print(f"❌ Critical Error: {str(e)}")
    print("\nPossible Solutions:")
    print("- Check if InfinityFree is down (try again later)")
    print("- Verify credentials in InfinityFree control panel")
    print("- Try a VPN (your network may block MySQL)")

input("\nPress Enter to exit...")
