import streamlit as st
import os
import re
import hashlib
import mysql.connector
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from dotenv import load_dotenv
from datetime import datetime
import time

# Load environment variables
load_dotenv()

# Configure Gemini API Key
API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBpMOF0OCTAyZiXofYORpJZ931j7-UuRYw")
if API_KEY == "your_api_key_here":
    st.warning("Gemini API Key is missing. Please update it in your .env file.")
genai.configure(api_key=API_KEY)

# =============================================
# Database Configuration for Filess.io
# =============================================
DB_CONFIG = {
    "host": "dtkfg.h.filess.io",
    "port": 3307,
    "user": "YTVidSummarizer_planetbowl",
    "password": "b05d878989a003f24fd40b82e9020410dfc20d2a",
    "database": "YTVidSummarizer_planetbowl",
    "pool_name": "youtube_pool",
    "pool_size": 3,
    "connect_timeout": 10,
    "autocommit": True
}

def init_db_pool():
    """Initialize and return a connection pool"""
    try:
        return mysql.connector.pooling.MySQLConnectionPool(**DB_CONFIG)
    except mysql.connector.Error as err:
        st.error(f"Database connection failed: {err}")
        return None

def get_db_connection():
    """Get a connection from the pool with error handling"""
    try:
        if 'db_pool' not in st.session_state:
            st.session_state.db_pool = init_db_pool()
        
        if st.session_state.db_pool:
            return st.session_state.db_pool.get_connection()
        return None
    except Exception as e:
        st.error(f"Failed to get database connection: {str(e)}")
        return None

