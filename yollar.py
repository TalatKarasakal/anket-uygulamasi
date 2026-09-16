from datetime import datetime, timedelta
from uygulama import uygulama
from uzantılar import db
from modeller import Kullanıcı, Anket, Soru, Seçenek, Yanıt, Cevap
from email_validator import validate_email, EmailNotValidError
from flask import render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

TİP_İZİN_ALANI = {
    "açık uçlu": "açık_uçlu_izinli_mi",
    "evet/hayır": "evet_hayır_izinli_mi",
    "ölçek": "ölçek_izinli_mi",
    "çoktan seçmeli": "çoktan_seçmeli_izinli_mi",
}

@uygulama.route("/")
def ana_sayfa():
    kimlik = session.get("kullanıcı_kimlik")
    anketler = []
    if kimlik:
        anketler = db.session.execute(
            db.select(Anket).where(Anket.sahip_kimlik == kimlik)
        ).scalars().all()
    return render_template("ana_sayfa.html", anketler=anketler)

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

@uygulama.route("/çıkış")
def çıkış():
    session.pop("kullanıcı_kimlik", None)
    return redirect(url_for("ana_sayfa"))

@uygulama.route("/anket/yeni", methods=["GET", "POST"])
def anket_oluşturma():
    kimlik = session.get("kullanıcı_kimlik")

    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    if request.method == "POST":
        başlık = request.form["başlık"]
        açıklama = request.form["açıklama"]
        anonim_mi = "anonim_mi" in request.form
        if not başlık.strip():
            return render_template("anket_yeni.html", hata="Başlık boş bırakılamaz")

        herkese_açık_mı = "herkese_açık_mı" in request.form
        anket = Anket(başlık=başlık, açıklama=açıklama, anonim_mi=anonim_mi, herkese_açık_mı=herkese_açık_mı, sahip_kimlik=kimlik)
        db.session.add(anket)
        db.session.commit()
        return redirect(url_for("ana_sayfa"))
    return render_template("anket_yeni.html")

