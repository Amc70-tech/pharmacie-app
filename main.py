# -*- coding: utf-8 -*-
"""Dépôt pharmaceutique - application Android (Kivy + SQLite)."""

import csv
import hashlib
import io
import os
import re
import shutil
import sqlite3
import unicodedata
from datetime import datetime

from kivy.config import Config
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput
from kivy.utils import platform

# Le clavier ne cache plus le champ en cours de saisie
Window.softinput_mode = 'below_target'

CHEMIN_DB = ""
DOSSIER_RECUS = ""
DOSSIER_EXPORTS = ""

ROUGE = (1, 0.3, 0.3, 1)
VERT = (0, 1, 0, 1)
BLANC = (1, 1, 1, 1)

NOM_DEPOT_DEFAUT = "DÉPÔT PHARMACEUTIQUE"
LARGEUR_RECU = 40
SEUIL_DEFAUT = 10
TEXTE_CHOIX = "Choisir un médicament (liste)"
TOUS_FOURNISSEURS = "Tous les fournisseurs"


# ====================================================
# OUTILS GÉNÉRAUX (testables sans interface)
# ====================================================
def sans_accents(texte):
    texte = unicodedata.normalize('NFD', texte or "")
    return ''.join(c for c in texte if unicodedata.category(c) != 'Mn')


def fmt_aff(n):
    """Nombre pour l'affichage : 15 000 ou 12.50"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n == int(n):
        return f"{int(n):,}".replace(",", " ")
    return f"{n:.2f}"


def fmt_csv(n):
    """Nombre pour le CSV : 1500 ou 12.5 (sans séparateur de milliers)."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "" if n is None else str(n)
    return str(int(n)) if n == int(n) else str(round(n, 2))


def normaliser_nom(nom):
    """Évite « PHARMACIE DÉPÔT PHARMACEUTIQUE » (le mot apparaissait deux fois)."""
    nom = (nom or "").strip()
    bas = sans_accents(nom).lower()
    if bas in ("", "pharmacie"):
        return NOM_DEPOT_DEFAUT
    if "depot" in bas:
        nom = re.sub(r'(?i)\bpharmacie\b', '', nom)
        nom = re.sub(r'\s+', ' ', nom).strip(" -–—,.")
    return nom or NOM_DEPOT_DEFAUT


def preparer_chemins(base):
    """Base, reçus et exports dans le dossier privé de l'app.
    Au premier lancement, la base embarquée dans l'APK est copiée."""
    os.makedirs(base, exist_ok=True)
    chemin_db = os.path.join(base, "pharmacie.db")
    if not os.path.exists(chemin_db):
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pharmacie.db")
        if os.path.exists(source):
            shutil.copy(source, chemin_db)
    dossier_recus = os.path.join(base, "recus")
    dossier_exports = os.path.join(base, "exports")
    os.makedirs(dossier_recus, exist_ok=True)
    os.makedirs(dossier_exports, exist_ok=True)
    return chemin_db, dossier_recus, dossier_exports


def connexion(chemin_db):
    conn = sqlite3.connect(chemin_db)
    conn.row_factory = sqlite3.Row
    return conn


def migrer_base(chemin_db):
    """Ajoute la colonne client aux ventes et corrige le nom du dépôt."""
    conn = sqlite3.connect(chemin_db)
    try:
        colonnes = [r[1] for r in conn.execute("PRAGMA table_info(ventes)")]
        if colonnes and "client" not in colonnes:
            conn.execute("ALTER TABLE ventes ADD COLUMN client TEXT DEFAULT ''")
        ligne = conn.execute("SELECT valeur FROM parametres WHERE cle='nom'").fetchone()
        if ligne and ligne[0]:
            propre = normaliser_nom(ligne[0])
            if propre != ligne[0]:
                conn.execute("UPDATE parametres SET valeur=? WHERE cle='nom'", (propre,))
        conn.commit()
    except Exception as e:
        print("Migration ignorée :", e)
    finally:
        conn.close()


def lire_parametres(chemin_db):
    try:
        conn = connexion(chemin_db)
        try:
            return {r["cle"]: r["valeur"] for r in conn.execute("SELECT cle, valeur FROM parametres")}
        finally:
            conn.close()
    except Exception:
        return {}


# ----------------------------------------------------
# Médicaments / ventes / reçus
# ----------------------------------------------------
def lister_medicaments(chemin_db, recherche=""):
    conn = connexion(chemin_db)
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, nom, stock, prix_vente FROM medicaments ORDER BY nom")]
    finally:
        conn.close()
    mot = sans_accents(recherche).lower().strip()
    if mot:
        rows = [r for r in rows if mot in sans_accents(r["nom"]).lower()]
    return rows


def enregistrer_vente_panier(chemin_db, lignes, client=""):
    """lignes = [(produit_id, quantite), ...] : une seule vente, un seul reçu.
    Tout est enregistré ou rien. Lève ValueError si impossible."""
    if not lignes:
        raise ValueError("Le panier est vide.")
    conn = connexion(chemin_db)
    try:
        c = conn.cursor()
        maintenant = datetime.now()
        date_v = maintenant.strftime("%Y-%m-%d %H:%M")
        base_groupe = maintenant.strftime("V%Y%m%d_%H%M%S")
        groupe, n = base_groupe, 1
        while c.execute("SELECT 1 FROM ventes WHERE groupe=?", (groupe,)).fetchone():
            n += 1
            groupe = f"{base_groupe}_{n}"

        details = []
        for produit_id, qte in lignes:
            if qte <= 0:
                raise ValueError("Quantité invalide.")
            produit = c.execute("SELECT * FROM medicaments WHERE id=?", (produit_id,)).fetchone()
            if produit is None:
                raise ValueError("Produit introuvable.")
            stock = produit["stock"] or 0
            if stock < qte:
                raise ValueError(f"Stock insuffisant pour {produit['nom']} ({stock} dispo).")
            prix = produit["prix_vente"] or 0
            total = qte * prix
            c.execute("UPDATE medicaments SET stock=? WHERE id=?", (stock - qte, produit_id))
            c.execute("INSERT INTO ventes(date_vente,medicament,quantite,prix_unitaire,total,groupe,client) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (date_v, produit["nom"], qte, prix, total, groupe, client))
            details.append({"nom": produit["nom"], "qte": qte, "prix": prix, "total": total})
        conn.commit()
        return {"lignes": details, "total": sum(d["total"] for d in details),
                "groupe": groupe, "date": date_v, "client": client}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def construire_recu(params, vente):
    """Texte du reçu (plusieurs produits). Le nom du dépôt n'apparaît qu'une seule fois."""
    nom = normaliser_nom(params.get("nom", ""))
    vus = {sans_accents(nom).lower()}
    ligne_eq = "=" * LARGEUR_RECU
    ligne_tr = "-" * LARGEUR_RECU

    out = [ligne_eq, nom.upper().center(LARGEUR_RECU)]
    for cle, prefixe in (("adresse", ""), ("telephone", "Tel : ")):
        valeur = (params.get(cle) or "").strip()
        cle_vue = sans_accents(valeur).lower()
        if valeur and cle_vue not in vus and cle_vue != "pharmacie":
            vus.add(cle_vue)
            out.append((prefixe + valeur).center(LARGEUR_RECU))
    out += [ligne_eq,
            f"N° : {vente['groupe']}",
            f"Date : {vente['date']}"]
    if vente.get("client"):
        out.append(f"Client : {vente['client']}")
    out.append(ligne_tr)
    for i, l in enumerate(vente["lignes"], start=1):
        out.append(f"{i}. {l['nom']}")
        out.append(f"      {l['qte']} x {fmt_aff(l['prix'])} = {fmt_aff(l['total'])} FCFA")
    out += [ligne_tr,
            f"Articles : {sum(l['qte'] for l in vente['lignes'])}",
            f"TOTAL : {fmt_aff(vente['total'])} FCFA",
            ligne_eq,
            (params.get("message") or "Merci de votre visite !")]
    return "\n".join(out) + "\n"


def ecrire_recu(dossier, groupe, texte):
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"recu_{groupe}.txt")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(texte)
    return chemin


