from datetime import datetime, timedelta
from uygulama import uygulama
from uzantılar import db
from modeller import Kullanıcı, Anket, Soru, Seçenek, Yanıt, Cevap, AnketYetki
from email_validator import validate_email, EmailNotValidError
from flask import render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

TİP_İZİN_ALANI = {
    "açık uçlu": "açık_uçlu_izinli_mi",
    "evet/hayır": "evet_hayır_izinli_mi",
    "ölçek": "ölçek_izinli_mi",
    "çoktan seçmeli": "çoktan_seçmeli_izinli_mi",
}

def yetkiyi_getir(anket, kimlik):
    if not anket or not kimlik:
        return None
    return db.session.execute(
        db.select(AnketYetki).where(
            AnketYetki.anket_kimlik == anket.kimlik,
            AnketYetki.kullanıcı_kimlik == kimlik,
        )
    ).scalar_one_or_none()

def anketi_getir(anket_kimlik, izin=None):
    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        abort(403)
    if anket.sahip_kimlik == kimlik:
        return anket

    if izin == "sahip":
        abort(403)

    yetki = yetkiyi_getir(anket, kimlik)

    if not yetki:
        abort(403)

    if yetki.yöneticilik_mi:
        return anket

    if izin is None:
        return anket

    if isinstance(izin, (list, tuple, set)):
        if any(getattr(yetki, i, False) for i in izin):
            return anket
    elif getattr(yetki, izin, False):
        return anket

    abort(403)

def anket_duzenle_goster(anket, hata=None):
    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)
    yetki = yetkiyi_getir(anket, kimlik)
    yönetici_mi = sahip_mi or (yetki and yetki.yöneticilik_mi)
    üye_mi = (yetki is not None)
    return render_template("anket_duzenle.html", anket=anket, hata=hata, yönetici_mi=yönetici_mi, üye_mi=üye_mi)

@uygulama.route("/")
def ana_sayfa():
    kimlik = session.get("kullanıcı_kimlik")
    anketler = []
    üye_olunan_anketler = []
    if kimlik:
        anketler = db.session.execute(
            db.select(Anket).where(Anket.sahip_kimlik == kimlik)
        ).scalars().all()
        üye_olunan_anketler = db.session.execute(
            db.select(Anket).join(AnketYetki, AnketYetki.anket_kimlik == Anket.kimlik)
            .where(AnketYetki.kullanıcı_kimlik == kimlik)
        ).scalars().all()
    return render_template("ana_sayfa.html", anketler=anketler, üye_olunan_anketler=üye_olunan_anketler)

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
    anket = anketi_getir(anket_kimlik)
    return anket_duzenle_goster(anket)

