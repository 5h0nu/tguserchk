import os
import sys
import time
import requests
from bs4 import BeautifulSoup
from groq import Groq

# Reconfigure stdout/stderr to support Unicode characters in Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Load .env file manually if it exists (for local testing/non-Docker runs)
if os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()
    except Exception as e:
        print(f"⚠️ Warning: Could not load .env file: {e}")

# --- CONFIGURATION (Reads from Environment) ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CHECK_DELAY = int(os.environ.get("CHECK_DELAY", "4"))
LLM_REFILL_THRESHOLD = 5

# Files for persistence
CHECKED_FILE = "checked_usernames.txt"
WORDS_FILE = "words.txt"
WORDLIST_URL = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears-medium.txt"

# Initialize Groq client if key is available
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"⚠️ Failed to initialize Groq client: {e}")

def load_checked_usernames():
    """Loads previously checked usernames from a local file to prevent duplicates."""
    checked = set()
    if os.path.exists(CHECKED_FILE):
        try:
            with open(CHECKED_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip().lower()
                    if name:
                        checked.add(name)
            print(f"📖 Loaded {len(checked)} previously checked usernames from {CHECKED_FILE}.")
        except Exception as e:
            print(f"⚠️ Error reading checked usernames file: {e}")
    return checked

def save_checked_username(username):
    """Appends a checked username to the persistent storage immediately."""
    try:
        with open(CHECKED_FILE, "a", encoding="utf-8") as f:
            f.write(username + "\n")
    except Exception as e:
        print(f"⚠️ Error writing checked username to file: {e}")

def download_dictionary_if_needed():
    """Downloads a public dictionary of common English words if not present locally."""
    if not os.path.exists(WORDS_FILE):
        print(f"📥 Downloading common word list from {WORDLIST_URL}...")
        try:
            response = requests.get(WORDLIST_URL, timeout=15)
            if response.status_code == 200:
                # Filter words (length 5 to 8, only alphanumeric)
                words = []
                for line in response.text.splitlines():
                    w = line.strip().lower()
                    if 5 <= len(w) <= 8 and w.isalnum():
                        words.append(w)
                
                with open(WORDS_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(words))
                print(f"✅ Downloaded and filtered {len(words)} words into {WORDS_FILE}.")
            else:
                print(f"❌ Failed to download dictionary, status code: {response.status_code}")
        except Exception as e:
            print(f"❌ Error downloading dictionary: {e}")

def load_dictionary_words():
    """Loads filtered dictionary words from the local file."""
    download_dictionary_if_needed()
    words = []
    if os.path.exists(WORDS_FILE):
        try:
            with open(WORDS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w:
                        words.append(w)
        except Exception as e:
            print(f"⚠️ Error reading dictionary file: {e}")
    return words

def fetch_rare_usernames_from_groq():
    """Fetches a batch of cleanly formatted rare candidate usernames from Groq as secondary source."""
    if not client:
        return []
        
    print("\n🤖 Asking Groq to think up a batch of rare dictionary/aesthetic usernames...")
    prompt = (
        "Generate a list of exactly 15 unique, clean, and rare English dictionary or smooth aesthetic words. "
        "They must be between 5 and 7 characters long. "
        "Do not include any special characters or spaces. "
        "Provide ONLY the names separated by commas. No intro, no numbers, no explanations."
    )
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.85
        )
        
        raw_output = chat_completion.choices[0].message.content
        usernames = [name.strip().lower() for name in raw_output.split(",") if name.strip()]
        usernames = [name.replace("\n", "").replace('"', '').replace("'", "") for name in usernames]
        
        valid_usernames = [name for name in usernames if len(name) >= 5 and name.isalnum()]
        print(f"🔮 Groq provided {len(valid_usernames)} candidate names.")
        return valid_usernames
        
    except Exception as e:
        print(f"❌ Error fetching from Groq API: {e}")
        return []

def check_telegram_username(username):
    """
    Robust text-based check for public t.me layout.
    Returns True if AVAILABLE (not taken), False if TAKEN.
    """
    url = f"https://t.me/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # If tgme_page_title is found, the name is taken
            title_div = soup.find(class_="tgme_page_title")
            if title_div and title_div.get_text(strip=True):
                return False  # TAKEN
                
            # If tgme_page_extra is found (contains members/subscribers count or bot status), it's taken
            extra_div = soup.find(class_="tgme_page_extra")
            if extra_div and extra_div.get_text(strip=True):
                return False  # TAKEN
                
            return True  # AVAILABLE
        else:
            return True
            
    except requests.RequestException as e:
        print(f"⚠️ Network check failed for t.me/@{username}: {e}")
        return True 

def check_fragment_status(username):
    """
    Check username status on Fragment.com.
    Returns True if NOT on sale / auction / sold (meaning it is free to register),
    Returns False if it is on auction, for sale, or sold.
    """
    url = f"https://fragment.com/username/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            header_status = soup.find(class_="tm-section-header-status")
            if header_status:
                status_text = header_status.get_text(strip=True).lower()
                # If status is Taken, Sold, On auction, or For sale, it is not available for free
                if status_text in ["taken", "sold", "on auction", "for sale"]:
                    return False
            
            return True
        else:
            return True
    except Exception as e:
        print(f"⚠️ Fragment check failed for @{username}: {e}")
        return True

def send_telegram_alert(username):
    """Sends a notification to Telegram bot channel when a free/available name is found."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = (
        f"✨ AVAILABLE USERNAME FOUND!\n"
        f"👉 @{username}\n\n"
        f"🔗 Telegram: https://t.me/{username}\n"
        f"🔗 Fragment: https://fragment.com/username/{username}"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            print(f"📡 Bot alert pushed to Telegram for @{username}!")
        else:
            print(f"❌ Failed to push bot alert: {res.text}")
    except Exception as e:
        print(f"❌ Alert exception: {e}")

def main():
    print("🚀 Telegram & Fragment.com Username Evaluator Initialized.")
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env file or environment variables!")
        sys.exit(1)
    
    checked_usernames = load_checked_usernames()
    dict_words = load_dictionary_words()
    
    # We will pick words from our dictionary file that haven't been checked yet
    dict_index = 0
    username_pool = []
    
    while True:
        # Refill username pool if it drops below threshold
        if len(username_pool) < LLM_REFILL_THRESHOLD:
            # First, try refilling from dictionary words
            refilled_count = 0
            while dict_index < len(dict_words) and refilled_count < 10:
                word = dict_words[dict_index]
                dict_index += 1
                if word not in checked_usernames and word not in username_pool:
                    username_pool.append(word)
                    refilled_count += 1
            
            # Second, augment with Groq if available
            if client and refilled_count < 5:
                new_batch = fetch_rare_usernames_from_groq()
                for name in new_batch:
                    if name not in checked_usernames and name not in username_pool:
                        username_pool.append(name)
            
            # If still empty, wait and loop
            if not username_pool:
                print("💤 Dictionary fully processed and no new words from Groq. Sleeping 60s...")
                time.sleep(60)
                continue
        
        current_name = username_pool.pop(0)
        
        # Double check to prevent duplicates in the current run
        if current_name in checked_usernames:
            continue
            
        print(f"🔍 Checking: @{current_name} (Total History: {len(checked_usernames)})")
        
        # 1. Check t.me
        if check_telegram_username(current_name):
            # 2. Check Fragment.com
            if check_fragment_status(current_name):
                print(f"✨ MATCH: @{current_name} is AVAILABLE on Telegram & Fragment! Sending alert...")
                send_telegram_alert(current_name)
            else:
                print(f"❌ @{current_name} is not taken on Telegram but is SOLD/ON-SALE on Fragment.")
        else:
            print(f"🔒 @{current_name} is actively taken on Telegram.")
            
        # Record checked name
        checked_usernames.add(current_name)
        save_checked_username(current_name)
        
        time.sleep(CHECK_DELAY)

if __name__ == "__main__":
    main()
