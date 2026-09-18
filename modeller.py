from datetime import datetime
from uzantılar import db

class Kullanıcı(db.Model):
    __tablename__ = "kullanıcı"
    kimlik = db.Column(db.Integer, primary_key=True)
    e_posta = db.Column(db.String(255), unique=True, nullable=False)
    parola_özeti = db.Column(db.String(255), nullable=False)
    kalıplar = db.relationship("Kalıp", back_populates="sahip", cascade="all, delete-orphan")

class Anket(db.Model):
    __tablename__ = "anket"
    kimlik = db.Column(db.Integer, primary_key=True)
    sahip_kimlik = db.Column(db.Integer, db.ForeignKey("kullanıcı.kimlik"), nullable=True)
    başlık = db.Column(db.String(50), nullable=False)
    açıklama = db.Column(db.Text, nullable=True)
    anonim_mi = db.Column(db.Boolean, nullable=False, default=False)
    yayında_mı = db.Column(db.Boolean, nullable=False, default=False)
    oluşturma_zamanı = db.Column(db.DateTime, nullable=False, default=datetime.now)
    herkese_açık_mı = db.Column(db.Boolean, nullable=False, default=False)
    açık_uçlu_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    evet_hayır_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    ölçek_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    çoktan_seçmeli_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    son_tarih = db.Column(db.DateTime, nullable=True)
    süre_gün = db.Column(db.Integer, nullable=True)
    değerlendirilebilir_mi = db.Column(db.Boolean, nullable=False, default=False)
    değerlendirme_alt_sınırı = db.Column(db.Integer, nullable=True, default=0)
    değerlendirme_üst_sınırı = db.Column(db.Integer, nullable=True, default=10)
    kaynak_kalıp_adı = db.Column(db.String(100), nullable=True)
    sorular = db.relationship("Soru", back_populates="anket", cascade="all, delete-orphan", order_by="Soru.sıra")
    yanıtlar = db.relationship("Yanıt", back_populates="anket", cascade="all, delete-orphan")
    yetkiler = db.relationship("AnketYetki", back_populates="anket", cascade="all, delete-orphan")
    tanımlamalar = db.relationship("AnketTanımlama", back_populates="anket", cascade="all, delete-orphan")

class Soru(db.Model):
    __tablename__ = "soru"
    kimlik = db.Column(db.Integer, primary_key=True)
    anket_kimlik = db.Column(db.Integer, db.ForeignKey("anket.kimlik"), nullable=False)
    metin = db.Column(db.Text, nullable=False)
    tip = db.Column(db.String(20), nullable=False)
    zorunlu_mu = db.Column(db.Boolean, nullable=False, default=False)
    sıra = db.Column(db.Integer, nullable=False)
    ölçek_alt_sınırı = db.Column(db.Integer, nullable=True)
    ölçek_üst_sınırı = db.Column(db.Integer, nullable=True)
    anket = db.relationship("Anket", back_populates="sorular")
    seçenekler = db.relationship("Seçenek", back_populates="soru", cascade="all, delete-orphan", order_by="Seçenek.sıra")

class Seçenek(db.Model):
    __tablename__ = "seçenek"
    kimlik = db.Column(db.Integer, primary_key=True)
    soru_kimlik = db.Column(db.Integer, db.ForeignKey("soru.kimlik"), nullable=False)
    metin = db.Column(db.String(255), nullable=False)
    sıra = db.Column(db.Integer, nullable=False)
    soru = db.relationship("Soru", back_populates="seçenekler")

class Yanıt(db.Model):
    __tablename__ = "yanıt"
    kimlik = db.Column(db.Integer, primary_key=True)
    anket_kimlik = db.Column(db.Integer, db.ForeignKey("anket.kimlik"), nullable=False)
    yanıtlayan_kimlik = db.Column(db.Integer, db.ForeignKey("kullanıcı.kimlik"), nullable=True)
    oluşturma_zamanı = db.Column(db.DateTime, nullable=False, default=datetime.now)
    gönderim_zamanı = db.Column(db.DateTime, nullable=True)
    gönderildi_mi = db.Column(db.Boolean, nullable=False, default=False)
    değerlendirme_puanı = db.Column(db.Integer, nullable=True)
    __table_args__ = (db.UniqueConstraint("anket_kimlik", "yanıtlayan_kimlik"),)
    cevaplar = db.relationship("Cevap", back_populates="yanıt", cascade="all, delete-orphan")
    yanıtlayan = db.relationship("Kullanıcı")
    anket = db.relationship("Anket", back_populates="yanıtlar")
    
