import streamlit as st
import os
import re
import hashlib
import mysql.connector
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from dotenv import load_dotenv
from fpdf import FPDF
import base64
from datetime import datetime
import time

# Load environment variables
load_dotenv()

# Configure Gemini API Key (Replace with your own)
API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBpMOF0OCTAyZiXofYORpJZ931j7-UuRYw")
if API_KEY == "your_api_key_here":
    st.warning("Gemini API Key is missing. Please update it in your .env file.")
genai.configure(api_key=API_KEY)

# Connect to MySQL Database
def connect_db():
    try:
        return mysql.connector.connect(
            host="localhost",  
            user="root",       
            password="root",
            database="youtube_summarizer"
        )
    except mysql.connector.Error as e:
        st.error(f"Database connection error: {str(e)}")
        return None

# Hash Passwords for Security
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User Registration
def register_user(username, password):
    conn = connect_db()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", 
                       (username, hash_password(password)))
        conn.commit()
        st.success("Registration successful! You can now log in.")
    except mysql.connector.IntegrityError:
        st.error("Username already exists. Please choose a different one.")
    finally:
        cursor.close()
        conn.close()

# User Login
def login_user(username, password):
    conn = connect_db()
    if conn is None:
        return None

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM users WHERE username=%s AND password=%s", 
                       (username, hash_password(password)))
        user = cursor.fetchone()
        return user["id"] if user else None
    finally:
        cursor.close()
        conn.close()

# Save Generated Content
def save_content(user_id, video_id, video_title, summary_type, content):
    conn = connect_db()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO summaries (user_id, video_id, video_title, summary_type, content)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, video_id, video_title, summary_type, content))
        conn.commit()
        st.toast("Content saved to your account.", icon="✅")
    finally:
        cursor.close()
        conn.close()

# Retrieve Saved Content
def get_saved_content(user_id):
    conn = connect_db()
    if conn is None:
        return []

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, video_title, summary_type, content, created_at 
            FROM summaries WHERE user_id=%s ORDER BY created_at DESC
        """, (user_id,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

# Delete Saved Content
def delete_saved_content(content_id, user_id):
    conn = connect_db()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM summaries WHERE id=%s AND user_id=%s", (content_id, user_id))
        conn.commit()
        st.toast("Content deleted successfully.", icon="🗑️")
    finally:
        cursor.close()
        conn.close()

# Extract Video ID from YouTube URL
def extract_video_id(youtube_url):
    pattern = r"(?:v=|\/|embed\/|youtu\.be\/|v\/|shorts\/|watch\?v=|watch\?.*?&v=)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, youtube_url)
    return match.group(1) if match else None

# Extract YouTube Video Transcript
def extract_transcript_details(youtube_video_url):
    try:
        video_id = extract_video_id(youtube_video_url)
        if not video_id:
            return "Invalid YouTube URL"

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try fetching English transcript first
        try:
            transcript = transcript_list.find_transcript(['en'])
        except NoTranscriptFound:
            available_languages = [t.language_code for t in transcript_list]
            
            # If English isn't available, find a translatable language
            if 'hi' in available_languages:  # Hindi (or add other preferred languages)
                transcript = transcript_list.find_transcript(['hi']).translate('en')
            elif available_languages:
                transcript = transcript_list.find_transcript([available_languages[0]]).translate('en')
            else:
                return "Error: No English or translatable transcripts found."

        # Convert transcript to text
        transcript_text = " ".join([i["text"] for i in transcript.fetch()])
        return transcript_text

    except TranscriptsDisabled:
        return "Error: This video does not have transcripts available."
    except Exception as e:
        return f"Error: {str(e)}"

# Define prompts for different output types
PROMPTS = {
    "Summary": "Summarize the content in 250 words in a clear, structured format with key points:\n\n",
    "Follow-Up Exercises": "Generate 10 practical follow-up exercises based on the transcript. Format each with a title, description, and expected outcome:\n\n",
    "MCQ Test": "Generate 10 multiple-choice questions with four options each. Format clearly with question numbers and mark the correct answer with (Correct). Group answers at the end:\n\n"
}

# Generate AI-based content using Gemini API with progress indication
def generate_gemini_content(transcript_text, prompt):
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        with st.spinner('Generating content... This may take a moment'):
            response = model.generate_content(prompt + transcript_text, generation_config={"temperature": 0.7})
            return response.text.strip()
    except Exception as e:
        return f"Error generating content: {str(e)}"

# Custom CSS for better UI
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
        background-color: white;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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

# Login/Register Page
def login():
    st.markdown("""
    <h1 style='text-align: center;'>YouTube Video Summarizer</h1>            
    <div style='text-align: center; margin-bottom: 30px;'>
        <h4>Enhance your learning experience from YouTube videos effortlessly</h4>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        with st.container(border=True):
            st.subheader("Login")
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("Login", key="login_button"):
                if username and password:
                    user_id = login_user(username, password)
                    if user_id:
                        st.session_state["logged_in"] = True
                        st.session_state["user_id"] = user_id
                        st.session_state["username"] = username
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Try again.")
                else:
                    st.warning("Please enter both username and password")
    
    with col2:
        with st.container(border=True):
            st.subheader("Register")
            new_username = st.text_input("Choose a username", key="reg_username")
            new_password = st.text_input("Choose a password", type="password", key="reg_password")
            confirm_password = st.text_input("Confirm password", type="password", key="confirm_password")
            
            if st.button("Register", key="register_button"):
                if new_username and new_password and confirm_password:
                    if new_password == confirm_password:
                        register_user(new_username, new_password)
                    else:
                        st.error("Passwords don't match!")
                else:
                    st.warning("Please fill all fields")