@uygulama.route("/anket/<int:anket_kimlik>/ayarlar", methods=["GET", "POST"])
def anket_ayarları(anket_kimlik):
    anket = anketi_getir(anket_kimlik, ("içerik_düzenleme_mi", "yayın_yönetimi_mi"))
    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)
    yetki = yetkiyi_getir(anket, kimlik)

    içerik_yetkisi = sahip_mi or (yetki and (yetki.yöneticilik_mi or yetki.içerik_düzenleme_mi))
    yayın_yetkisi = sahip_mi or (yetki and (yetki.yöneticilik_mi or yetki.yayın_yönetimi_mi))

    if request.method == "POST":
        if not yayın_yetkisi and any(k in request.form for k in ("herkese_açık_mı", "anonim_mi", "süre_tipi", "son_tarih", "süre_gün")):
            return render_template(
                "anket_ayarlar.html",
                anket=anket,
                hata="Erişim politikası ve süre ayarlarını değiştirme yetkiniz yoktur",
                içerik_yetkisi=içerik_yetkisi,
                yayın_yetkisi=yayın_yetkisi,
            )

        if not içerik_yetkisi and any(k in request.form for k in ("başlık", "açıklama", "açık_uçlu_izinli_mi", "evet_hayır_izinli_mi", "ölçek_izinli_mi", "çoktan_seçmeli_izinli_mi")):
            return render_template(
                "anket_ayarlar.html",
                anket=anket,
                hata="İçerik ayarlarını değiştirme yetkiniz yoktur",
                içerik_yetkisi=içerik_yetkisi,
                yayın_yetkisi=yayın_yetkisi,
            )

        if içerik_yetkisi:
            başlık = request.form.get("başlık", "").strip()
            if not başlık:
                return render_template("anket_ayarlar.html", anket=anket, hata="Başlık boş bırakılamaz",
                                       içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)
            anket.başlık = başlık
            anket.açıklama = request.form.get("açıklama", "")
            anket.açık_uçlu_izinli_mi = "açık_uçlu_izinli_mi" in request.form
            anket.evet_hayır_izinli_mi = "evet_hayır_izinli_mi" in request.form
            anket.ölçek_izinli_mi = "ölçek_izinli_mi" in request.form
            anket.çoktan_seçmeli_izinli_mi = "çoktan_seçmeli_izinli_mi" in request.form

        if yayın_yetkisi:
            anonim_mi = "anonim_mi" in request.form
            if anonim_mi != anket.anonim_mi:
                yanıt_var = db.session.execute(
                    db.select(db.func.count()).select_from(Yanıt).where(Yanıt.anket_kimlik == anket_kimlik)
                ).scalar() > 0
                if yanıt_var:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Yanıt almış bir anketin anonimlik ayarı değiştirilemez",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)
                anket.anonim_mi = anonim_mi

            anket.herkese_açık_mı = "herkese_açık_mı" in request.form

            süre_tipi = request.form.get("süre_tipi", "süre_yok")
            if süre_tipi == "son_tarih":
                son_tarih_metni = request.form.get("son_tarih", "").strip()
                if not son_tarih_metni:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Son tarih belirtilmelidir",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)
                try:
                    yeni_son_tarih = datetime.fromisoformat(son_tarih_metni)
                except ValueError:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Geçersiz tarih formatı",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)
                if yeni_son_tarih <= datetime.now():
                    return render_template("anket_ayarlar.html", anket=anket, hata="Son tarih gelecekte bir zaman olmalıdır",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)
                anket.son_tarih = yeni_son_tarih
                anket.süre_gün = None
            elif süre_tipi == "süre_gün":
                süre_gün_metni = request.form.get("süre_gün", "").strip()
                try:
                    yeni_süre_gün = int(süre_gün_metni)
                    if yeni_süre_gün <= 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    return render_template("anket_ayarlar.html", anket=anket, hata="Süre pozitif bir gün sayısı olmalıdır",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)
                anket.süre_gün = yeni_süre_gün
            else:
                anket.son_tarih = None
                anket.süre_gün = None

        db.session.commit()
        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

    return render_template("anket_ayarlar.html", anket=anket,
                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi)


@uygulama.route("/anket/<int:anket_kimlik>/soru/yeni", methods=["GET", "POST"])
def soru_ekleme(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "içerik_düzenleme_mi")
    if anket.yayında_mı:
        return anket_duzenle_goster(anket, hata="Yayındaki ankete soru eklenemez")
    if request.method == "POST":
        metin = request.form["metin"]
        tip = request.form["tip"]
        if tip not in TİP_İZİN_ALANI:
            return anket_duzenle_goster(anket, hata="Geçersiz soru tipi")
        if not getattr(anket, TİP_İZİN_ALANI[tip]):
            return anket_duzenle_goster(anket, hata="Bu soru tipine izin verilmiyor")
        zorunlu_mu = "zorunlu_mu" in request.form

        if not metin.strip():
            return anket_duzenle_goster(anket, hata="Metin boş bırakılamaz")

        ölçek_alt_sınırı = None
        ölçek_üst_sınırı = None
        if tip == "ölçek":
            try:
                ölçek_alt_sınırı = int(request.form["ölçek_alt_sınırı"])
                ölçek_üst_sınırı = int(request.form["ölçek_üst_sınırı"])
            except (ValueError, KeyError):
                return anket_duzenle_goster(anket, hata="Geçersiz ölçek sınırı")

            if ölçek_alt_sınırı >= ölçek_üst_sınırı:
                return anket_duzenle_goster(anket, hata="Alt sınır üst sınırdan küçük olmalıdır")

        seçenekler = []
        if tip == "çoktan seçmeli":
            seçenekler = [s.strip() for s in request.form.getlist("seçenek") if s.strip()]
            if len(seçenekler) < 2:
                return anket_duzenle_goster(anket, hata="Seçenek en az 2 olmalıdır")

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
    return anket_duzenle_goster(anket)

@uygulama.route("/anket/<int:anket_kimlik>/soru/<int:soru_kimlik>/sil", methods=["POST"])
def soru_silme(anket_kimlik, soru_kimlik):
    anket = anketi_getir(anket_kimlik, "içerik_düzenleme_mi")
    if anket.yayında_mı:
        return anket_duzenle_goster(anket, hata="Yayındaki anketin soruları silinemez")

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
    anket = anketi_getir(anket_kimlik, "yayın_yönetimi_mi")
    if not anket.sorular:
        return anket_duzenle_goster(anket, hata="Boş anket yayınlanamaz")
    for soru in anket.sorular:
        alan = TİP_İZİN_ALANI.get(soru.tip)
        if alan and not getattr(anket, alan):
            return anket_duzenle_goster(anket, hata=f"İzinsiz tipte soru ({soru.tip}) içerdiği için anket yayınlanamaz")
    if anket.süre_gün:
        anket.son_tarih = datetime.now() + timedelta(days=anket.süre_gün)
    anket.yayında_mı = True
    db.session.commit()

    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/yayindan-al", methods=["POST"])
