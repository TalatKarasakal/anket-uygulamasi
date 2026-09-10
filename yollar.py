from uygulama import uygulama
from uzantılar import db
from modeller import Kullanıcı
from email_validator import validate_email, EmailNotValidError
from flask import render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

@uygulama.route("/")
def ana_sayfa():
    return "Anket Uygulaması"

@uygulama.route("/kayit", methods=["GET", "POST"])
def kayıt_ekranı():
    if request.method == "POST":
        e_posta = request.form["e_posta"]
        parola = request.form["parola"]
        # 1. biçim geçersizse mesaj göster, kaydetme
        try:
            validate_email(e_posta, check_deliverability=False)
        except EmailNotValidError:
            return render_template("kayit.html", hata="Geçersiz e-posta adresi")
        # 2. e-posta kayıtlıysa mesaj göster, kaydetme
        if db.session.execute(db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)).scalar_one_or_none():
            return render_template("kayit.html", hata="E-posta adresi zaten kayıtlı")
        # 3. özet al
        özet = generate_password_hash(parola)
        # 4. kullanıcıyı oluştur, add + commit
        kullanıcı = Kullanıcı(e_posta=e_posta, parola_özeti=özet)
        db.session.add(kullanıcı)
        db.session.commit()
        # 5. yönlendir
        return redirect(url_for("ana_sayfa"))
    return render_template("kayit.html")

@uygulama.route("/giris", methods=["GET", "POST"])
def giriş_ekranı():
    if request.method == "POST":
        e_posta = request.form["e_posta"]
        parola = request.form["parola"]
        # e-posta var mı?
        kullanıcı = db.session.execute(
            db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)
        ).scalar_one_or_none()
        if not kullanıcı:
            return render_template("giris.html", hata="E-posta veya parola hatalı")
        # parola eşleşiyor mu?
        if not check_password_hash(kullanıcı.parola_özeti, parola):
            return render_template("giris.html", hata="E-posta veya parola hatalı")
        # giriş yap (session ile)
        session["kullanıcı_kimlik"] = kullanıcı.kimlik
        return redirect(url_for("ana_sayfa"))
    return render_template("giris.html")