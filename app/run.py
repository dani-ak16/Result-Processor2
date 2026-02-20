from __init__ import create_app

app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )


# if __name__ == "__main__":
#     init_db()
#     # Automatically get your local network IP address
#     hostname = socket.gethostname()
#     local_ip = socket.gethostbyname(hostname)

#     print(f"\n🚀 Server running on:")
#     print(f"   Local:     http://127.0.0.1:5000")
#     print(f"   Network:   http://{local_ip}:5000\n")
#     print("📡 Connect other devices on the same Wi-Fi using the 'Network' address above.\n")

#     # Run Flask on all interfaces (so others can access it)
#     app.run(host="0.0.0.0", port=5000, debug=True)