def anket_yayından_alma(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yayın_yönetimi_mi")
    anket.yayında_mı = False
    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/sil", methods=["POST"])
def anket_silme(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "sahip")

    db.session.delete(anket)
    db.session.commit()
    return redirect(url_for("ana_sayfa"))


@uygulama.route("/anket/<int:anket_kimlik>/uyeler", methods=["GET", "POST"])
def anket_üyeleri(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yöneticilik_mi")
    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)

    if request.method == "POST":
        e_posta = request.form.get("e_posta", "").strip()
        if not e_posta:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="E-posta adresi boş bırakılamaz")

        hedef_kullanıcı = db.session.execute(
            db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)
        ).scalar_one_or_none()

        if not hedef_kullanıcı:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="Bu e-posta adresine sahip kullanıcı bulunamadı")

        if hedef_kullanıcı.kimlik == anket.sahip_kimlik:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="Anket sahibi üye olarak eklenemez")

        if hedef_kullanıcı.kimlik == kimlik:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="Kendi yetkilerinizi değiştiremezsiniz")

        içerik_düzenleme_mi = "içerik_düzenleme_mi" in request.form
        yayın_yönetimi_mi = "yayın_yönetimi_mi" in request.form
        yanıtları_görme_mi = "yanıtları_görme_mi" in request.form
        kullanıcı_tanımlama_mı = "kullanıcı_tanımlama_mı" in request.form
        # Yöneticilik iznini yalnızca birincil sahip verebilir
        yöneticilik_mi = ("yöneticilik_mi" in request.form) if sahip_mi else False

        mevcut_yetki = yetkiyi_getir(anket, hedef_kullanıcı.kimlik)

        if mevcut_yetki:
            mevcut_yetki.içerik_düzenleme_mi = içerik_düzenleme_mi
            mevcut_yetki.yayın_yönetimi_mi = yayın_yönetimi_mi
            mevcut_yetki.yanıtları_görme_mi = yanıtları_görme_mi
            mevcut_yetki.kullanıcı_tanımlama_mı = kullanıcı_tanımlama_mı
            if sahip_mi:
                mevcut_yetki.yöneticilik_mi = yöneticilik_mi
            else:
                mevcut_yetki.yöneticilik_mi = False
        else:
            yeni_yetki = AnketYetki(
                anket_kimlik=anket_kimlik,
                kullanıcı_kimlik=hedef_kullanıcı.kimlik,
                içerik_düzenleme_mi=içerik_düzenleme_mi,
                yayın_yönetimi_mi=yayın_yönetimi_mi,
                yanıtları_görme_mi=yanıtları_görme_mi,
                kullanıcı_tanımlama_mı=kullanıcı_tanımlama_mı,
                yöneticilik_mi=yöneticilik_mi,
            )
            db.session.add(yeni_yetki)

        db.session.commit()
        return redirect(url_for("anket_üyeleri", anket_kimlik=anket_kimlik))

    return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi)


@uygulama.route("/anket/<int:anket_kimlik>/uye/<int:kullanici_kimlik>/cikar", methods=["POST"])
def anket_üye_çıkarma(anket_kimlik, kullanici_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        abort(403)

    # Kendi üyeliğinden ayrılma durumu
    if kullanici_kimlik == kimlik:
        yetki = yetkiyi_getir(anket, kimlik)
        if not yetki:
            abort(404)
        db.session.delete(yetki)
        db.session.commit()
        return redirect(url_for("ana_sayfa"))

    # Başka bir üyeyi çıkarma (yöneticilik veya sahiplik gerekir)
    anket = anketi_getir(anket_kimlik, "yöneticilik_mi")
    if kullanici_kimlik == anket.sahip_kimlik:
        abort(403)

    yetki = yetkiyi_getir(anket, kullanici_kimlik)
    if not yetki:
        abort(404)

    db.session.delete(yetki)
    db.session.commit()
    return redirect(url_for("anket_üyeleri", anket_kimlik=anket_kimlik))


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
    anket = anketi_getir(anket_kimlik, "yanıtları_görme_mi")

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
    anket = anketi_getir(anket_kimlik, "yanıtları_görme_mi")

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