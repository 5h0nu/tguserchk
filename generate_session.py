import os
import sys

# Reconfigure stdout/stderr to support Unicode characters in Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
except ImportError:
    print("❌ Telethon is not installed! Installing it now...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon"])
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession

def main():
    print("====================================================")
    print("🔑 Telegram String Session Generator 🔑")
    print("====================================================")
    
    api_id = input("Enter your API ID: ").strip()
    api_hash = input("Enter your API Hash: ").strip()
    phone = input("Enter your Phone Number (e.g. +1234567890): ").strip()
    
    if not api_id or not api_hash or not phone:
        print("❌ Error: All fields are required!")
        sys.exit(1)
        
    try:
        api_id_int = int(api_id)
    except ValueError:
        print("❌ Error: API ID must be an integer!")
        sys.exit(1)
        
    print("\nConnecting to Telegram and requesting verification code...")
    try:
        client = TelegramClient(StringSession(), api_id_int, api_hash)
        client.start(phone=phone)
        
        session_str = client.session.save()
        print("\n====================================================")
        print("✅ LOGIN SUCCESSFUL!")
        print("====================================================")
        print("Here is your TELEGRAM_STRING_SESSION:\n")
        print(session_str)
        print("\n====================================================")
        print("Copy the entire string above and set it in your .env file or Railway variables.")
        print("Keep this string secret! Anyone who has it can access your Telegram account.")
        
        client.disconnect()
    except Exception as e:
        print(f"\n❌ Login failed: {e}")

if __name__ == "__main__":
    main()
