import ollama

def ask_ai(prompt):

    response = ollama.chat(
        model="llama3",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]

reply = ask_ai("Tell me a joke")

print(reply)