# Main App Functionality
def main_app():
    set_custom_css()
    
    # Add logout button to top right
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
    
    # Sidebar with user info and navigation
    with st.sidebar:
        st.markdown(f"""
        <div style='text-align: center; margin-bottom: 30px;'>
            <h3>Welcome back, {st.session_state['username']}!</h3>
        </div>
        """, unsafe_allow_html=True)
        
        menu = st.radio(
            "Navigation",
            ["Generate Content from Video", "Saved Content"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; font-size: small; color: #bdc3c7;'>
            YouTube Video Summarizer v1.1<br>
            Powered by Gemini AI
        </div>
        """, unsafe_allow_html=True)
    
    # Main content area
    if menu == "Generate Content from Video":
        st.header("YouTube Video Summarizer")
        st.markdown("Extract key information from any YouTube video with transcripts")
        
        with st.form("video_form"):
            youtube_link = st.text_input(
                "Enter YouTube Video URL:",
                placeholder="https://www.youtube.com/watch?v=...",
                help="Paste the URL of any YouTube video with available transcripts"
            )
            
            col1, col2 = st.columns([3, 1])
            with col1:
                option = st.selectbox(
                    "Choose output type:",
                    ["Summary", "Follow-Up Exercises", "MCQ Test"],
                    help="Select the type of content you want to generate"
                )
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                save_option = st.checkbox("Save to account", value=True)
            
            submitted = st.form_submit_button(f"Generate {option}", type="primary")
            
            if submitted:
                if not youtube_link:
                    st.warning("Please enter a YouTube URL")
                else:
                    with st.spinner("Processing video..."):
                        transcript_text = extract_transcript_details(youtube_link)
                    
                    if "Error" in transcript_text:
                        st.error(transcript_text)
                    else:
                        with st.expander("View Transcript", expanded=False):
                            st.write(transcript_text)
                        
                        generated_content = generate_gemini_content(transcript_text, PROMPTS[option])
                        
                        st.subheader(f"Generated {option}")
                        st.markdown(f"""
                        <div class="main-content">
                            {generated_content}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if save_option:
                            video_id = extract_video_id(youtube_link)
                            save_content(
                                user_id=st.session_state["user_id"], 
                                video_id=video_id, 
                                video_title=f"Video {video_id[:6]}...",  
                                summary_type=option, 
                                content=generated_content
                            )
    
    elif menu == "Saved Content":
        st.header("Your Saved Content")
        st.markdown("Access your previously generated summaries and exercises")
        
        saved_data = get_saved_content(st.session_state["user_id"])
        
        if not saved_data:
            st.info("You haven't saved any content yet.")
        else:
            for idx, entry in enumerate(saved_data):
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.subheader(entry["video_title"])
                        st.caption(f"Type: {entry['summary_type']} • Created: {entry['created_at'].strftime('%b %d, %Y %H:%M')}")
                    with col2:
                        if st.button("Delete", key=f"del_{entry['id']}"):
                            delete_saved_content(entry["id"], st.session_state["user_id"])
                            time.sleep(0.5)
                            st.rerun()
                    
                    with st.expander("View Content", expanded=False):
                        st.write(entry["content"])

# App Initialization
if __name__ == "__main__":
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login()
    else:
        main_app()