# ----------------------------------------------------
# Commande
# ----------------------------------------------------
def lister_fournisseurs(chemin_db):
    conn = connexion(chemin_db)
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT fournisseur FROM medicaments "
            "WHERE fournisseur IS NOT NULL AND TRIM(fournisseur)<>'' ORDER BY fournisseur")]
    finally:
        conn.close()


def produits_a_commander(chemin_db, seuil, fournisseur=None):
    conn = connexion(chemin_db)
    try:
        sql = ("SELECT id, nom, stock, fournisseur FROM medicaments "
               "WHERE IFNULL(stock,0) <= ?")
        args = [seuil]
        if fournisseur:
            sql += " AND fournisseur = ?"
            args.append(fournisseur)
        sql += " ORDER BY fournisseur, nom"
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def texte_commande(nom_depot, lignes, fournisseur=None):
    """lignes = [(nom, quantite, fournisseur), ...]"""
    out = [f"COMMANDE - {nom_depot}",
           f"Date : {datetime.now().strftime('%d/%m/%Y')}"]
    if fournisseur:
        out.append(f"Fournisseur : {fournisseur}")
        out.append("")
        for nom, qte, _ in lignes:
            out.append(f"- {nom} : {qte}")
    else:
        groupes = {}
        for nom, qte, fourn in lignes:
            groupes.setdefault(fourn or "Sans fournisseur", []).append((nom, qte))
        for fourn in sorted(groupes):
            out.append("")
            out.append(f"Fournisseur : {fourn}")
            for nom, qte in groupes[fourn]:
                out.append(f"- {nom} : {qte}")
    out += ["", f"Total : {len(lignes)} produit(s)", "Merci de confirmer la disponibilité."]
    return "\n".join(out)


# ----------------------------------------------------
# CSV
# ----------------------------------------------------
ENTETES_STOCK = ["nom", "categorie", "stock", "prix_achat", "prix_vente",
                 "peremption", "ordonnance", "lot", "fournisseur", "type"]
ENTETES_VENTES = ["date_vente", "medicament", "quantite", "prix_unitaire",
                  "total", "groupe", "client"]

ALIAS_COLONNES = {
    "nom": ["nom", "name", "designation", "medicament", "produit", "libelle"],
    "categorie": ["categorie", "category", "famille"],
    "stock": ["stock", "quantite", "qte", "qty"],
    "prix_achat": ["prix_achat", "prixachat", "achat", "pa"],
    "prix_vente": ["prix_vente", "prixvente", "vente", "prix", "pv"],
    "peremption": ["peremption", "expiration", "date_peremption", "expiry"],
    "ordonnance": ["ordonnance", "rx"],
    "lot": ["lot", "batch"],
    "fournisseur": ["fournisseur", "supplier"],
    "type": ["type"],
}


def csv_texte(entetes, lignes):
    """CSV séparé par des points-virgules (s'ouvre directement dans Excel)."""
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=';', lineterminator='\r\n')
    ecrivain.writerow(entetes)
    for ligne in lignes:
        ecrivain.writerow(ligne)
    return "\ufeff" + sortie.getvalue()


def exporter_stock_csv(chemin_db):
    conn = connexion(chemin_db)
    try:
        lignes = []
        for r in conn.execute("SELECT * FROM medicaments ORDER BY nom"):
            lignes.append([r["nom"], r["categorie"] or "", fmt_csv(r["stock"]),
                           fmt_csv(r["prix_achat"]), fmt_csv(r["prix_vente"]),
                           r["peremption"] or "", r["ordonnance"] or 0,
                           r["lot"] or "", r["fournisseur"] or "", r["type"] or "medicament"])
    finally:
        conn.close()
    return csv_texte(ENTETES_STOCK, lignes)


def exporter_ventes_csv(chemin_db):
    conn = connexion(chemin_db)
    try:
        lignes = []
        for r in conn.execute("SELECT * FROM ventes ORDER BY id"):
            client = r["client"] if "client" in r.keys() else ""
            lignes.append([r["date_vente"], r["medicament"], fmt_csv(r["quantite"]),
                           fmt_csv(r["prix_unitaire"]), fmt_csv(r["total"]),
                           r["groupe"] or "", client or ""])
    finally:
        conn.close()
    return csv_texte(ENTETES_VENTES, lignes)


def _entete_normalisee(h):
    h = sans_accents(h).lower().strip().lstrip("\ufeff")
    return re.sub(r'[\s\-]+', '_', h)


def _nombre(valeur, defaut=0.0):
    v = (valeur or "").strip().replace("\u00a0", "").replace(" ", "")
    if not v:
        return defaut
    if "," in v and "." in v:
        v = v.replace(",", "")
    else:
        v = v.replace(",", ".")
    return float(v)


def lire_csv_medicaments(lignes):
    """Retourne (liste_de_medicaments, liste_d_erreurs)."""
    lignes = [l for l in (x.lstrip("\ufeff") for x in lignes) if l.strip()]
    if not lignes:
        return [], ["Le fichier est vide."]
    entete = lignes[0]
    delimiteur = max(";,\t", key=entete.count)
    lignes_csv = list(csv.reader(lignes, delimiter=delimiteur))
    cles = [_entete_normalisee(h) for h in lignes_csv[0]]

    index = {}
    for champ, alias in ALIAS_COLONNES.items():
        for i, h in enumerate(cles):
            if h in alias and champ not in index:
                index[champ] = i
    if "nom" not in index:
        return [], ["Colonne « nom » introuvable. Exportez d'abord le stock pour voir le bon format."]

    medocs, erreurs = [], []
    for numero, ligne in enumerate(lignes_csv[1:], start=2):
        def val(champ, ligne=ligne):
            i = index.get(champ)
            return ligne[i].strip() if i is not None and i < len(ligne) else ""

        nom = val("nom")
        if not nom:
            erreurs.append(f"Ligne {numero} : nom vide.")
            continue
        try:
            stock = int(_nombre(val("stock")))
            prix_achat = _nombre(val("prix_achat"))
            prix_vente = _nombre(val("prix_vente"))
        except ValueError:
            erreurs.append(f"Ligne {numero} ({nom}) : nombre invalide.")
            continue
        ordonnance = 1 if sans_accents(val("ordonnance")).lower() in ("1", "oui", "o", "yes", "true", "vrai", "x") else 0
        medocs.append({
            "nom": nom, "categorie": val("categorie"), "stock": stock,
            "prix_achat": prix_achat, "prix_vente": prix_vente,
            "peremption": val("peremption"), "ordonnance": ordonnance,
            "lot": val("lot"), "fournisseur": val("fournisseur"),
            "type": val("type") or "medicament",
        })
    return medocs, erreurs


