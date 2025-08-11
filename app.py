from flask import Flask, render_template, request, send_from_directory, redirect, url_for, session, abort
from openpyxl import Workbook, load_workbook
from datetime import datetime, timedelta
import os
import uuid
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import matplotlib.patches as patches
from flask_mail import Mail, Message
import requests
from flask_session import Session
import re

# ================== UYGULAMA & OTURUM ==================
app = Flask(__name__)
app.secret_key = 'gizli_anahtar'
app.permanent_session_lifetime = timedelta(minutes=10)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# ================== MAİL ==================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'winJohariTest@gmail.com'
app.config['MAIL_PASSWORD'] = 'pebxhabcyhcucsmy'
app.config['MAIL_DEFAULT_SENDER'] = 'winJohariTest@gmail.com'
mail = Mail(app)

# ================== DİZİNLER & AYARLAR ==================
BASE_DIR = os.getcwd()
STATIC_DIR = os.path.join(BASE_DIR, "static")
GRAFIK_DIR = os.path.join(STATIC_DIR, "grafik")
DATA_DIR = os.path.join(BASE_DIR, "data")  # gizli tutulacak
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(GRAFIK_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

EXCEL_YOLU = os.path.join(DATA_DIR, "sonuclar.xlsx")  # artık static'te değil!
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")  # basit indirme koruması

# Güvenli dosya adı
def slugify(txt):
    txt = re.sub(r"[^\w\s-]", "", str(txt), flags=re.UNICODE).strip()
    txt = re.sub(r"[\s-]+", "_", txt)
    return txt[:40] if txt else "kisi"

# ================== ROUTELAR ==================
@app.route("/")
def giris():
    # Modern hero tasarımlı giriş
    return render_template("giris.html")

@app.route("/index", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        yapan = request.form.get("yapan", "").strip()
        test_edilen = request.form.get("test_edilen", "").strip()
        if request.form.get("kendim_icin") == "on":
            test_edilen = yapan

        # Sorular yükle
        from sorular import sorular

        # Oturuma temel bilgiler
        session.permanent = True
        session['yapan'] = yapan
        session['test_edilen'] = test_edilen
        session['cevap_id'] = str(uuid.uuid4())

        # Test sayfası
        return render_template("test.html", yapan=yapan, test_edilen=test_edilen, sorular=sorular)
    return render_template("index.html")  # mevcut sayfan varsa çalışmaya devam etsin

# === GİZLİ RAPOR/EXCEL İNDİRME (Admin korumalı) ===
@app.route("/indir/sonuclar")
def indir_sonuc():
    sifre = request.args.get("pass")
    if sifre != ADMIN_PASS:
        abort(403)  # yetkisiz
    if not os.path.exists(EXCEL_YOLU):
        abort(404)
    # data/ klasöründen indirme
    directory = os.path.dirname(EXCEL_YOLU)
    filename = os.path.basename(EXCEL_YOLU)
    return send_from_directory(directory=directory, path=filename, as_attachment=True)

# === E-POSTA GÖNDERME (isteğe bağlı) ===
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

# === TEST SONUCU HESAPLAMA ===
@app.route("/sonuc", methods=["POST"])
def sonuc_post():
    yapan = request.form["yapan"]
    test_edilen = request.form["test_edilen"]
    cevaplar = {k: v for k, v in request.form.items() if k.startswith("soru")}
    puanlar, genel_A, genel_G = puan_hesapla(cevaplar)
    alanlar = hesapla_johari_alanlari(puanlar)

    # ÜSTTE Açık & Kör olacak şekilde grafik
    grafik_path = ciz_grafik_duzenli(alanlar, yapan)

    # Yapay zeka yorumu
    yorum = yapay_zeka_yorumla(yapan, test_edilen, alanlar)

    # Excel'e KAYIT (artık data/sonuclar.xlsx)
    kaydet_excel(yapan, test_edilen, puanlar, genel_A, genel_G, alanlar)

    # PRG (Post/Redirect/Get) için session'a özet koy
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

# ================== SKORLAMA ==================
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
    # 48x48 grid’e yerleştiriyoruz
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

# ================== GRAFİK (ÜSTTE AÇIK & KÖR) ==================
def ciz_grafik_duzenli(alanlar, yapan_adi):
    G = max(0, min(48, alanlar["G"]))
    A = max(0, min(48, alanlar["A"]))

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 48)
    ax.set_ylim(0, 48)
    ax.set_aspect("equal")
    ax.axis("off")

    # Üst sıra: Açık (sol) + Kör (sağ) — y=48-A ... 48
    rects = [
        ((0, 48 - A),       G,      A,      "Açık",        alanlar['acik_yuzde']),
        ((G, 48 - A),       48 - G, A,      "Kör",         alanlar['kor_yuzde']),
        ((0, 0),            G,      48 - A, "Gizli",       alanlar['gizli_yuzde']),
        ((G, 0),            48 - G, 48 - A, "Bilinmeyen",  alanlar['bilinmeyen_yuzde']),
    ]
    colors = ["#b8e994", "#f8c291", "#82ccdd", "#d1d8e0"]

    for i, (xy, w, h, ad, yuzde) in enumerate(rects):
        ax.add_patch(patches.Rectangle(xy, w, h, alpha=0.7, ec="#2f3640", fc=colors[i], lw=1.5))
        if w > 2 and h > 2:
            ax.text(xy[0] + w/2, xy[1] + h/2, f"{ad}\n%{yuzde}", ha="center", va="center", fontsize=12, weight="bold")

    # Bölücü çizgiler
    ax.axhline(y=48 - A, color="black", linewidth=1.5)
    ax.axvline(x=G, color="black", linewidth=1.5)

    # Dosya
    kisi = slugify(yapan_adi)
    dosya_adi = f"johari_{kisi}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    tam_yol = os.path.join(GRAFIK_DIR, dosya_adi)
    fig.tight_layout()
    fig.savefig(tam_yol, dpi=150)
    plt.close(fig)
    return f"grafik/{dosya_adi}"

# ================== YZ YORUM ==================
def yapay_zeka_yorumla(yapan, test_edilen, alanlar):
    prompt = f"""
Johari Test Sonucu:
Testi yapan kişi: {yapan}
Test edilen kişi: {test_edilen}

Açık Alan: %{alanlar['acik_yuzde']}
Kör Alan: %{alanlar['kor_yuzde']}
Gizli Alan: %{alanlar['gizli_yuzde']}
Bilinmeyen Alan: %{alanlar['bilinmeyen_yuzde']}

Yukarıdaki Johari Penceresi sonuçlarına göre, test edilen kişi hakkında profesyonel ve sade bir psikolojik analiz yap.
Açık alanı artırmak ve kör alanı azaltmak için uygulanabilir 3 öneri ver. 
Yalnızca Türkçe karakterler kullan, gereksiz semboller olmasın.
"""
    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }
    data = {
        "model": "z-ai/glm-4.5-air:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Yapay zeka yorum üretirken hata oluştu: {e}"

# ================== EXCEL KAYIT (GİZLİ KONUM) ==================
def kaydet_excel(yapan, test_edilen, puanlar, genel_A, genel_G, alanlar):
    # Dosya yoksa başlıkları oluştur
    if not os.path.exists(EXCEL_YOLU):
        wb = Workbook()
        ws = wb.active
        ws.title = "Sonuçlar"
        ws.append([
            "Tarih", "Yapan", "Test Edilen",
            "A1", "A2", "G1", "G2", "Genel A", "Genel G",
            "Açık", "Kör", "Gizli", "Bilinmeyen",
            "Açık (%)", "Kör (%)", "Gizli (%)", "Bilinmeyen (%)"
        ])
        wb.save(EXCEL_YOLU)

    wb = load_workbook(EXCEL_YOLU)
    ws = wb.active
    ws.append([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        yapan, test_edilen,
        puanlar["A1"], puanlar["A2"], puanlar["G1"], puanlar["G2"],
        genel_A, genel_G,
        round(alanlar["acik"], 4), round(alanlar["kor"], 4),
        round(alanlar["gizli"], 4), round(alanlar["bilinmeyen"], 4),
        alanlar['acik_yuzde'], alanlar['kor_yuzde'], alanlar['gizli_yuzde'], alanlar['bilinmeyen_yuzde']
    ])
    wb.save(EXCEL_YOLU)

# ================== MAİL ==================
def mail_gonder(eposta, yapan, grafik_path, alanlar, yorum):
    try:
        msg = Message(
            subject="Johari Test Sonucunuz ve Tavsiyeler",
            recipients=[eposta]
        )
        msg.body = (
            f"Merhaba {yapan},\n\n"
            "Johari Test Sonuçlarınız:\n"
            f"Açık Alan: %{alanlar['acik_yuzde']}\n"
            f"Kör Alan: %{alanlar['kor_yuzde']}\n"
            f"Gizli Alan: %{alanlar['gizli_yuzde']}\n"
            f"Bilinmeyen Alan: %{alanlar['bilinmeyen_yuzde']}\n\n"
            f"Yapay Zeka Yorumu:\n{yorum}\n\n"
            "Sevgiler,\nJohari Testi"
        )
        with app.open_resource(os.path.join("static", grafik_path)) as fp:
            msg.attach("johari_sonuc.png", "image/png", fp.read())
        mail.send(msg)
    except Exception as e:
        print(f"[HATA] Mail gönderilemedi: {str(e)}")

# ================== ÖNBELLEK KAPAT ==================
@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ================== MAIN ==================
if __name__ == "__main__":
    app.run(debug=True)
