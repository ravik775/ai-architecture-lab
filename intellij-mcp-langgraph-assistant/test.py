import openai

client = openai.OpenAI(api_key="anything", base_url="http://localhost:4000")

response = client.chat.completions.create(
  model="gpt-3.5-turbo",
  messages=[{"role": "user", "content": "Write a short poem"}]
)
print(response.choices[0].message.content)