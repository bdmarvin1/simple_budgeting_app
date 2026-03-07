import sys
from werkzeug.security import generate_password_hash

def main():
    if len(sys.argv) < 2:
        print("Usage: python hash_password.py <password>")
        sys.exit(1)

    password = sys.argv[1]
    hashed = generate_password_hash(password)
    print(f"Hashed password: {hashed}")
    print("\nAdd this to your .env file as ADMIN_PASSWORD_HASH")

if __name__ == "__main__":
    main()
