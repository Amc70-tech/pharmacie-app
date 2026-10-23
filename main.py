from kivy.config import Config
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner  # <-- NOUVEL IMPORT
import sqlite3
import hashlib
import os
import shutil
from datetime import datetime

# Le clavier ne cache plus le champ en cours de saisie
Window.softinput_mode = 'below_target'

CHEMIN_DB = ""
DOSSIER_RECUS = ""

ROUGE = (1, 0.3, 0.3, 1)
VERT = (0, 1, 0, 1)


def preparer_chemins(base):
    os.makedirs(base, exist_ok=True)
    chemin_db = os.path.join(base, "pharmacie.db")
    if not os.path.exists(chemin_db):
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pharmacie.db")
        if os.path.exists(source):
            shutil.copy(source, chemin_db)
    dossier_recus = os.path.join(base, "recus")
    os.makedirs(dossier_recus, exist_ok=True)
    return chemin_db, dossier_recus


def titre(texte, taille=24):
    return Label(text=texte, font_size=sp(taille), bold=True, halign="center",
                 size_hint=(1, None), height=dp(70))


def bouton(texte, couleur=None, hauteur=56, taille=18):
    b = Button(text=texte, font_size=sp(taille), size_hint=(1, None), height=dp(hauteur))
    if couleur:
        b.background_color = couleur
    return b


def champ(hint, **kw):
    return TextInput(hint_text=hint, multiline=False, font_size=sp(18),
                     size_hint=(1, None), height=dp(50), **kw)


