from flask import Flask, render_template, request, send_from_directory, redirect, url_for, session
from openpyxl import Workbook, load_workbook
from datetime import datetime, timedelta
import os
import uuid
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from flask_mail import Mail, Message
import requests
from flask_session import Session

app = Flask(__name__)
app.secret_key = 'gizli_anahtar'
app.permanent_session_lifetime = timedelta(minutes=10)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'winJohariTest@gmail.com'
app.config['MAIL_PASSWORD'] = 'pebxhabcyhcucsmy'
app.config['MAIL_DEFAULT_SENDER'] = 'winJohariTest@gmail.com'
mail = Mail(app)

@app.route("/")
def giris():
    return render_template("giris.html")

@app.route("/index", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        yapan = request.form.get("yapan")
        test_edilen = request.form.get("test_edilen")
        if request.form.get("kendim_icin") == "on":
            test_edilen = yapan
        from sorular import sorular
        session.permanent = True
        session['yapan'] = yapan
        session['test_edilen'] = test_edilen
        session['cevap_id'] = str(uuid.uuid4())
        return render_template("test.html", yapan=yapan, test_edilen=test_edilen, sorular=sorular)
    return render_template("index.html")

@app.route("/indir/sonuclar")
def indir_sonuc():
    return send_from_directory(directory="static", path="sonuclar.xlsx", as_attachment=True)

@app.route("/eposta-gonder", methods=["POST"])
def eposta_gonder():
    yapan = request.form.get("yapan")
    eposta = request.form.get("eposta")
    grafik_path = request.form.get("grafik_path")
    yorum = request.form.get("yorum")
    alanlar = {
        "acik_yuzde": float(request.form.get("alanlar_acik", 0)),
        "kor_yuzde": float(request.form.get("alanlar_kor", 0)),
        "gizli_yuzde": float(request.form.get("alanlar_gizli", 0)),
        "bilinmeyen_yuzde": float(request.form.get("alanlar_bilinmeyen", 0))
    }
    mail_gonder(eposta, yapan, grafik_path, alanlar, yorum)
    return redirect(url_for("sonuc_get"))

@app.route("/sonuc", methods=["POST"])
def sonuc_post():
    yapan = request.form["yapan"]
    test_edilen = request.form["test_edilen"]
    cevaplar = {k: v for k, v in request.form.items() if k.startswith("soru")}
    puanlar, genel_A, genel_G = puan_hesapla(cevaplar)
    alanlar = hesapla_johari_alanlari(puanlar)
    grafik_path = ciz_grafik_duzenli(alanlar, yapan)
    yorum = yapay_zeka_yorumla(yapan, test_edilen, alanlar)
    kaydet_excel(yapan, test_edilen, puanlar, genel_A, genel_G, alanlar)

    eposta = request.form.get("eposta")
    if eposta:
        mail_gonder(eposta, yapan, grafik_path, alanlar, yorum)

    session["sonuc"] = {
        "yapan": yapan,
        "test_edilen": test_edilen,
        "puanlar": puanlar,
        "genel_A": genel_A,
        "genel_G": genel_G,
        "grafik_path": grafik_path,
        "alanlar": alanlar,
        "yorum": yorum
    }
    return redirect(url_for("sonuc_get"))

@app.route("/sonuc", methods=["GET"])
def sonuc_get():
    data = session.get("sonuc")
    if not data:
        return redirect(url_for("index"))
    return render_template("sonuc.html", **data)

def puan_hesapla(cevaplar):
    G1 = [1,4,6,14,16,24,26,34,36,40,46,47]
    G2 = [3,9,12,18,21,28,30,31,37,41,44]
    A1 = [2,5,7,13,17,19,23,25,27,29,32,35]
    A2 = [8,10,11,15,20,22,33,38,42,43,45,48]

    harf_puanlari = {"A": 1, "B": 2, "C": 3, "D": 4}
    puanlar = {"G1": 0, "G2": 0, "A1": 0, "A2": 0}

    for key, secenek in cevaplar.items():
        soru_no = int(key.replace("soru", ""))
        for grup, liste in [("G1", G1), ("G2", G2), ("A1", A1), ("A2", A2)]:
            if soru_no in liste:
                puanlar[grup] += harf_puanlari.get(secenek, 0)

    genel_A = round((puanlar["A1"] + puanlar["A2"]) / 2, 2)
    genel_G = round((puanlar["G1"] + puanlar["G2"]) / 2, 2)
    return puanlar, genel_A, genel_G

def hesapla_johari_alanlari(puanlar):
    A = (puanlar["A1"] + puanlar["A2"]) / 2
    G = (puanlar["G1"] + puanlar["G2"]) / 2

    alan_acik = (G * A) / 2304
    alan_kor = ((48 - G) * A) / 2304
    alan_gizli = (G * (48 - A)) / 2304
    alan_bilinmeyen = ((48 - G) * (48 - A)) / 2304

    return {
        "acik": alan_acik,
        "kor": alan_kor,
        "gizli": alan_gizli,
        "bilinmeyen": alan_bilinmeyen,
        "acik_yuzde": round(alan_acik * 100, 2),
        "kor_yuzde": round(alan_kor * 100, 2),
        "gizli_yuzde": round(alan_gizli * 100, 2),
        "bilinmeyen_yuzde": round(alan_bilinmeyen * 100, 2),
        "G": G,
        "A": A
    }

def ciz_grafik_duzenli(alanlar, yapan_adi):
    G = alanlar["G"]
    A = alanlar["A"]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.add_patch(plt.Rectangle((0, 48 - A), G, A, color="green", alpha=0.4))
    ax.text(G/2, 48 - A/2, f"Açık\n{alanlar['acik_yuzde']}%", ha="center", va="center")

    ax.add_patch(plt.Rectangle((G, 48 - A), 48 - G, A, color="red", alpha=0.4))
    ax.text(G + (48 - G)/2, 48 - A/2, f"Kör\n{alanlar['kor_yuzde']}%", ha="center", va="center")

    ax.add_patch(plt.Rectangle((0, 0), G, 48 - A, color="orange", alpha=0.4))
    ax.text(G/2, (48 - A)/2, f"Gizli\n{alanlar['gizli_yuzde']}%", ha="center", va="center")

    ax.add_patch(plt.Rectangle((G, 0), 48 - G, 48 - A, color="gray", alpha=0.4))
    ax.text(G + (48 - G)/2, (48 - A)/2, f"Bilinmeyen\n{alanlar['bilinmeyen_yuzde']}%", ha="center", va="center")

    ax.set_xlim(0, 48)
    ax.set_ylim(0, 48)
    ax.axhline(y=48 - A, color="black", linewidth=1.5)
    ax.axvline(x=G, color="black", linewidth=1.5)
    ax.axis("off")
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.set_title("Johari Penceresi")

    os.makedirs("static/grafik", exist_ok=True)
    dosya_adi = f"grafik_duzenli_{yapan_adi}.png"
    tam_yol = os.path.join("static", "grafik", dosya_adi)
    plt.savefig(tam_yol)
    plt.close()
    return f"grafik/{dosya_adi}"

import os
import requests

def yapay_zeka_yorumla(yapan, test_edilen, alanlar):
    prompt = f"""
Johari Test Sonucu:
Testi yapan kişi: {yapan}
Test edilen kişi: {test_edilen}

Açık Alan: {alanlar['acik']} puan
Kör Alan: {alanlar['kor']} puan
Gizli Alan: {alanlar['gizli']} puan
Bilinmeyen Alan: {alanlar['bilinmeyen']} puan

Yukarıdaki Johari Penceresi sonuçlarına göre, test edilen kişi hakkında psikolojik bir analiz yapmanı istiyorum...
Profesyonel bir Johari analizi yapmalısın.Oranların anlamlarını birlikte değerlendir, güçlü ve zayıf yönlerini yorumla. Açık alanı artırmak için önerilerde bulun.Muhteşem bir youm yap ve mükemmel bir yazı görselinde olsun. Gereksiz karakterli bulundurma # + gibi gibi temiz duru bir analiz görünütüsü çıksın ortaya ve öneri fikri ver. Sadece Türkçe karakterler kullan
    """

    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "z-ai/glm-4.5-air:free",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Yapay zeka yorum üretirken hata oluştu: {e}"


def kaydet_excel(yapan, test_edilen, puanlar, genel_A, genel_G, alanlar):
    dosya_yolu = "static/sonuclar.xlsx"
    if not os.path.exists(dosya_yolu):
        wb = Workbook()
        ws = wb.active
        ws.title = "Sonuçlar"
        ws.append([
            "Tarih", "Yapan", "Test Edilen",
            "A1", "A2", "G1", "G2", "Genel A", "Genel G",
            "Açık", "Kör", "Gizli", "Bilinmeyen",
            "Açık (%)", "Kör (%)", "Gizli (%)", "Bilinmeyen (%)"
        ])
    else:
        wb = load_workbook(dosya_yolu)
        ws = wb.active

    ws.append([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        yapan, test_edilen,
        puanlar["A1"], puanlar["A2"], puanlar["G1"], puanlar["G2"],
        genel_A, genel_G,
        round(alanlar["acik"], 2), round(alanlar["kor"], 2),
        round(alanlar["gizli"], 2), round(alanlar["bilinmeyen"], 2),
        f"%{alanlar['acik_yuzde']}", f"%{alanlar['kor_yuzde']}",
        f"%{alanlar['gizli_yuzde']}", f"%{alanlar['bilinmeyen_yuzde']}"
    ])
    wb.save(dosya_yolu)

def mail_gonder(eposta, yapan, grafik_path, alanlar, yorum):
    try:
        msg = Message(
            subject="Johari Test Sonucunuz ve Tavsiyemiz",
            recipients=[eposta]
        )
        msg.body = (
            f"Merhaba {yapan},\n\n"
            "Johari Test Sonuçlarınız:\n"
            f"Açık Alan: %{alanlar['acik_yuzde']}\n"
            f"Kör Alan: %{alanlar['kor_yuzde']}\n"
            f"Gizli Alan: %{alanlar['gizli_yuzde']}\n"
            f"Bilinmeyen Alan: %{alanlar['bilinmeyen_yuzde']}\n\n"
            f"🎯 Yapay Zeka Yorumu:\n{yorum}\n\n"
            "Teşekkürler,\nJohari Test Platformu"
        )
        with app.open_resource(os.path.join("static", grafik_path)) as fp:
            msg.attach("johari_sonucunuz.png", "image/png", fp.read())
        mail.send(msg)
    except Exception as e:
        print(f"[HATA] Mail gönderilemedi: {str(e)}")

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    app.run(debug=True)
