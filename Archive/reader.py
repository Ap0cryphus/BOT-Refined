with open("incoming.txt", "r") as file:
    message = file.read()

print("Received:", message)