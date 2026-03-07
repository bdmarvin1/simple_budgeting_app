import sys
from werkzeug.security import generate_password_hash

def main():
    if len(sys.argv) < 2:
        print("Usage: python hash_password.py <password>")
        sys.exit(1)

    password = sys.argv[1]
    hashed = generate_password_hash(password)
    print("\n--- COPY THE HASH BELOW ---")
    print(hashed)
    print("--- END OF HASH ---\n")
    print("Add the string between the dashes to your .env file as ADMIN_PASSWORD_HASH")
    print("Example: ADMIN_PASSWORD_HASH=scrypt:32768:8:1$...")

if __name__ == "__main__":
    main()
