import requests

question = input("Ask me something: ")

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.2",
        "prompt": question,
        "stream": False
    }
)

answer = response.json()["response"]

print("\nAI Response:\n")
print(answer)