class Cevap(db.Model):
    __tablename__ = "cevap"
    kimlik = db.Column(db.Integer, primary_key=True)
    yanıt_kimlik = db.Column(db.Integer, db.ForeignKey("yanıt.kimlik"), nullable=False)
    soru_kimlik = db.Column(db.Integer, db.ForeignKey("soru.kimlik"), nullable=False)
    metin_değeri = db.Column(db.Text, nullable=True)
    sayısal_değer = db.Column(db.Integer, nullable=True)
    evet_hayır_değeri = db.Column(db.Boolean, nullable=True)
    seçilen_seçenek_kimlik = db.Column(db.Integer, db.ForeignKey("seçenek.kimlik"), nullable=True)
    __table_args__ = (db.UniqueConstraint("yanıt_kimlik", "soru_kimlik"),)
    yanıt = db.relationship("Yanıt", back_populates="cevaplar")
    seçenek = db.relationship("Seçenek")

class AnketYetki(db.Model):
    __tablename__ = "anket_yetki"
    kimlik = db.Column(db.Integer, primary_key=True)
    anket_kimlik = db.Column(db.Integer, db.ForeignKey("anket.kimlik"), nullable=False)
    kullanıcı_kimlik = db.Column(db.Integer, db.ForeignKey("kullanıcı.kimlik"), nullable=False)
    içerik_düzenleme_mi = db.Column(db.Boolean, nullable=False, default=False)
    yayın_yönetimi_mi = db.Column(db.Boolean, nullable=False, default=False)
    yanıtları_görme_mi = db.Column(db.Boolean, nullable=False, default=False)
    kullanıcı_tanımlama_mı = db.Column(db.Boolean, nullable=False, default=False)
    yöneticilik_mi = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.UniqueConstraint("anket_kimlik", "kullanıcı_kimlik"),)
    anket = db.relationship("Anket", back_populates="yetkiler")
    kullanıcı = db.relationship("Kullanıcı")

class AnketTanımlama(db.Model):
    __tablename__ = "anket_tanımlama"
    kimlik = db.Column(db.Integer, primary_key=True)
    anket_kimlik = db.Column(db.Integer, db.ForeignKey("anket.kimlik"), nullable=False)
    kullanıcı_kimlik = db.Column(db.Integer, db.ForeignKey("kullanıcı.kimlik"), nullable=False)
    zorunlu_mu = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.UniqueConstraint("anket_kimlik", "kullanıcı_kimlik"),)
    anket = db.relationship("Anket", back_populates="tanımlamalar")
    kullanıcı = db.relationship("Kullanıcı")

class Kalıp(db.Model):
    __tablename__ = "kalıp"
    kimlik = db.Column(db.Integer, primary_key=True)
    sahip_kimlik = db.Column(db.Integer, db.ForeignKey("kullanıcı.kimlik"), nullable=True)
    ad = db.Column(db.String(100), nullable=False)
    sistem_kalıbı_mı = db.Column(db.Boolean, nullable=False, default=False)
    açık_uçlu_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    evet_hayır_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    ölçek_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    çoktan_seçmeli_izinli_mi = db.Column(db.Boolean, nullable=False, default=True)
    anonim_mi = db.Column(db.Boolean, nullable=False, default=False)
    herkese_açık_mı = db.Column(db.Boolean, nullable=False, default=False)
    süre_gün = db.Column(db.Integer, nullable=True)
    __table_args__ = (db.UniqueConstraint("sahip_kimlik", "ad"),)
    sahip = db.relationship("Kullanıcı", back_populates="kalıplar")