@uygulama.route("/anket/<int:anket_kimlik>/duzenle")
def anket_duzenle(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    return render_template("anket_duzenle.html", anket=anket)

@uygulama.route("/anket/<int:anket_kimlik>/ayarlar", methods=["GET", "POST"])
def anket_ayarları(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)

    if request.method == "POST":
        başlık = request.form["başlık"].strip()
        açıklama = request.form.get("açıklama", "")
        anonim_mi = "anonim_mi" in request.form
        herkese_açık_mı = "herkese_açık_mı" in request.form

        if not başlık:
            return render_template("anket_ayarlar.html", anket=anket, hata="Başlık boş bırakılamaz")

        if anonim_mi != anket.anonim_mi:
            yanıt_var = db.session.execute(
                db.select(db.func.count()).select_from(Yanıt).where(Yanıt.anket_kimlik == anket_kimlik)
            ).scalar() > 0
            if yanıt_var:
                return render_template("anket_ayarlar.html", anket=anket, hata="Yanıt almış bir anketin anonimlik ayarı değiştirilemez")
            anket.anonim_mi = anonim_mi

        süre_tipi = request.form.get("süre_tipi", "süre_yok")

        if süre_tipi == "son_tarih":
            son_tarih_metni = request.form.get("son_tarih", "").strip()
            if not son_tarih_metni:
                return render_template("anket_ayarlar.html", anket=anket, hata="Son tarih belirtilmelidir")
            try:
                yeni_son_tarih = datetime.fromisoformat(son_tarih_metni)
            except ValueError:
                return render_template("anket_ayarlar.html", anket=anket, hata="Geçersiz tarih formatı")
            if yeni_son_tarih <= datetime.now():
                return render_template("anket_ayarlar.html", anket=anket, hata="Son tarih gelecekte bir zaman olmalıdır")
            anket.son_tarih = yeni_son_tarih
            anket.süre_gün = None
        elif süre_tipi == "süre_gün":
            süre_gün_metni = request.form.get("süre_gün", "").strip()
            try:
                yeni_süre_gün = int(süre_gün_metni)
                if yeni_süre_gün <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return render_template("anket_ayarlar.html", anket=anket, hata="Süre pozitif bir gün sayısı olmalıdır")
            anket.süre_gün = yeni_süre_gün
            # süre_gün seçiliyse son_tarih'e dokunulmaz (yayına alma hesaplayacak)
        else:
            anket.son_tarih = None
            anket.süre_gün = None

        anket.başlık = başlık
        anket.açıklama = açıklama
        anket.herkese_açık_mı = herkese_açık_mı
        anket.açık_uçlu_izinli_mi = "açık_uçlu_izinli_mi" in request.form
        anket.evet_hayır_izinli_mi = "evet_hayır_izinli_mi" in request.form
        anket.ölçek_izinli_mi = "ölçek_izinli_mi" in request.form
        anket.çoktan_seçmeli_izinli_mi = "çoktan_seçmeli_izinli_mi" in request.form
        db.session.commit()

        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

    return render_template("anket_ayarlar.html", anket=anket)


@uygulama.route("/anket/<int:anket_kimlik>/soru/yeni", methods=["GET", "POST"])
def soru_ekleme(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    if anket.yayında_mı:
        return render_template("anket_duzenle.html", anket=anket, hata="Yayındaki ankete soru eklenemez")
    if request.method == "POST":
        metin = request.form["metin"]
        tip = request.form["tip"]
        if tip not in TİP_İZİN_ALANI:
            return render_template("anket_duzenle.html", anket=anket, hata="Geçersiz soru tipi")
        if not getattr(anket, TİP_İZİN_ALANI[tip]):
            return render_template("anket_duzenle.html", anket=anket, hata="Bu soru tipine izin verilmiyor")
        zorunlu_mu = "zorunlu_mu" in request.form


        if not metin.strip():
            return render_template("anket_duzenle.html", anket=anket, hata="Metin boş bırakılamaz")

        ölçek_alt_sınırı = None
        ölçek_üst_sınırı = None
        if tip == "ölçek":
            try:
                ölçek_alt_sınırı = int(request.form["ölçek_alt_sınırı"])
                ölçek_üst_sınırı = int(request.form["ölçek_üst_sınırı"])
            except (ValueError, KeyError):
                return render_template("anket_duzenle.html", anket=anket, hata="Geçersiz ölçek sınırı")

            if ölçek_alt_sınırı >= ölçek_üst_sınırı:
                return render_template("anket_duzenle.html", anket=anket, hata="Alt sınır üst sınırdan küçük olmalıdır")

        seçenekler = []
        if tip == "çoktan seçmeli":
            seçenekler = [s.strip() for s in request.form.getlist("seçenek") if s.strip()]
            if len(seçenekler) < 2:
                return render_template("anket_duzenle.html", anket=anket, hata="Seçenek en az 2 olmalıdır")

        soru = Soru(
            metin=metin,
            tip=tip,
            zorunlu_mu=zorunlu_mu,
            anket_kimlik=anket_kimlik,
            sıra=len(anket.sorular) + 1,
            ölçek_alt_sınırı=ölçek_alt_sınırı,
            ölçek_üst_sınırı=ölçek_üst_sınırı
        )

        for sıra, seçenek_metni in enumerate(seçenekler, start=1):
            soru.seçenekler.append(Seçenek(metin=seçenek_metni, sıra=sıra))

        db.session.add(soru)
        db.session.commit()
        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))
    return render_template("anket_duzenle.html", anket=anket)

@uygulama.route("/anket/<int:anket_kimlik>/soru/<int:soru_kimlik>/sil", methods=["POST"])
def soru_silme(anket_kimlik, soru_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    if anket.yayında_mı:
        return render_template("anket_duzenle.html", anket=anket, hata="Yayındaki anketin soruları silinemez")

    soru = db.session.get(Soru, soru_kimlik)
    if soru is None or soru.anket_kimlik != anket_kimlik:
        abort(404)

    db.session.delete(soru)
    kalan_sorular = [s for s in anket.sorular if s.kimlik != soru.kimlik]
    for yeni_sıra, s in enumerate(sorted(kalan_sorular, key=lambda x: x.sıra), start=1):
        s.sıra = yeni_sıra

    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))