# =============================================
# Security Functions
# =============================================
def hash_password(password):
    """Securely hash passwords using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

# =============================================
# User Management Functions
# =============================================
def register_user(username, password):
    """Register a new user with error handling"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hash_password(password)))
        conn.commit()
        st.success("Registration successful! Please login.")
        return True
    except mysql.connector.IntegrityError:
        st.error("Username already exists. Please choose another.")
        return False
    except mysql.connector.Error as e:
        st.error(f"Registration failed: {str(e)}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def login_user(username, password):
    """Authenticate user with secure password checking"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return None

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM users WHERE username = %s AND password = %s",
            (username, hash_password(password))
        )
        return cursor.fetchone()
    except mysql.connector.Error as e:
        st.error(f"Login failed: {str(e)}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# =============================================
# Content Management Functions
# =============================================
def save_content(user_id, video_id, video_title, summary_type, content):
    """Save generated content to database"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO summaries 
            (user_id, video_id, video_title, summary_type, content) 
            VALUES (%s, %s, %s, %s, %s)""",
            (user_id, video_id, video_title, summary_type, content))
        conn.commit()
        st.toast("✓ Content saved successfully!", icon="✅")
        return True
    except mysql.connector.Error as e:
        st.error(f"Failed to save content: {str(e)}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_saved_content(user_id):
    """Retrieve user's saved content"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return []

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT id, video_id, video_title, summary_type, content, created_at 
            FROM summaries WHERE user_id = %s ORDER BY created_at DESC""",
            (user_id,))
        return cursor.fetchall()
    except mysql.connector.Error as e:
        st.error(f"Failed to load content: {str(e)}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def delete_saved_content(content_id, user_id):
    """Delete specific content with ownership check"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM summaries WHERE id = %s AND user_id = %s",
            (content_id, user_id))
        conn.commit()
        st.toast("🗑️ Content deleted successfully!", icon="✅")
        return cursor.rowcount > 0
    except mysql.connector.Error as e:
        st.error(f"Deletion failed: {str(e)}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# =============================================
# YouTube Processing Functions
# =============================================
def extract_video_id(url):
    """Extract YouTube video ID from various URL formats"""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu.be\/([0-9A-Za-z_-]{11})",
        r"youtube.com\/shorts\/([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_transcript_details(youtube_url):
    """Fetch and process YouTube transcript with fallbacks"""
    try:
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return "Invalid YouTube URL"

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try English first, then Hindi, then first available with translation
        for lang in ['en', 'hi']:
            try:
                transcript = transcript_list.find_transcript([lang])
                # Properly access transcript text using the correct method
                transcript_text = " ".join([t.text for t in transcript.fetch()])
                return transcript_text
            except NoTranscriptFound:
                continue
        
        # If no direct match, find translatable transcript
        for transcript in transcript_list:
            if transcript.is_translatable:
                translated = transcript.translate('en').fetch()
                transcript_text = " ".join([t.text for t in translated])
                return transcript_text
        
        return "No English or translatable transcripts found"
    
    except TranscriptsDisabled:
        return "Transcripts disabled for this video"
    except Exception as e:
        return f"Error: {str(e)}"

# =============================================
# AI Generation Functions
# =============================================
PROMPTS = {
    "Summary": """Generate a concise 250-word summary with these sections:
    1. Key Concepts
    2. Main Arguments
    3. Important Examples
    4. Conclusion\n\nTranscript:\n""",
    "Follow-Up Exercises": """Create 10 practical exercises with:
    - Title
    - Objective
    - Steps
    - Expected Outcome\n\nBased on:\n""",
    "MCQ Test": """Generate 10 MCQs with:
    - Clear question stem
    - 4 options (A-D)
    - Mark correct answer with (Correct)\n\nFrom:\n"""
}

def generate_gemini_content(transcript, prompt_type):
    """Generate content using Gemini with error handling"""
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        with st.spinner(f'Generating {prompt_type}...'):
            response = model.generate_content(
                PROMPTS[prompt_type] + transcript,
                generation_config={"temperature": 0.7})
            return response.text
    except Exception as e:
        return f"⚠️ Generation failed: {str(e)}"

# =============================================
# UI Components
# =============================================
def set_custom_css():
    st.markdown("""
    <style>
    /* Main app styling */
    .stApp {
        background-image: linear-gradient(rgba(255,255,255,0.1), rgba(255,255,255,0.1)), 
                          url("https://images.unsplash.com/photo-1651575560910-b497ea4ec36f?q=80&w=2127&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D");
        background-size: cover;
        background-attachment: fixed;
        background-position: center;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #232323 !important;
    }
    
    /* Sidebar text color */
    [data-testid="stSidebar"] * {
        color: #ecf0f1 !important;
    }
    
    /* Button styling */
    .stButton>button {
        background-color: #3498db !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        border: none !important;
        transition: all 0.3s ease;
        width: 100%;
    }
    
    .stButton>button:hover {
        background-color: #2980b9 !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    /* Input field styling */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 8px !important;
        padding: 10px !important;
        border: 1px solid #dfe6e9 !important;
    }
    
    /* Card styling for saved content */
    .card {
        background-color: white !important;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
        color: #333333 !important;
    }

    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #3498db;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #2980b9;
    }
    
    /* Logout button container */
    .logout-container {
        position: fixed;
        top: 15px;
        right: 20px;
        z-index: 9999;
    }
    
    /* Logout button styling */
    .logout-button {
        background-color: #e74c3c !important;
        color: white !important;
        border: none !important;
        padding: 10px 20px !important;
        font-size: 16px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        transition: 0.3s !important;
        margin-top: 25px;
    }
    
    .logout-button:hover {
        background-color: #c0392b !important;
    }
    
    /* Main content container */
    .main-content {
        
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================
# Main App Pages
# =============================================
def login_page():
    """Authentication page with login/register forms"""
    st.title("🎬 YouTube Video Summarizer")
    st.markdown("""
    <div style='text-align: center; margin-bottom: 30px;'>
        <h4>Transform YouTube videos into study materials with AI</h4>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login", type="primary"):
                if username and password:
                    user = login_user(username, password)
                    if user:
                        st.session_state.update({
                            "logged_in": True,
                            "user_id": user["id"],
                            "username": username
                        })
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
                else:
                    st.warning("Please enter both fields")
    
    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("Choose username")
            new_pass = st.text_input("Choose password", type="password")
            confirm_pass = st.text_input("Confirm password", type="password")
            
            if st.form_submit_button("Create Account"):
                if new_user and new_pass and confirm_pass:
                    if new_pass == confirm_pass:
                        if register_user(new_user, new_pass):
                            st.session_state.login_tab = True
                            st.rerun()
                    else:
                        st.error("Passwords don't match")
                else:
                    st.warning("Please complete all fields")

def main_app_page():
    """Main application interface"""
    set_custom_css()
    
    # Logout button
    st.markdown("""
    <div class="logout-container">
        <form>
            <button class="logout-button" formaction="?logout=true" type="submit">Logout</button>
        </form>
    </div>
    """, unsafe_allow_html=True)
    
    # Handle logout
    if st.query_params.get("logout"):
        st.session_state.clear()
        st.experimental_set_query_params()  # Clear all query parameters
        st.rerun()
    
    # Sidebar navigation
    with st.sidebar:
        st.markdown(f"### Welcome, {st.session_state.username}!")
        page = st.radio("Menu", ["Generator", "My Library"])
        st.markdown("---")
        st.caption("v1.2 | Powered by Gemini AI")
    
    # Page routing
    if page == "Generator":
        render_generator()
    else:
        render_library()

def render_generator():
    """Video processing and content generation UI"""
    st.header("🎥 Video Content Generator")
    
    with st.form("video_form"):
        url = st.text_input("YouTube URL", placeholder="Paste any YouTube video link")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            content_type = st.selectbox(
                "Output Type",
                ["Summary", "Follow-Up Exercises", "MCQ Test"])
        with col2:
            save_to_lib = st.checkbox("Save to Library", True)
        
        if st.form_submit_button(f"Generate {content_type}"):
            if not url:
                st.warning("Please enter a URL")
            else:
                with st.spinner("Processing video..."):
                    transcript_text = extract_transcript_details(url)
                
                if "Error" in transcript_text:
                    st.error(transcript_text)
                else:
                    with st.expander("View Transcript", expanded=False):
                        st.write(transcript_text)
                    
                    generated_content = generate_gemini_content(transcript_text, content_type)
                    
                    st.subheader(f"Generated {content_type}")
                    st.markdown(f"""
                    <div class='card'>
                        {generated_content}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if save_to_lib:
                        video_id = extract_video_id(url)
                        save_content(
                            user_id=st.session_state["user_id"], 
                            video_id=video_id, 
                            video_title=f"Video {video_id[:6]}...",  
                            summary_type=content_type, 
                            content=generated_content)

def render_library():
    """Saved content browsing interface"""
    st.header("📚 My Content Library")
    
    content = get_saved_content(st.session_state.user_id)
    if not content:
        st.info("Your library is empty. Generate some content first!")
        return
    
    for item in content:
        with st.container():
            st.markdown(f"""
            <div class='card'>
                <h3>{item['video_title']}</h3>
                <p><small>{item['summary_type']} • {item['created_at'].strftime('%b %d, %Y')}</small></p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("View Content", expanded=False):
                st.markdown(item['content'])
            
            if st.button("Delete", key=f"del_{item['id']}"):
                if delete_saved_content(item['id'], st.session_state.user_id):
                    time.sleep(0.5)
                    st.rerun()

# =============================================
# Main App Flow
# =============================================
if __name__ == "__main__":
    if "logged_in" not in st.session_state:
        login_page()
    else:
        main_app_page()
