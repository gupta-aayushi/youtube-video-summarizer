import mysql.connector

def test_connection():
    try:
        conn = mysql.connector.connect(
            host="sql305.infinityfree.com",
            user="if0_38757634",
            password="miDebQzfNS46c",
            database="if0_38757634_youtube_summaries",
            port=3306,
            ssl_disabled=True
        )
        print("✅ Connection successful!")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return False

test_connection()