def importer_medicaments(chemin_db, medocs):
    """Met à jour les produits existants (même nom + même lot), ajoute les autres."""
    ajoutes = maj = 0
    conn = connexion(chemin_db)
    try:
        c = conn.cursor()
        for m in medocs:
            c.execute("SELECT id FROM medicaments WHERE LOWER(nom)=LOWER(?) AND IFNULL(lot,'')=?",
                      (m["nom"], m["lot"]))
            existant = c.fetchone()
            valeurs = (m["categorie"], m["stock"], m["prix_achat"], m["prix_vente"],
                       m["peremption"], m["ordonnance"], m["lot"], m["fournisseur"], m["type"])
            if existant:
                c.execute("UPDATE medicaments SET categorie=?, stock=?, prix_achat=?, prix_vente=?, "
                          "peremption=?, ordonnance=?, lot=?, fournisseur=?, type=? WHERE id=?",
                          valeurs + (existant["id"],))
                maj += 1
            else:
                c.execute("INSERT INTO medicaments(nom, categorie, stock, prix_achat, prix_vente, "
                          "peremption, ordonnance, lot, fournisseur, type) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (m["nom"],) + valeurs)
                ajoutes += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return ajoutes, maj


# ====================================================
# ANDROID : partage, enregistrement et ouverture de fichiers
# ====================================================
class Plateforme:
    REQ_IMPORT = 4101
    REQ_EXPORT = 4102

    def __init__(self):
        self.android = (platform == 'android')
        self._lie = False
        self._contenu_export = None
        self._cb_export = None
        self._cb_import = None

    def lier(self):
        """À appeler au démarrage : écoute le retour des sélecteurs de fichiers."""
        if not self.android or self._lie:
            return
        try:
            from android import activity
            activity.bind(on_activity_result=self._on_activity_result)
            self._lie = True
        except Exception as e:
            print("Liaison activité impossible :", e)

    # ---------- Écran toujours en portrait ----------
    def forcer_portrait(self):
        if not self.android:
            return
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass

            @run_on_ui_thread
            def appliquer():
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                ActivityInfo = autoclass('android.content.pm.ActivityInfo')
                PythonActivity.mActivity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
            appliquer()
        except Exception as e:
            print("Orientation non forcée :", e)

    # ---------- Partage de texte (WhatsApp, SMS, email...) ----------
    def partager_texte(self, texte, titre="Partager"):
        """Retourne True si la fenêtre de partage a été ouverte, False si le texte a seulement été copié."""
        if not self.android:
            Clipboard.copy(texte)
            return False
        try:
            from jnius import autoclass, cast
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            String = autoclass('java.lang.String')
            cs = 'java.lang.CharSequence'
            intent = Intent()
            intent.setAction(Intent.ACTION_SEND)
            intent.setType('text/plain')
            intent.putExtra(Intent.EXTRA_TEXT, cast(cs, String(texte)))
            choix = Intent.createChooser(intent, cast(cs, String(titre)))
            PythonActivity.mActivity.startActivity(choix)
            return True
        except Exception as e:
            print("Partage impossible :", e)
            Clipboard.copy(texte)
            return False

    # ---------- Export : l'utilisateur choisit où enregistrer ----------
    def exporter_fichier(self, nom_fichier, contenu, callback):
        """callback(ok, message)"""
        if not self.android:
            try:
                chemin = os.path.join(DOSSIER_EXPORTS, nom_fichier)
                with open(chemin, "w", encoding="utf-8") as f:
                    f.write(contenu)
                callback(True, f"Fichier enregistré :\n{chemin}")
            except Exception as e:
                callback(False, f"Erreur : {e}")
            return
        try:
            from jnius import autoclass, cast
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            String = autoclass('java.lang.String')
            self._contenu_export = contenu
            self._cb_export = callback
            intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType('text/csv')
            intent.putExtra(Intent.EXTRA_TITLE, cast('java.lang.CharSequence', String(nom_fichier)))
            PythonActivity.mActivity.startActivityForResult(intent, self.REQ_EXPORT)
        except Exception as e:
            callback(False, f"Erreur : {e}")

    # ---------- Import : l'utilisateur choisit le fichier ----------
    def importer_fichier(self, callback):
        """callback(ok, lignes_ou_message)"""
        if not self.android:
            chemin = os.path.join(DOSSIER_EXPORTS, "import.csv")
            if not os.path.exists(chemin):
                callback(False, f"Placez votre fichier ici :\n{chemin}")
                return
            try:
                with open(chemin, "r", encoding="utf-8-sig") as f:
                    callback(True, f.read().splitlines())
            except Exception as e:
                callback(False, f"Erreur : {e}")
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            self._cb_import = callback
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType('*/*')
            PythonActivity.mActivity.startActivityForResult(intent, self.REQ_IMPORT)
        except Exception as e:
            callback(False, f"Erreur : {e}")

    # ---------- Retour des sélecteurs ----------
    def _on_activity_result(self, request_code, result_code, intent):
        if request_code not in (self.REQ_IMPORT, self.REQ_EXPORT):
            return
        ok_android = (result_code == -1 and intent is not None)  # RESULT_OK = -1
        if request_code == self.REQ_EXPORT:
            callback = self._cb_export
            ok, info = False, "Export annulé."
            if ok_android:
                try:
                    from jnius import autoclass
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    OutputStreamWriter = autoclass('java.io.OutputStreamWriter')
                    String = autoclass('java.lang.String')
                    uri = intent.getData()
                    flux = PythonActivity.mActivity.getContentResolver().openOutputStream(uri)
                    ecrivain = OutputStreamWriter(flux, "UTF-8")
                    ecrivain.write(String(self._contenu_export))
                    ecrivain.flush()
                    ecrivain.close()
                    ok, info = True, "Fichier enregistré avec succès."
                except Exception as e:
                    info = f"Erreur : {e}"
            self._contenu_export = None
            if callback:
                Clock.schedule_once(lambda dt: callback(ok, info), 0)
        else:
            callback = self._cb_import
            ok, resultat = False, "Import annulé."
            if ok_android:
                try:
                    from jnius import autoclass
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    InputStreamReader = autoclass('java.io.InputStreamReader')
                    BufferedReader = autoclass('java.io.BufferedReader')
                    uri = intent.getData()
                    flux = PythonActivity.mActivity.getContentResolver().openInputStream(uri)
                    lecteur = BufferedReader(InputStreamReader(flux, "UTF-8"))
                    lignes = []
                    ligne = lecteur.readLine()
                    while ligne is not None:
                        lignes.append(str(ligne))
                        ligne = lecteur.readLine()
                    lecteur.close()
                    ok, resultat = True, lignes
                except Exception as e:
                    resultat = f"Erreur : {e}"
            if callback:
                Clock.schedule_once(lambda dt: callback(ok, resultat), 0)


PF = Plateforme()


# ====================================================
# PETITS CONSTRUCTEURS D'INTERFACE (tailles en dp / sp)
# ====================================================
def titre(texte, taille=24, hauteur=70):
    return Label(text=texte, font_size=sp(taille), bold=True, halign="center",
                 size_hint=(1, None), height=dp(hauteur))


def bouton(texte, couleur=None, hauteur=56, taille=18):
    b = Button(text=texte, font_size=sp(taille), size_hint=(1, None), height=dp(hauteur),
               halign="center")
    if couleur:
        b.background_color = couleur
    return b


def champ(hint, hauteur=50, **kw):
    return TextInput(hint_text=hint, multiline=False, font_size=sp(18),
                     size_hint=(1, None), height=dp(hauteur), **kw)


def etiquette(texte="", taille=14, hauteur=None, halign="left", couleur=BLANC):
    kw = {}
    if hauteur:
        kw = dict(size_hint=(1, None), height=dp(hauteur))
    lbl = Label(text=texte, font_size=sp(taille), halign=halign, valign="middle",
                color=couleur, **kw)
    lbl.bind(size=lambda inst, s: setattr(inst, 'text_size', s))
    return lbl


class OptionListe(SpinnerOption):
    """Lignes de la liste déroulante : police lisible, nom complet sur 2 lignes."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.font_size = sp(15)
        self.height = dp(56)
        self.halign = "left"
        self.valign = "middle"
        self.bind(width=lambda inst, w: setattr(inst, 'text_size', (w - dp(16), None)))
        # ====================================================
# APPLICATION
# ====================================================
class PharmacieApp(App):
    def build(self):
        global CHEMIN_DB, DOSSIER_RECUS, DOSSIER_EXPORTS
        CHEMIN_DB, DOSSIER_RECUS, DOSSIER_EXPORTS = preparer_chemins(self.user_data_dir)
        migrer_base(CHEMIN_DB)
        self.layout = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        self.username_courant = ""
        self._medocs_map = {}
        self._recu_courant = ""
        self.panier = []
        self.afficher_connexion()
        Window.bind(on_keyboard=self._touche)
        return self.layout

    def on_start(self):
        PF.lier()
        PF.forcer_portrait()

    def on_pause(self):
        # Indispensable : l'app reste en vie quand on ouvre le partage ou le sélecteur de fichiers
        return True

    def on_resume(self):
        pass

    def _touche(self, fenetre, key, *args):
        """Bouton Retour d'Android : revient au menu au lieu de quitter l'app."""
        if key == 27 and self.username_courant:
            self.afficher_menu()
            return True
        return False

    # ====================================================
    # CONNEXION
    # ====================================================
    def afficher_connexion(self):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("CONNEXION", 28))

        self.user_input = champ("Nom d'utilisateur")
        self.layout.add_widget(self.user_input)

        self.pass_input = champ("Mot de passe", password=True)
        self.layout.add_widget(self.pass_input)

        btn_login = bouton("SE CONNECTER", (0, 0.5, 0, 1))
        btn_login.bind(on_press=self.verifier_connexion)
        self.layout.add_widget(btn_login)

        self.message = Label(text="", font_size=sp(16), color=ROUGE)
        self.layout.add_widget(self.message)

    def verifier_connexion(self, instance):
        username = self.user_input.text.strip()
        password = self.pass_input.text.strip()

        if not username or not password:
            self.message.text = "Veuillez remplir tous les champs."
            return

        try:
            conn = connexion(CHEMIN_DB)
            try:
                user = conn.execute("SELECT * FROM utilisateurs WHERE username=?", (username,)).fetchone()
            finally:
                conn.close()

            if user:
                h = hashlib.sha256((user["sel"] + password).encode()).hexdigest()
                if h == user["password_hash"]:
                    self.username_courant = username
                    self.afficher_menu()
                else:
                    self.message.text = "Mot de passe incorrect."
            else:
                self.message.text = "Utilisateur introuvable."
        except Exception as e:
            self.message.text = f"Erreur : {str(e)}"

    # ====================================================
    # MENU PRINCIPAL
    # ====================================================
    def afficher_menu(self, instance=None):
        self.layout.clear_widgets()
        self.layout.add_widget(titre(f"DÉPÔT PHARMACEUTIQUE\n{self.username_courant}", 20))

        grille = GridLayout(cols=2, spacing=dp(10))
        elements = [
            ("VENDRE", self.afficher_vendre, (0, 0.6, 0, 1), 20),
            ("STOCK", self.afficher_stock, None, 20),
            ("REÇUS", self.afficher_recus, None, 20),
            ("COMMANDE", self.afficher_commande, None, 18),
            ("IMPORT /\nEXPORT CSV", self.afficher_donnees, None, 16),
            ("PARAMÈTRES", self.afficher_parametres, None, 16),
        ]
        for texte, action, couleur, taille in elements:
            b = Button(text=texte, font_size=sp(taille), halign="center")
            if couleur:
                b.background_color = couleur
            b.bind(on_press=action)
            grille.add_widget(b)
        self.layout.add_widget(grille)

        btn_quitter = bouton("QUITTER", (0.8, 0, 0, 1))
        btn_quitter.bind(on_press=self.deconnexion)
        self.layout.add_widget(btn_quitter)

    def deconnexion(self, instance):
        App.get_running_app().stop()

    # ====================================================
    # ÉCRAN VENDRE (liste déroulante + panier + nom du client)
    # ====================================================
    def afficher_vendre(self, instance=None):
        self.layout.clear_widgets()

        entete = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(8))
        btn_menu = Button(text="< MENU", font_size=sp(14), size_hint=(0.3, 1),
                          background_color=(0.5, 0.5, 0.5, 1))
        btn_menu.bind(on_press=self.afficher_menu)
        entete.add_widget(btn_menu)
        entete.add_widget(Label(text="VENDRE", font_size=sp(20), bold=True))
        self.layout.add_widget(entete)

        self.input_recherche = champ("Rechercher un médicament...", 46)
        self.layout.add_widget(self.input_recherche)

        self.spin_medoc = Spinner(text=TEXTE_CHOIX, values=[], font_size=sp(16),
                                  size_hint=(1, None), height=dp(50), option_cls=OptionListe)
        self.layout.add_widget(self.spin_medoc)

        ligne_ajout = BoxLayout(size_hint=(1, None), height=dp(50), spacing=dp(8))
        self.input_qte = TextInput(hint_text="Qté", multiline=False, input_filter='int',
                                   font_size=sp(18), size_hint=(0.3, 1), padding=[dp(8), dp(13)])
        btn_ajouter = Button(text="AJOUTER AU PANIER", font_size=sp(15), size_hint=(0.7, 1),
                             background_color=(0.1, 0.4, 0.8, 1))
        btn_ajouter.bind(on_press=self.ajouter_panier)
        ligne_ajout.add_widget(self.input_qte)
        ligne_ajout.add_widget(btn_ajouter)
        self.layout.add_widget(ligne_ajout)

        self.msg_vendre = etiquette("", 14, 44, "center")
        self.layout.add_widget(self.msg_vendre)

        scroll = ScrollView()
        self.panier_grille = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.panier_grille.bind(minimum_height=self.panier_grille.setter('height'))
        scroll.add_widget(self.panier_grille)
        self.layout.add_widget(scroll)

        ligne_total = BoxLayout(size_hint=(1, None), height=dp(38), spacing=dp(8))
        self.lbl_total = etiquette("", 16)
        btn_vider = Button(text="VIDER", font_size=sp(13), size_hint=(0.25, 1),
                           background_color=(0.8, 0.3, 0.1, 1))
        btn_vider.bind(on_press=self.vider_panier)
        ligne_total.add_widget(self.lbl_total)
        ligne_total.add_widget(btn_vider)
        self.layout.add_widget(ligne_total)

        self.input_client = champ("Nom du client (facultatif)", 46)
        self.layout.add_widget(self.input_client)

        btn_valider = bouton("VALIDER LA VENTE", (0, 0.5, 0, 1), hauteur=52)
        btn_valider.bind(on_press=self.valider_vente)
        self.layout.add_widget(btn_valider)

        self._charger_medocs("")
        self._rafraichir_panier()
        self.input_recherche.bind(text=lambda inst, val: self._charger_medocs(val))
        self.spin_medoc.bind(text=self._medoc_choisi)

    def _charger_medocs(self, recherche):
        try:
            rows = lister_medicaments(CHEMIN_DB, recherche)
        except Exception as e:
            self._erreur_vente(f"Erreur : {e}")
            return
        self._medocs_map = {}
        valeurs = []
        for r in rows[:150]:
            etiq = f"{r['nom']}  ·  stock {r['stock']}"
            if etiq in self._medocs_map:
                etiq += f"  #{r['id']}"
            self._medocs_map[etiq] = r
            valeurs.append(etiq)
        self.spin_medoc.values = valeurs
        if self.spin_medoc.text not in self._medocs_map:
            self.spin_medoc.text = TEXTE_CHOIX if valeurs else "Aucun résultat"
        if recherche and len(valeurs) == 1:
            self.spin_medoc.text = valeurs[0]

    def _medoc_choisi(self, spinner, texte):
        r = self._medocs_map.get(texte)
        if r:
            self.msg_vendre.color = BLANC
            self.msg_vendre.text = f"Prix : {fmt_aff(r['prix_vente'])} FCFA   |   Stock : {r['stock']}"

    def _erreur_vente(self, texte):
        self.msg_vendre.color = ROUGE
        self.msg_vendre.text = texte

    def _rafraichir_panier(self):
        self.panier_grille.clear_widgets()
        total = 0
        if not self.panier:
            self.panier_grille.add_widget(etiquette(
                "Panier vide. Choisissez un produit, entrez la quantité, puis « AJOUTER AU PANIER ».",
                13, 50, "center"))
        for i, l in enumerate(self.panier):
            sous_total = l["qte"] * l["prix"]
            total += sous_total
            ligne = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            lbl = etiquette(f"{l['qte']} x {l['nom']}\n{fmt_aff(l['prix'])} F  =  {fmt_aff(sous_total)} F", 13)
            lbl.size_hint_x = 0.82
            b = Button(text="X", font_size=sp(16), size_hint=(0.18, 1),
                       background_color=(0.8, 0, 0, 1))
            b.bind(on_press=lambda x, idx=i: self._retirer_ligne(idx))
            ligne.add_widget(lbl)
            ligne.add_widget(b)
            self.panier_grille.add_widget(ligne)
        if self.panier:
            self.lbl_total.text = f"TOTAL : {fmt_aff(total)} FCFA  ({len(self.panier)} article(s))"
        else:
            self.lbl_total.text = "TOTAL : 0 FCFA"

    def _retirer_ligne(self, idx):
        if 0 <= idx < len(self.panier):
            self.panier.pop(idx)
        self._rafraichir_panier()

    def vider_panier(self, instance):
        self.panier = []
        self._rafraichir_panier()

    def ajouter_panier(self, instance):
        r = self._medocs_map.get(self.spin_medoc.text)
        if r is None:
            self._erreur_vente("Choisissez un médicament dans la liste.")
            return
        try:
            qte = int(self.input_qte.text.strip())
        except ValueError:
            self._erreur_vente("Entrez la quantité.")
            return
        if qte <= 0:
            self._erreur_vente("La quantité doit être supérieure à 0.")
            return
        deja = next((l for l in self.panier if l["id"] == r["id"]), None)
        total_qte = qte + (deja["qte"] if deja else 0)
        if total_qte > (r["stock"] or 0):
            self._erreur_vente(f"Stock insuffisant ({r['stock']} dispo).")
            return
        if deja:
            deja["qte"] = total_qte
        else:
            self.panier.append({"id": r["id"], "nom": r["nom"], "qte": qte,
                                "prix": r["prix_vente"] or 0})
        self.input_qte.text = ""
        self.input_recherche.text = ""
        self._charger_medocs("")
        self.spin_medoc.text = TEXTE_CHOIX
        self._rafraichir_panier()
        self.msg_vendre.color = VERT
        self.msg_vendre.text = f"Ajouté : {qte} x {r['nom']}"

    def valider_vente(self, instance):
        if not self.panier:
            self._erreur_vente("Le panier est vide.")
            return
        try:
            vente = enregistrer_vente_panier(
                CHEMIN_DB, [(l["id"], l["qte"]) for l in self.panier],
                self.input_client.text.strip())
            texte = construire_recu(lire_parametres(CHEMIN_DB), vente)
            ecrire_recu(DOSSIER_RECUS, vente["groupe"], texte)
        except ValueError as e:
            self._erreur_vente(str(e))
            return
        except Exception as e:
            self._erreur_vente(f"Erreur : {str(e)}")
            return

        nb = len(vente["lignes"])
        self.panier = []
        self.input_client.text = ""
        self._charger_medocs(self.input_recherche.text)
        self._rafraichir_panier()
        self.msg_vendre.color = VERT
        self.msg_vendre.text = (f"Vente enregistrée : {nb} article(s)\n"
                                f"Total : {fmt_aff(vente['total'])} FCFA - reçu généré")

    # ====================================================
    # ÉCRAN STOCK
    # ====================================================
    def afficher_stock(self, instance=None):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("ETAT DU STOCK", 22, 50))

        scroll = ScrollView()
        grille_stock = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grille_stock.bind(minimum_height=grille_stock.setter('height'))

        try:
            conn = connexion(CHEMIN_DB)
            try:
                produits = conn.execute(
                    "SELECT nom, stock, prix_vente FROM medicaments ORDER BY nom").fetchall()
            finally:
                conn.close()
            for p in produits:
                bas = (p["stock"] or 0) <= SEUIL_DEFAUT
                lbl = etiquette(f"{p['nom']}\nStock : {p['stock']}   |   {fmt_aff(p['prix_vente'])} F",
                                14, 56, "left", (1, 0.6, 0.5, 1) if bas else BLANC)
                grille_stock.add_widget(lbl)
        except Exception as e:
            grille_stock.add_widget(etiquette(f"Erreur : {str(e)}", 14, 56))

        scroll.add_widget(grille_stock)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=self.afficher_menu)
        self.layout.add_widget(btn_retour)

    # ====================================================
    # ÉCRAN REÇUS
    # ====================================================
    def afficher_recus(self, instance=None):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("DERNIERS REÇUS", 22, 50))

        scroll = ScrollView()
        grille_recus = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        grille_recus.bind(minimum_height=grille_recus.setter('height'))

        try:
            fichiers = []
            if os.path.exists(DOSSIER_RECUS):
                fichiers = sorted([f for f in os.listdir(DOSSIER_RECUS) if f.endswith(".txt")], reverse=True)
            if not fichiers:
                grille_recus.add_widget(etiquette("Aucun reçu pour le moment.\nFaites une vente !",
                                                  16, 80, "center"))
            else:
                for f in fichiers[:30]:
                    btn = Button(text=f, size_hint_y=None, height=dp(48), font_size=sp(14))
                    btn.bind(on_press=lambda x, nom_fichier=f: self.ouvrir_recu(nom_fichier))
                    grille_recus.add_widget(btn)
        except Exception as e:
            grille_recus.add_widget(etiquette(f"Erreur : {str(e)}", 14, 56))

        scroll.add_widget(grille_recus)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=self.afficher_menu)
        self.layout.add_widget(btn_retour)

    def ouvrir_recu(self, nom_fichier):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("DÉTAIL DU REÇU", 22, 50))

        scroll = ScrollView()
        try:
            with open(os.path.join(DOSSIER_RECUS, nom_fichier), "r", encoding="utf-8") as f:
                self._recu_courant = f.read()
        except Exception as e:
            self._recu_courant = f"Erreur de lecture : {e}"

        lbl_texte = Label(text=self._recu_courant, font_size=sp(12), size_hint_y=None,
                          halign="left", valign="top", color=BLANC)
        lbl_texte.bind(
            width=lambda inst, w: setattr(inst, 'text_size', (w, None)),
            texture_size=lambda inst, ts: setattr(inst, 'height', ts[1])
        )
        scroll.add_widget(lbl_texte)
        self.layout.add_widget(scroll)

        self.msg_recu = etiquette("", 13, 24, "center")
        self.layout.add_widget(self.msg_recu)

        btn_partager = bouton("PARTAGER LE REÇU", (0, 0.5, 0, 1))
        btn_partager.bind(on_press=self._partager_recu)
        self.layout.add_widget(btn_partager)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=self.afficher_recus)
        self.layout.add_widget(btn_retour)

    def _partager_recu(self, instance):
        if PF.partager_texte(self._recu_courant, "Partager le reçu"):
            self.msg_recu.text = ""
        else:
            self.msg_recu.text = "Reçu copié : collez-le dans WhatsApp ou SMS."

    # ====================================================
    # ÉCRAN COMMANDE (à partager au fournisseur)
    # ====================================================
    def afficher_commande(self, instance=None):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("COMMANDE", 22, 50))

        barre = BoxLayout(size_hint=(1, None), height=dp(50), spacing=dp(8))
        fournisseurs = [TOUS_FOURNISSEURS] + lister_fournisseurs(CHEMIN_DB)
        self.cmd_fourn = Spinner(text=TOUS_FOURNISSEURS, values=fournisseurs, font_size=sp(14),
                                 size_hint=(0.62, 1), option_cls=OptionListe)
        self.cmd_seuil = TextInput(text=str(SEUIL_DEFAUT), hint_text="Seuil", multiline=False,
                                   input_filter='int', font_size=sp(16), size_hint=(0.38, 1),
                                   padding=[dp(8), dp(14)])
        barre.add_widget(self.cmd_fourn)
        barre.add_widget(self.cmd_seuil)
        self.layout.add_widget(barre)

        self.layout.add_widget(etiquette(
            "Produits dont le stock est inférieur ou égal au seuil (à droite). "
            "Modifiez les quantités avant d'envoyer.", 12, 34, "center"))

        scroll = ScrollView()
        self.cmd_liste = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.cmd_liste.bind(minimum_height=self.cmd_liste.setter('height'))
        scroll.add_widget(self.cmd_liste)
        self.layout.add_widget(scroll)

        self.msg_cmd = etiquette("", 13, 26, "center")
        self.layout.add_widget(self.msg_cmd)

        ligne_btn = BoxLayout(size_hint=(1, None), height=dp(56), spacing=dp(8))
        btn_partager = Button(text="ENVOYER / PARTAGER", font_size=sp(15),
                              background_color=(0, 0.5, 0, 1), halign="center")
        btn_partager.bind(on_press=self._partager_commande)
        btn_copier = Button(text="COPIER", font_size=sp(15), size_hint=(0.45, 1))
        btn_copier.bind(on_press=self._copier_commande)
        ligne_btn.add_widget(btn_partager)
        ligne_btn.add_widget(btn_copier)
        self.layout.add_widget(ligne_btn)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=self.afficher_menu)
        self.layout.add_widget(btn_retour)

        self.cmd_fourn.bind(text=lambda *a: self._remplir_commande())
        self.cmd_seuil.bind(text=lambda *a: self._remplir_commande())
        self._remplir_commande()

    def _remplir_commande(self):
        self.cmd_liste.clear_widgets()
        self.cmd_champs = []
        try:
            seuil = int(self.cmd_seuil.text or 0)
        except ValueError:
            seuil = SEUIL_DEFAUT
        fournisseur = None if self.cmd_fourn.text == TOUS_FOURNISSEURS else self.cmd_fourn.text
        try:
            produits = produits_a_commander(CHEMIN_DB, seuil, fournisseur)
        except Exception as e:
            self.cmd_liste.add_widget(etiquette(f"Erreur : {e}", 14, 56))
            return
        if not produits:
            self.cmd_liste.add_widget(etiquette("Aucun produit à commander.", 15, 60, "center"))
            return
        for p in produits:
            ligne = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
            detail = f"stock {p['stock']}"
            if p["fournisseur"]:
                detail += f" · {p['fournisseur']}"
            lbl = etiquette(f"{p['nom']}\n{detail}", 13)
            lbl.size_hint_x = 0.68
            qte_defaut = max(2 * seuil - (p["stock"] or 0), 1)
            saisie = TextInput(text=str(qte_defaut), multiline=False, input_filter='int',
                               font_size=sp(16), halign="center", size_hint=(0.32, 1),
                               padding=[dp(6), dp(17)])
            ligne.add_widget(lbl)
            ligne.add_widget(saisie)
            self.cmd_liste.add_widget(ligne)
            self.cmd_champs.append((p, saisie))

    def _texte_commande(self):
        lignes = []
        for p, saisie in self.cmd_champs:
            try:
                q = int(saisie.text or 0)
            except ValueError:
                q = 0
            if q > 0:
                lignes.append((p["nom"], q, p["fournisseur"] or ""))
        if not lignes:
            self.msg_cmd.color = ROUGE
            self.msg_cmd.text = "Aucune quantité à commander."
            return None
        nom_depot = normaliser_nom(lire_parametres(CHEMIN_DB).get("nom", ""))
        fournisseur = None if self.cmd_fourn.text == TOUS_FOURNISSEURS else self.cmd_fourn.text
        return texte_commande(nom_depot, lignes, fournisseur)

    def _partager_commande(self, instance):
        texte = self._texte_commande()
        if not texte:
            return
        self.msg_cmd.color = VERT
        if PF.partager_texte(texte, "Envoyer la commande"):
            self.msg_cmd.text = ""
        else:
            self.msg_cmd.text = "Commande copiée : collez-la dans WhatsApp, SMS ou email."

    def _copier_commande(self, instance):
        texte = self._texte_commande()
        if not texte:
            return
        Clipboard.copy(texte)
        self.msg_cmd.color = VERT
        self.msg_cmd.text = "Commande copiée : collez-la dans WhatsApp, SMS ou email."

    # ====================================================
    # ÉCRAN IMPORT / EXPORT CSV
    # ====================================================
    def afficher_donnees(self, instance=None):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("IMPORT / EXPORT CSV", 20, 60))

        b_stock = bouton("EXPORTER LE STOCK (CSV)", (0, 0.5, 0, 1), taille=16)
        b_stock.bind(on_press=self._exporter_stock)
        self.layout.add_widget(b_stock)

        b_ventes = bouton("EXPORTER LES VENTES (CSV)", (0, 0.5, 0, 1), taille=16)
        b_ventes.bind(on_press=self._exporter_ventes)
        self.layout.add_widget(b_ventes)

        b_import = bouton("IMPORTER DES MÉDICAMENTS (CSV)", (0.1, 0.4, 0.8, 1), taille=15)
        b_import.bind(on_press=self._lancer_import)
        self.layout.add_widget(b_import)

        self.msg_donnees = etiquette(
            "Export : choisissez où enregistrer le fichier (Téléchargements, Drive...). "
            "Il s'ouvre dans Excel ou Google Sheets.\n\n"
            "Import : les produits de même nom et même lot sont mis à jour "
            "(stock et prix remplacés), les autres sont ajoutés. "
            "Utilisez d'abord l'export du stock pour obtenir le bon modèle.",
            13, None, "center")
        self.layout.add_widget(self.msg_donnees)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=self.afficher_menu)
        self.layout.add_widget(btn_retour)

    def _fin_donnees(self, ok, info):
        self.msg_donnees.color = VERT if ok else ROUGE
        self.msg_donnees.text = info

    def _exporter_stock(self, instance):
        try:
            contenu = exporter_stock_csv(CHEMIN_DB)
        except Exception as e:
            self._fin_donnees(False, f"Erreur : {e}")
            return
        nom = f"stock_{datetime.now().strftime('%Y%m%d')}.csv"
        PF.exporter_fichier(nom, contenu, self._fin_donnees)

    def _exporter_ventes(self, instance):
        try:
            contenu = exporter_ventes_csv(CHEMIN_DB)
        except Exception as e:
            self._fin_donnees(False, f"Erreur : {e}")
            return
        nom = f"ventes_{datetime.now().strftime('%Y%m%d')}.csv"
        PF.exporter_fichier(nom, contenu, self._fin_donnees)

    def _lancer_import(self, instance):
        PF.importer_fichier(self._apres_import)

    def _apres_import(self, ok, resultat):
        if not ok:
            self._fin_donnees(False, resultat)
            return
        medocs, erreurs = lire_csv_medicaments(resultat)
        if not medocs:
            self._fin_donnees(False, "Import impossible.\n" + "\n".join(erreurs[:4]))
            return
        try:
            ajoutes, maj = importer_medicaments(CHEMIN_DB, medocs)
        except Exception as e:
            self._fin_donnees(False, f"Erreur pendant l'import : {e}")
            return
        info = f"Import terminé : {ajoutes} ajouté(s), {maj} mis à jour."
        if erreurs:
            info += f"\n{len(erreurs)} ligne(s) ignorée(s) :\n" + "\n".join(erreurs[:3])
        self._fin_donnees(True, info)

    # ====================================================
    # ÉCRAN PARAMÈTRES
    # ====================================================
    def afficher_parametres(self, instance=None):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("PARAMÈTRES", 22, 50))

        scroll = ScrollView()
        grille = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        grille.bind(minimum_height=grille.setter('height'))

        params = lire_parametres(CHEMIN_DB)
        self.param_inputs = {}
        champs = [
            ("nom", "Nom du dépôt pharmaceutique"),
            ("adresse", "Adresse"),
            ("telephone", "Téléphone"),
            ("email", "Email"),
            ("nif", "NIF"),
            ("message", "Message du reçu"),
        ]
        for cle, label_txt in champs:
            grille.add_widget(etiquette(label_txt, 14, 28))
            inp = TextInput(text=params.get(cle, "") or "", multiline=False, font_size=sp(16),
                            size_hint_y=None, height=dp(48))
            self.param_inputs[cle] = inp
            grille.add_widget(inp)

        scroll.add_widget(grille)
        self.layout.add_widget(scroll)

        self.msg_params = etiquette("", 14, 30, "center")
        self.layout.add_widget(self.msg_params)

        btn_sauver = bouton("ENREGISTRER", (0, 0.6, 0, 1))
        btn_sauver.bind(on_press=self.sauvegarder_parametres)
        self.layout.add_widget(btn_sauver)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=self.afficher_menu)
        self.layout.add_widget(btn_retour)

    def sauvegarder_parametres(self, instance):
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            try:
                c = conn.cursor()
                for cle, inp in self.param_inputs.items():
                    valeur = inp.text.strip()
                    if cle == "nom" and valeur:
                        valeur = normaliser_nom(valeur)
                        inp.text = valeur
                    if valeur:
                        c.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES (?, ?)",
                                  (cle, valeur))
                    else:
                        c.execute("DELETE FROM parametres WHERE cle=?", (cle,))
                conn.commit()
            finally:
                conn.close()
            self.msg_params.color = VERT
            self.msg_params.text = "Paramètres sauvegardés !"
        except Exception as e:
            self.msg_params.color = ROUGE
            self.msg_params.text = f"Erreur : {str(e)}"
            # ====================================================
# NOUVEAU : MODIFIER UN PRODUIT
# ====================================================
def afficher_modifier(self, instance=None):
    self.layout.clear_widgets()
    self.layout.add_widget(titre("MODIFIER UN PRODUIT", 22, 50))

    self.spin_modif = Spinner(text="Choisir un produit", values=[], font_size=sp(16),
                              size_hint=(1, None), height=dp(52), option_cls=OptionListe)
    self.layout.add_widget(self.spin_modif)

    self.modif_nom = champ("Nouveau nom")
    self.modif_pa = champ("Nouveau prix d'achat", input_filter='float')
    self.modif_pv = champ("Nouveau prix de vente", input_filter='float')
    self.modif_stock = champ("Nouveau stock", input_filter='int')
    
    for c in (self.modif_nom, self.modif_pa, self.modif_pv, self.modif_stock):
        self.layout.add_widget(c)

    self.msg_modif = etiquette("", 14, 30, "center")
    self.layout.add_widget(self.msg_modif)

    btn_sauver = bouton("ENREGISTRER LES MODIFICATIONS", (0, 0.6, 0, 1), taille=16)
    btn_sauver.bind(on_press=self._sauvegarder_modification)
    self.layout.add_widget(btn_sauver)

    btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
    btn_retour.bind(on_press=self.afficher_menu)
    self.layout.add_widget(btn_retour)

    self._charger_modif()
    self.spin_modif.bind(text=self._afficher_valeurs_modif)

def _charger_modif(self):
    try:
        conn = connexion(CHEMIN_DB)
        rows = conn.execute("SELECT * FROM medicaments ORDER BY nom").fetchall()
        conn.close()
        self._modifs_map = {}
        valeurs = []
        for r in rows:
            etiq = r["nom"]
            self._modifs_map[etiq] = dict(r)
            valeurs.append(etiq)
        self.spin_modif.values = valeurs
    except Exception as e:
        self.msg_modif.text = f"Erreur : {e}"

def _afficher_valeurs_modif(self, spinner, texte):
    r = getattr(self, '_modifs_map', {}).get(texte)
    if r:
        self.modif_nom.text = r["nom"]
        self.modif_pa.text = str(r["prix_achat"])
        self.modif_pv.text = str(r["prix_vente"])
        self.modif_stock.text = str(r["stock"])

def _sauvegarder_modification(self, instance):
    r = getattr(self, '_modifs_map', {}).get(self.spin_modif.text)
    if not r:
        self.msg_modif.text = "Choisissez un produit."
        return
    try:
        nom = self.modif_nom.text.strip() or r["nom"]
        pa = float(self.modif_pa.text or r["prix_achat"])
        pv = float(self.modif_pv.text or r["prix_vente"])
        stock = int(self.modif_stock.text or r["stock"])
        
        conn = connexion(CHEMIN_DB)
        conn.execute("UPDATE medicaments SET nom=?, prix_achat=?, prix_vente=?, stock=? WHERE id=?",
                     (nom, pa, pv, stock, r["id"]))
        conn.commit()
        conn.close()
        self.msg_modif.color = VERT
        self.msg_modif.text = "Produit modifié avec succès !"
        self._charger_modif()
    except ValueError:
        self.msg_modif.color = ROUGE
        self.msg_modif.text = "Valeurs invalides."
    except Exception as e:
        self.msg_modif.color = ROUGE
        self.msg_modif.text = f"Erreur : {e}"


# ====================================================
# NOUVEAU : BILAN DU JOUR
# ====================================================
def afficher_bilan(self, instance=None):
    self.layout.clear_widgets()
    self.layout.add_widget(titre("BILAN DU JOUR", 22, 50))

    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn = connexion(CHEMIN_DB)
        ventes = conn.execute(
            "SELECT * FROM ventes WHERE date_vente LIKE ?", (f"{aujourd_hui}%",)
        ).fetchall()
        conn.close()
    except Exception as e:
        self.layout.add_widget(etiquette(f"Erreur : {e}", 14))
        ventes = []

    if not ventes:
        self.layout.add_widget(etiquette(f"Aucune vente aujourd'hui ({aujourd_hui}).", 16, 100, "center"))
    else:
        ca = sum(v["total"] for v in ventes)
        groupes = len(set(v["groupe"] for v in ventes if v["groupe"]))
        articles = sum(v["quantite"] for v in ventes)
        
        top = {}
        for v in ventes:
            top[v["medicament"]] = top.get(v["medicament"], 0) + v["quantite"]
        top3 = sorted(top.items(), key=lambda x: -x[1])[:3]

        txt = f"📅 Date : {aujourd_hui}\n\n"
        txt += f"💰 Chiffre d'affaires :\n   {fmt_aff(ca)} FCFA\n\n"
        txt += f"🧾 Transactions : {groupes}\n"
        txt += f"📦 Articles vendus : {articles}\n\n"
        txt += "🏆 TOP 3 PRODUITS :\n"
        for nom, q in top3:
            txt += f"  • {nom} : {q}\n"
            
        self.layout.add_widget(etiquette(txt, 16, None, "left"))

    btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
    btn_retour.bind(on_press=self.afficher_menu)
    self.layout.add_widget(btn_retour)


# ====================================================
# NOUVEAU : GESTION DES UTILISATEURS
# ====================================================
def afficher_utilisateurs(self, instance=None):
    self.layout.clear_widgets()
    self.layout.add_widget(titre("UTILISATEURS", 22, 50))

    scroll = ScrollView()
    grille = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
    grille.bind(minimum_height=grille.setter('height'))

    try:
        conn = connexion(CHEMIN_DB)
        users = conn.execute("SELECT id, username, role FROM utilisateurs ORDER BY username").fetchall()
        conn.close()
        for u in users:
            txt = f"{u['username']}  ({u['role']})"
            grille.add_widget(etiquette(txt, 15, 30))
    except Exception as e:
        grille.add_widget(etiquette(f"Erreur : {e}", 14))

    scroll.add_widget(grille)
    self.layout.add_widget(scroll)

    # Formulaire d'ajout
    self.nouv_user = champ("Nouveau vendeur (nom)")
    self.nouv_mdp = champ("Mot de passe", password=True)
    self.layout.add_widget(self.nouv_user)
    self.layout.add_widget(self.nouv_mdp)

    self.msg_user = etiquette("", 14, 24, "center")
    self.layout.add_widget(self.msg_user)

    btn_ajouter = bouton("AJOUTER LE VENDEUR", (0, 0.6, 0, 1), taille=16)
    btn_ajouter.bind(on_press=self._ajouter_utilisateur)
    self.layout.add_widget(btn_ajouter)

    btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
    btn_retour.bind(on_press=self.afficher_menu)
    self.layout.add_widget(btn_retour)

def _ajouter_utilisateur(self, instance):
    u = self.nouv_user.text.strip()
    m = self.nouv_mdp.text.strip()
    if not u or len(m) < 4:
        self.msg_user.color = ROUGE
        self.msg_user.text = "Nom requis et mot de passe (min 4 car.)."
        return
    try:
        conn = connexion(CHEMIN_DB)
        if conn.execute("SELECT 1 FROM utilisateurs WHERE username=?", (u,)).fetchone():
            self.msg_user.color = ROUGE
            self.msg_user.text = "Ce nom existe déjà."
            conn.close()
            return
        sel = os.urandom(16).hex()
        h = hashlib.sha256((sel + m).encode()).hexdigest()
        conn.execute("INSERT INTO utilisateurs (username, password_hash, sel, role) VALUES (?, ?, ?, 'vendeur')", (u, h, sel))
        conn.commit()
        conn.close()
        self.msg_user.color = VERT
        self.msg_user.text = f"Vendeur {u} ajouté !"
        self.nouv_user.text = ""
        self.nouv_mdp.text = ""
        self.afficher_utilisateurs()
    except Exception as e:
        self.msg_user.color = ROUGE
        self.msg_user.text = f"Erreur : {e}"
        def afficher_menu(self, instance=None):
    self.layout.clear_widgets()
    self.layout.add_widget(titre(f"DÉPÔT PHARMACEUTIQUE\n{self.username_courant}", 18, 60))

    grille = GridLayout(cols=2, spacing=dp(8))
    elements = [
        ("VENDRE", self.afficher_vendre, (0, 0.6, 0, 1), 20),
        ("STOCK", self.afficher_stock, None, 20),
        ("REÇUS", self.afficher_recus, None, 20),
        ("BILAN JOUR", self.afficher_bilan, None, 18),
        ("MODIFIER", self.afficher_modifier, None, 18),
        ("COMMANDE", self.afficher_commande, None, 18),
        ("UTILISATEURS", self.afficher_utilisateurs, None, 18),
        ("CSV / PARAM", self.afficher_donnees, None, 18),
    ]
    for texte, action, couleur, taille in elements:
        b = Button(text=texte, font_size=sp(taille), halign="center")
        if couleur:
            b.background_color = couleur
        b.bind(on_press=action)
        grille.add_widget(b)
    self.layout.add_widget(grille)

    btn_quitter = bouton("QUITTER", (0.8, 0, 0, 1))
    btn_quitter.bind(on_press=self.deconnexion)
    self.layout.add_widget(btn_quitter)


if __name__ == '__main__':
    PharmacieApp().run()
