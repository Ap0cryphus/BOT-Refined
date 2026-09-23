import ollama

with open("incoming.txt", "r") as file:
    message = file.read()

print("User:", message)

response = ollama.chat(
    model="llama3",
    messages=[
        {
            "role": "user",
            "content": message
        }
    ]
)

reply = response["message"]["content"]

print("Bot:", reply)