class PharmacieApp(App):
    def build(self):
        global CHEMIN_DB, DOSSIER_RECUS
        CHEMIN_DB, DOSSIER_RECUS = preparer_chemins(self.user_data_dir)
        self.layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(12))
        self.username_courant = ""
        self.afficher_connexion()
        return self.layout

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
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM utilisateurs WHERE username=?", (username,))
            user = c.fetchone()
            conn.close()

            if user:
                sel = user["sel"]
                h = hashlib.sha256((sel + password).encode()).hexdigest()
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
    def afficher_menu(self):
        self.layout.clear_widgets()

        self.layout.add_widget(titre(f"PHARMACIE\n{self.username_courant}", 24))

        grille = GridLayout(cols=2, spacing=dp(12))

        btn_vendre = Button(text="VENDRE", font_size=sp(20), background_color=(0, 0.6, 0, 1))
        btn_vendre.bind(on_press=self.afficher_vendre)

        btn_stock = Button(text="STOCK", font_size=sp(20))
        btn_stock.bind(on_press=self.afficher_stock)

        btn_recus = Button(text="REÇUS", font_size=sp(20))
        btn_recus.bind(on_press=self.afficher_recus)

        btn_params = Button(text="PARAMÈTRES", font_size=sp(18))
        btn_params.bind(on_press=self.afficher_parametres)

        for b in (btn_vendre, btn_stock, btn_recus, btn_params):
            grille.add_widget(b)

        self.layout.add_widget(grille)

        btn_quitter = bouton("QUITTER", (0.8, 0, 0, 1))
        btn_quitter.bind(on_press=self.deconnexion)
        self.layout.add_widget(btn_quitter)

    def deconnexion(self, instance):
        App.get_running_app().stop()

    # ====================================================
    # ÉCRAN VENDRE
    # ====================================================
    def afficher_vendre(self, instance):
        self.layout.clear_widgets()

        self.layout.add_widget(titre("VENDRE", 24))

        # Récupération des produits pour la liste déroulante
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT nom, prix_vente, stock FROM medicaments ORDER BY nom")
            produits = c.fetchall()
            conn.close()
            self.liste_produits = {p["nom"]: p for p in produits}
        except Exception:
            self.liste_produits = {}

        valeurs = list(self.liste_produits.keys())
        if not valeurs:
            valeurs = ["Aucun produit en base"]

        # Liste déroulante
        self.spinner_produit = Spinner(
            text="Sélectionnez un produit",
            values=valeurs,
            font_size=sp(16),
            size_hint=(1, None),
            height=dp(50),
            background_color=(0.2, 0.2, 0.2, 1)
        )
        self.spinner_produit.bind(text=self.maj_info_produit)
        self.layout.add_widget(self.spinner_produit)

        # Label pour afficher le prix et le stock dès qu'on sélectionne
        self.info_produit = Label(text="", font_size=sp(14), color=(0.8, 0.8, 0.8, 1), size_hint=(1, None), height=dp(30))
        self.layout.add_widget(self.info_produit)

        # Champ quantité
        self.input_qte = champ("Quantité", input_filter='int')
        self.layout.add_widget(self.input_qte)

        self.msg_vendre = Label(text="", font_size=sp(16), halign="center")
        self.layout.add_widget(self.msg_vendre)

        btn_valider = bouton("VALIDER LA VENTE", (0, 0.5, 0, 1))
        btn_valider.bind(on_press=self.valider_vente)
        self.layout.add_widget(btn_valider)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def maj_info_produit(self, spinner, text):
        if text in self.liste_produits:
            p = self.liste_produits[text]
            self.info_produit.text = f"Prix : {p['prix_vente']} FCFA  |  Stock : {p['stock']} dispo"
        else:
            self.info_produit.text = ""

    def _erreur_vente(self, texte):
        self.msg_vendre.color = ROUGE
        self.msg_vendre.text = texte

    def valider_vente(self, instance):
        nom = self.spinner_produit.text
        
        if nom not in self.liste_produits:
            self._erreur_vente("Veuillez sélectionner un produit valide.")
            return

        try:
            qte = int(self.input_qte.text.strip())
        except ValueError:
            self._erreur_vente("Erreur : Quantité invalide.")
            return

        if qte <= 0:
            self._erreur_vente("Erreur : Quantité invalide.")
            return

        conn = None
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            produit = self.liste_produits[nom]

            if produit["stock"] < qte:
                self._erreur_vente(f"Stock insuffisant ({produit['stock']} dispo).")
                return

            nouveau_stock = produit["stock"] - qte
            c.execute("UPDATE medicaments SET stock=? WHERE nom=?", (nouveau_stock, nom))

            total = qte * produit["prix_vente"]
            date_v = datetime.now().strftime("%Y-%m-%d %H:%M")
            groupe = datetime.now().strftime("V%Y%m%d_%H%M%S")

            c.execute("INSERT INTO ventes(date_vente,medicament,quantite,prix_unitaire,total,groupe) VALUES(?,?,?,?,?,?)",
                      (date_v, nom, qte, produit["prix_vente"], total, groupe))

            # Paramètres pour le reçu
            c.execute("SELECT cle, valeur FROM parametres")
            params = {row["cle"]: row["valeur"] for row in c.fetchall()}
            nom_pharma = params.get("nom", "PHARMACIE")
            message_recu = params.get("message", "Merci de votre visite !")
            adresse = params.get("adresse", "")
            telephone = params.get("telephone", "")

            conn.commit()

            # Génération du reçu
            os.makedirs(DOSSIER_RECUS, exist_ok=True)
            nom_fichier = os.path.join(DOSSIER_RECUS, f"recu_{groupe}.txt")
            with open(nom_fichier, "w", encoding="utf-8") as f:
                f.write("========================================\n")
                f.write(f"           {nom_pharma.upper()}\n")
                if adresse:
                    f.write(f"           {adresse}\n")
                if telephone:
                    f.write(f"           Tel : {telephone}\n")
                f.write("========================================\n")
                f.write(f"N° : {groupe}\n")
                f.write(f"Date : {date_v}\n")
                f.write("----------------------------------------\n")
                f.write(f"Produit : {nom}\n")
                f.write(f"Quantite : {qte}\n")
                f.write(f"Prix U : {produit['prix_vente']} FCFA\n")
                f.write("----------------------------------------\n")
                f.write(f"TOTAL : {total} FCFA\n")
                f.write("========================================\n")
                f.write(f"{message_recu}\n")

            self.msg_vendre.color = VERT
            self.msg_vendre.text = f"Vendu : {qte} x {nom}\nTotal : {total} FCFA\nReçu généré !"
            self.input_qte.text = ""
            
            # Mettre à jour l'affichage du stock instantanément
            self.spinner_produit.text = "Sélectionnez un produit"
            self.info_produit.text = ""

        except Exception as e:
            self._erreur_vente(f"Erreur : {str(e)}")
        finally:
            if conn:
                conn.close()

    # ====================================================
    # ÉCRAN STOCK
    # ====================================================
    def afficher_stock(self, instance):
        self.layout.clear_widgets()

        self.layout.add_widget(titre("ETAT DU STOCK", 24))

        scroll = ScrollView()
        grille_stock = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grille_stock.bind(minimum_height=grille_stock.setter('height'))

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT nom, stock, prix_vente FROM medicaments ORDER BY nom")
            produits = c.fetchall()
            conn.close()

            for p in produits:
                texte = f"{p['nom']}\nStock : {p['stock']}   |   {p['prix_vente']} F"
                lbl = Label(text=texte, font_size=sp(14), size_hint_y=None, height=dp(56),
                            halign="left", valign="middle", color=(1, 1, 1, 1))
                lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
                grille_stock.add_widget(lbl)

        except Exception as e:
            grille_stock.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(14),
                                          size_hint_y=None, height=dp(56)))

        scroll.add_widget(grille_stock)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # ÉCRAN REÇUS
    # ====================================================
    def afficher_recus(self, instance):
        self.layout.clear_widgets()

        self.layout.add_widget(titre("DERNIERS REÇUS", 24))

        scroll = ScrollView()
        grille_recus = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        grille_recus.bind(minimum_height=grille_recus.setter('height'))

        try:
            fichiers = []
            if os.path.exists(DOSSIER_RECUS):
                fichiers = sorted([f for f in os.listdir(DOSSIER_RECUS) if f.endswith(".txt")], reverse=True)

            if not fichiers:
                grille_recus.add_widget(Label(text="Aucun reçu pour le moment.\nFaites une vente !",
                                              font_size=sp(16), size_hint_y=None, height=dp(80)))
            else:
                for f in fichiers[:20]:
                    btn = Button(text=f, size_hint_y=None, height=dp(48), font_size=sp(14))
                    btn.bind(on_press=lambda x, nom_fichier=f: self.ouvrir_recu(nom_fichier))
                    grille_recus.add_widget(btn)

        except Exception as e:
            grille_recus.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(14),
                                          size_hint_y=None, height=dp(56)))

        scroll.add_widget(grille_recus)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # ÉCRAN LIRE UN REÇU
    # ====================================================
    def ouvrir_recu(self, nom_fichier):
        self.layout.clear_widgets()

        self.layout.add_widget(titre("DÉTAIL DU REÇU", 22))

        scroll = ScrollView()

        chemin = os.path.join(DOSSIER_RECUS, nom_fichier)
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                contenu = f.read()
        except Exception as e:
            contenu = f"Erreur de lecture : {e}"

        lbl_texte = Label(
            text=contenu,
            font_size=sp(12),
            size_hint_y=None,
            halign="left",
            valign="top",
            color=(1, 1, 1, 1)
        )
        lbl_texte.bind(
            width=lambda inst, w: setattr(inst, 'text_size', (w, None)),
            texture_size=lambda inst, ts: setattr(inst, 'height', ts[1])
        )

        scroll.add_widget(lbl_texte)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_recus(None))
        self.layout.add_widget(btn_retour)

    # ====================================================
    # ÉCRAN PARAMÈTRES
    # ====================================================
    def afficher_parametres(self, instance):
        self.layout.clear_widgets()

        self.layout.add_widget(titre("PARAMÈTRES", 24))

        scroll = ScrollView()
        grille = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        grille.bind(minimum_height=grille.setter('height'))

        params = {}
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT cle, valeur FROM parametres")
            for row in c.fetchall():
                params[row["cle"]] = row["valeur"]
            conn.close()
        except Exception:
            pass

        self.param_inputs = {}
        champs = [
            ("nom", "Nom de la pharmacie"),
            ("adresse", "Adresse"),
            ("telephone", "Téléphone"),
            ("email", "Email"),
            ("nif", "NIF"),
            ("message", "Message du reçu")
        ]

        for cle, label_txt in champs:
            lbl = Label(text=label_txt, font_size=sp(14), size_hint_y=None, height=dp(28),
                        halign="left", color=(1, 1, 1, 1))
            lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
            inp = TextInput(text=params.get(cle, ""), multiline=False, font_size=sp(16),
                            size_hint_y=None, height=dp(48))
            self.param_inputs[cle] = inp
            grille.add_widget(lbl)
            grille.add_widget(inp)

        scroll.add_widget(grille)
        self.layout.add_widget(scroll)

        self.msg_params = Label(text="", font_size=sp(14), size_hint=(1, None), height=dp(30))
        self.layout.add_widget(self.msg_params)

        btn_sauver = bouton("ENREGISTRER", (0, 0.6, 0, 1))
        btn_sauver.bind(on_press=self.sauvegarder_parametres)
        self.layout.add_widget(btn_sauver)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def sauvegarder_parametres(self, instance):
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            for cle, inp in self.param_inputs.items():
                valeur = inp.text.strip()
                if valeur:
                    c.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES (?, ?)", (cle, valeur))
            conn.commit()
            conn.close()
            self.msg_params.color = VERT
            self.msg_params.text = "Paramètres sauvegardés !"
        except Exception as e:
            self.msg_params.color = ROUGE
            self.msg_params.text = f"Erreur : {str(e)}"


if __name__ == '__main__':
    PharmacieApp().run()