@uygulama.route("/anket/<int:anket_kimlik>/yayinla", methods=["POST"])
def anket_yayınlama(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    if not anket.sorular:
        return render_template("anket_duzenle.html", anket=anket, hata="Boş anket yayınlanamaz")
    for soru in anket.sorular:
        alan = TİP_İZİN_ALANI.get(soru.tip)
        if alan and not getattr(anket, alan):
            return render_template("anket_duzenle.html", anket=anket, hata=f"İzinsiz tipte soru ({soru.tip}) içerdiği için anket yayınlanamaz")
    if anket.süre_gün:
        anket.son_tarih = datetime.now() + timedelta(days=anket.süre_gün)
    anket.yayında_mı = True
    db.session.commit()

    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/yayindan-al", methods=["POST"])
def anket_yayından_alma(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    anket.yayında_mı = False
    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/sil", methods=["POST"])
def anket_silme(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)

    db.session.delete(anket)
    db.session.commit()
    return redirect(url_for("ana_sayfa"))


@uygulama.context_processor
def oturum_bilgisi():
    kimlik = session.get("kullanıcı_kimlik")
    return {"oturum_kullanıcısı": db.session.get(Kullanıcı, kimlik) if kimlik else None}

@uygulama.route("/anketler")
def anket_listesi():
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))
    anketler = db.session.execute(
        db.select(Anket)
        .where(
            Anket.yayında_mı.is_(True),
            Anket.herkese_açık_mı.is_(True),
            db.or_(Anket.son_tarih.is_(None), Anket.son_tarih > datetime.now())
        )
    ).scalars().all()
    return render_template("anketler.html", anketler=anketler)

@uygulama.route("/anket/<int:anket_kimlik>/yanitla", methods=["GET", "POST"])
def anket_yanıtlama(anket_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)

    if not anket.yayında_mı:
        abort(403)

    yanıt = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.yanıtlayan_kimlik == kimlik,
        )
    ).scalar_one_or_none()
    if yanıt:
        return redirect(url_for("yanıt_sayfası", anket_kimlik=anket_kimlik))

    if anket.son_tarih and anket.son_tarih < datetime.now():
        return render_template("anket_yanitla.html", anket=anket, hata="Bu anketin süresi dolmuştur")

    if request.method == "POST":
        yanıt = Yanıt(anket_kimlik=anket_kimlik, yanıtlayan_kimlik=kimlik)

        for soru in anket.sorular:
            değer = request.form.get("soru_" + str(soru.kimlik))

            if not değer or not değer.strip():
                if soru.zorunlu_mu:
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata=f"'{soru.metin}' sorusu zorunludur")
                continue

            değer = değer.strip()
            cevap = Cevap(soru_kimlik=soru.kimlik)

            if soru.tip == "açık uçlu":
                cevap.metin_değeri = değer
            elif soru.tip == "evet/hayır":
                cevap.evet_hayır_değeri = (değer == "evet")
            elif soru.tip == "ölçek":
                try:
                    sayısal = int(değer)
                except ValueError:
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata=f"'{soru.metin}' için geçerli bir sayı giriniz")
                if (soru.ölçek_alt_sınırı is not None and sayısal < soru.ölçek_alt_sınırı) or \
                   (soru.ölçek_üst_sınırı is not None and sayısal > soru.ölçek_üst_sınırı):
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata=f"'{soru.metin}' için değer {soru.ölçek_alt_sınırı} ile {soru.ölçek_üst_sınırı} arasında olmalıdır")
                cevap.sayısal_değer = sayısal
            elif soru.tip == "çoktan seçmeli":
                try:
                    seçilen_kimlik = int(değer)
                except ValueError:
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata="Geçersiz seçenek")
                if not any(seçenek.kimlik == seçilen_kimlik for seçenek in soru.seçenekler):
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata="Geçersiz seçenek")
                cevap.seçilen_seçenek_kimlik = seçilen_kimlik

            yanıt.cevaplar.append(cevap)

        db.session.add(yanıt)
        db.session.commit()
        return redirect(url_for("yanıt_sayfası", anket_kimlik=anket_kimlik))

    return render_template("anket_yanitla.html", anket=anket)

