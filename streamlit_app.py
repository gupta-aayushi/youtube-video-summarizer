import mysql.connector

def connect_db():
    try:
        conn = mysql.connector.connect(
            host="dtkfg.h.filess.io",
            port=3307,
            user="YTVidSummarizer_planetbowl",
            password="b05d878989a003f24fd40b82e9020410dfc20d2a",
            database="YTVidSummarizer_planetbowl",
            # Recommended parameters:
            connect_timeout=5,
            autocommit=True,
            pool_size=3  # For connection pooling
        )
        return conn
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None
