from werkzeug.security import generate_password_hash
import sys

if len(sys.argv) != 2:
    print("Usage: python hash_password.py <password>")
    sys.exit(1)

password = sys.argv[1]
hashed_password = generate_password_hash(password)
print(f"Your hashed password is: {hashed_password}")
print("Set this value for the DASHBOARD_PASSWORD in your .env file.")