@uygulama.route("/anket/<int:anket_kimlik>/yanitim")
def yanıt_sayfası(anket_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)

    yanıt = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.yanıtlayan_kimlik == kimlik,
        )
    ).scalar_one_or_none()
    if not yanıt:
        return redirect(url_for("anket_yanıtlama", anket_kimlik=anket_kimlik))

    cevaplar = {c.soru_kimlik: c for c in yanıt.cevaplar}
    return render_template("anket_yanitim.html", anket=anket, yanıt=yanıt, cevaplar=cevaplar)

@uygulama.route("/anket/<int:anket_kimlik>/yanitlar")
def anket_yanıtları(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)

    yanıtlar = db.session.execute(
        db.select(Yanıt).where(Yanıt.anket_kimlik == anket_kimlik).order_by(Yanıt.oluşturma_zamanı)
    ).scalars().all()

    if not anket.anonim_mi:
        yanıtlayanlar = {y.kimlik: y.yanıtlayan.e_posta for y in yanıtlar if y.yanıtlayan}
    else:
        yanıtlayanlar = {}

    return render_template("anket_yanitlar.html", anket=anket, yanıtlar=yanıtlar, yanıtlayanlar=yanıtlayanlar)

@uygulama.route("/anket/<int:anket_kimlik>/ozet")
def anket_özeti(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)

    yanıtlar = db.session.execute(
        db.select(Yanıt).where(Yanıt.anket_kimlik == anket_kimlik)
    ).scalars().all()
    toplam_yanıt = len(yanıtlar)

    özetler = {}
    for soru in anket.sorular:
        cevaplar = [c for y in yanıtlar for c in y.cevaplar if c.soru_kimlik == soru.kimlik]

        if soru.tip == "açık uçlu":
            metinler = [c.metin_değeri for c in cevaplar if c.metin_değeri and c.metin_değeri.strip()]
            özetler[soru.kimlik] = {
                "cevap_sayısı": len(metinler),
                "boş_sayısı": toplam_yanıt - len(metinler),
                "metinler": metinler,
            }
        elif soru.tip == "evet/hayır":
            evet_sayısı = sum(1 for c in cevaplar if c.evet_hayır_değeri is True)
            hayır_sayısı = sum(1 for c in cevaplar if c.evet_hayır_değeri is False)
            cevap_sayısı = evet_sayısı + hayır_sayısı
            özetler[soru.kimlik] = {
                "cevap_sayısı": cevap_sayısı,
                "boş_sayısı": toplam_yanıt - cevap_sayısı,
                "evet_sayısı": evet_sayısı,
                "hayır_sayısı": hayır_sayısı,
                "evet_yüzde": round((evet_sayısı / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0,
                "hayır_yüzde": round((hayır_sayısı / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0,
            }
        elif soru.tip == "ölçek":
            değerler = [c.sayısal_değer for c in cevaplar if c.sayısal_değer is not None]
            ortalama = round(sum(değerler) / len(değerler), 2) if değerler else None
            alt = soru.ölçek_alt_sınırı if soru.ölçek_alt_sınırı is not None else (min(değerler) if değerler else 1)
            ust = soru.ölçek_üst_sınırı if soru.ölçek_üst_sınırı is not None else (max(değerler) if değerler else 10)
            dağılım = []
            for val in range(alt, ust + 1):
                adet = değerler.count(val)
                yüzde = round((adet / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0
                dağılım.append({"değer": val, "adet": adet, "yüzde": yüzde})
            özetler[soru.kimlik] = {
                "cevap_sayısı": len(değerler),
                "boş_sayısı": toplam_yanıt - len(değerler),
                "ortalama": ortalama,
                "dağılım": dağılım,
            }
        elif soru.tip == "çoktan seçmeli":
            seçilenler = [c.seçilen_seçenek_kimlik for c in cevaplar if c.seçilen_seçenek_kimlik is not None]
            dağılım = []
            for sec in soru.seçenekler:
                adet = seçilenler.count(sec.kimlik)
                yüzde = round((adet / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0
                dağılım.append({"seçenek": sec, "adet": adet, "yüzde": yüzde})
            özetler[soru.kimlik] = {
                "cevap_sayısı": len(seçilenler),
                "boş_sayısı": toplam_yanıt - len(seçilenler),
                "dağılım": dağılım,
            }

    return render_template("anket_ozet.html", anket=anket, toplam_yanıt=toplam_yanıt, özetler=özetler)