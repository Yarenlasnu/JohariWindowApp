import openai

openai.api_key = "senin_api_anahtarın_buraya"

try:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Sen yardımcı bir asistansın."},
            {"role": "user", "content": "Merhaba! Nasılsın?"}
        ]
    )
    print("✅ API çalışıyor, cevap:")
    print(response['choices'][0]['message']['content'])
except Exception as e:
    print("❌ HATA:", type(e).__name__, "→", str(e))
